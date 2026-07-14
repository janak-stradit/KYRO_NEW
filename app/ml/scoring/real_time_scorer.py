"""
ml/scoring/real_time_scorer.py — Combines all three models into one 0-100
score for a single transaction, with a SHAP explanation. Designed for the
low-latency path (score-transaction API); batch_scorer.py handles throughput.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session

from app.ml.explainability.shap_explainer import ExplainabilityEngine
from app.ml.features.engineer import compute_transaction_features
from app.ml.registry.model_registry import ModelNotFoundError, ModelRegistry
from app.models.customer import Customer
from app.models.ml_score import MLScore
from app.models.transaction import Transaction

# Weighted blend: rules-informed proxy score (risk_scorer), supervised
# anomaly probability, and unsupervised outlier signal.
COMBINE_WEIGHTS = {"risk_scorer": 0.5, "anomaly_classifier": 0.35, "isolation_detector": 0.15}
ANOMALY_PROBABILITY_THRESHOLD = 0.5
HIGH_RISK_THRESHOLD = 71


class ScoringUnavailableError(RuntimeError):
    """Raised when no trained model exists yet — caller should return a
    clear 'train the models first' response rather than a 500."""


def isolation_to_0_100(raw_score: float) -> float:
    # sklearn's IsolationForest.decision_function centers around 0 for
    # normal points; our anomaly_score() negates it so higher = more
    # anomalous. Map that unbounded value onto a 0-100 scale.
    return max(0.0, min(100.0, 50.0 + raw_score * 50.0))


class RealTimeScorer:
    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or ModelRegistry()

    def _load(self, name: str) -> tuple[dict, int, bool]:
        version, is_candidate = self.registry.resolve_serving_version(name)
        return self.registry.load_model(name, version), version, is_candidate

    def score_transaction(self, db: Session, txn: Transaction, customer: Customer, persist: bool = True) -> dict:
        try:
            risk_artifact, risk_version, risk_candidate = self._load("risk_scorer")
            anomaly_artifact, anomaly_version, anomaly_candidate = self._load("anomaly_classifier")
            iso_artifact, iso_version, iso_candidate = self._load("isolation_detector")
        except ModelNotFoundError as exc:
            raise ScoringUnavailableError(str(exc)) from exc

        features = compute_transaction_features(db, txn, customer)
        X = pd.DataFrame([features])

        risk_scorer = risk_artifact["model"]
        anomaly_classifier = anomaly_artifact["model"]
        isolation_detector = iso_artifact["model"]

        rf_risk_score = float(risk_scorer.predict(X)[0])
        anomaly_probability = float(anomaly_classifier.predict_proba(X)[0])
        isolation_score = isolation_to_0_100(float(isolation_detector.anomaly_score(X)[0]))

        combined_score = max(
            0.0,
            min(
                100.0,
                COMBINE_WEIGHTS["risk_scorer"] * rf_risk_score
                + COMBINE_WEIGHTS["anomaly_classifier"] * (anomaly_probability * 100)
                + COMBINE_WEIGHTS["isolation_detector"] * isolation_score,
            ),
        )
        anomaly_flag = anomaly_probability > ANOMALY_PROBABILITY_THRESHOLD or combined_score >= HIGH_RISK_THRESHOLD

        explainer = ExplainabilityEngine(risk_scorer, list(X.columns))
        explanation = explainer.explain(features)

        is_candidate = risk_candidate or anomaly_candidate or iso_candidate
        result = {
            "risk_score": round(combined_score, 2),
            "rf_risk_score": round(rf_risk_score, 2),
            "anomaly_probability": round(anomaly_probability, 4),
            "isolation_score": round(isolation_score, 2),
            "anomaly_flag": anomaly_flag,
            "explanation": explanation,
            "model_versions": {
                "risk_scorer": risk_version,
                "anomaly_classifier": anomaly_version,
                "isolation_detector": iso_version,
            },
            "is_candidate": is_candidate,
        }

        if persist:
            ml_score = MLScore(
                transaction_id=txn.id,
                risk_scorer_version=risk_version,
                anomaly_classifier_version=anomaly_version,
                isolation_detector_version=iso_version,
                is_candidate=is_candidate,
                rf_risk_score=rf_risk_score,
                anomaly_probability=anomaly_probability,
                isolation_score=isolation_score,
                combined_score=combined_score,
                anomaly_flag=anomaly_flag,
                explanation=explanation,
                features=features,
            )
            db.add(ml_score)
            db.flush()
            result["ml_score_id"] = str(ml_score.id)

        return result
