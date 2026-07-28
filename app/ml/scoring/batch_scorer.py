"""
ml/scoring/batch_scorer.py — Vectorized batch scoring: build the whole
feature matrix once, then call each model's predict on the batch instead of
row-by-row, for real throughput. No per-row SHAP explanation (too slow at
batch scale) — use real_time_scorer for that on individual transactions.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session

from app.ml.features.engineer import compute_transaction_features
from app.ml.registry.model_registry import ModelNotFoundError, ModelRegistry
from app.ml.scoring.real_time_scorer import (
    ANOMALY_PROBABILITY_THRESHOLD,
    COMBINE_WEIGHTS,
    HIGH_RISK_THRESHOLD,
    ScoringUnavailableError,
    isolation_to_0_100,
)
from app.models.customer import Customer
from app.models.ml_score import MLScore
from app.models.transaction import Transaction


def score_batch(db: Session, transactions: list[Transaction], persist: bool = True) -> list[dict]:
    if not transactions:
        return []

    registry = ModelRegistry()
    try:
        risk_version, _ = registry.resolve_serving_version("risk_scorer")
        risk_artifact = registry.load_model("risk_scorer", risk_version)
        anomaly_version, _ = registry.resolve_serving_version("anomaly_classifier")
        anomaly_artifact = registry.load_model("anomaly_classifier", anomaly_version)
        iso_version, _ = registry.resolve_serving_version("isolation_detector")
        iso_artifact = registry.load_model("isolation_detector", iso_version)
    except ModelNotFoundError as exc:
        raise ScoringUnavailableError(str(exc)) from exc

    customer_cache: dict = {}
    feature_rows: list[dict] = []
    for txn in transactions:
        customer = customer_cache.get(txn.customer_id)
        if customer is None:
            customer = db.get(Customer, txn.customer_id)
            customer_cache[txn.customer_id] = customer
        feature_rows.append(compute_transaction_features(db, txn, customer))
    X = pd.DataFrame(feature_rows)

    risk_scores = risk_artifact["model"].predict(X)
    anomaly_probs = anomaly_artifact["model"].predict_proba(X)
    isolation_raw = iso_artifact["model"].anomaly_score(X)

    results: list[dict] = []
    for i, txn in enumerate(transactions):
        isolation_score = isolation_to_0_100(float(isolation_raw[i]))
        combined = max(
            0.0,
            min(
                100.0,
                COMBINE_WEIGHTS["risk_scorer"] * float(risk_scores[i])
                + COMBINE_WEIGHTS["anomaly_classifier"] * (float(anomaly_probs[i]) * 100)
                + COMBINE_WEIGHTS["isolation_detector"] * isolation_score,
            ),
        )
        anomaly_flag = bool(anomaly_probs[i] > ANOMALY_PROBABILITY_THRESHOLD or combined >= HIGH_RISK_THRESHOLD)

        results.append({"transaction_id": str(txn.id), "risk_score": round(combined, 2), "anomaly_flag": anomaly_flag})

        if persist:
            db.add(
                MLScore(
                    transaction_id=txn.id,
                    risk_scorer_version=risk_version,
                    anomaly_classifier_version=anomaly_version,
                    isolation_detector_version=iso_version,
                    rf_risk_score=float(risk_scores[i]),
                    anomaly_probability=float(anomaly_probs[i]),
                    isolation_score=isolation_score,
                    combined_score=combined,
                    anomaly_flag=anomaly_flag,
                    features=feature_rows[i],
                )
            )

    if persist:
        db.flush()
    return results
