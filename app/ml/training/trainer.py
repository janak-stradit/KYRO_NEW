"""
ml/training/trainer.py — Pulls transactions, engineers features, builds proxy
labels, and trains all three models.

Labels are a documented simplification: there is no ground-truth fraud
dataset yet, so:
  - risk_scorer target = Transaction.risk_score (0-100), the Phase 1
    deterministic rules-engine score — the RF regressor learns to
    approximate/generalize that score from engineered features.
  - anomaly_classifier target = 1 if risk_score >= ALERT_THRESHOLD (i.e. an
    alert would have been opened), else 0.
Once real analyst feedback accumulates (Alert.is_false_positive), the
retraining service should swap these for actual outcome labels.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, precision_score, r2_score, recall_score
from sklearn.model_selection import train_test_split
from sqlalchemy.orm import Session

from app.ml.features.engineer import compute_transaction_features
from app.ml.models.anomaly_classifier import AnomalyClassifier
from app.ml.models.isolation_detector import UnsupervisedAnomalyDetector
from app.ml.models.risk_scorer import RiskScorerModel
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.services.rules_engine import ALERT_THRESHOLD

MIN_TRAINING_ROWS = 50


@dataclass
class TrainingResult:
    risk_scorer: RiskScorerModel
    anomaly_classifier: AnomalyClassifier
    isolation_detector: UnsupervisedAnomalyDetector
    metrics: dict
    row_count: int


def build_training_frame(db: Session, limit: int | None = None) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    query = db.query(Transaction).order_by(Transaction.transaction_date.asc())
    if limit:
        query = query.limit(limit)
    transactions = query.all()

    customer_cache: dict = {}
    rows: list[dict] = []
    y_risk: list[float] = []
    y_anomaly: list[int] = []

    for txn in transactions:
        customer = customer_cache.get(txn.customer_id)
        if customer is None:
            customer = db.get(Customer, txn.customer_id)
            customer_cache[txn.customer_id] = customer
        if customer is None:
            continue
        rows.append(compute_transaction_features(db, txn, customer))
        y_risk.append(float(txn.risk_score))
        y_anomaly.append(1 if txn.risk_score >= ALERT_THRESHOLD else 0)

    return pd.DataFrame(rows), pd.Series(y_risk, name="risk_score"), pd.Series(y_anomaly, name="is_anomaly")


def train_all(db: Session, limit: int | None = None) -> TrainingResult:
    X, y_risk, y_anomaly = build_training_frame(db, limit=limit)
    if len(X) < MIN_TRAINING_ROWS:
        raise ValueError(f"Not enough transactions to train on: {len(X)} < {MIN_TRAINING_ROWS}")

    X_train, X_test, y_risk_train, y_risk_test, y_anom_train, y_anom_test = train_test_split(
        X, y_risk, y_anomaly, test_size=0.2, random_state=42
    )

    risk_scorer = RiskScorerModel()
    risk_scorer.train(X_train, y_risk_train)
    risk_pred = risk_scorer.predict(X_test)

    anomaly_classifier = AnomalyClassifier()
    anomaly_classifier.train(X_train, y_anom_train)
    anomaly_pred = anomaly_classifier.predict(X_test)

    isolation_detector = UnsupervisedAnomalyDetector()
    isolation_detector.train(X_train)

    metrics = {
        "row_count": len(X),
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "risk_scorer_r2": float(r2_score(y_risk_test, risk_pred)),
        "risk_scorer_mae": float(mean_absolute_error(y_risk_test, risk_pred)),
        "anomaly_precision": float(precision_score(y_anom_test, anomaly_pred, zero_division=0)),
        "anomaly_recall": float(recall_score(y_anom_test, anomaly_pred, zero_division=0)),
        "anomaly_positive_rate": float(np.mean(y_anomaly)) if len(y_anomaly) else 0.0,
    }

    return TrainingResult(
        risk_scorer=risk_scorer,
        anomaly_classifier=anomaly_classifier,
        isolation_detector=isolation_detector,
        metrics=metrics,
        row_count=len(X),
    )
