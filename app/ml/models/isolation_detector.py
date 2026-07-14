"""
ml/models/isolation_detector.py — Unsupervised anomaly detection (no labels
required); complements the supervised models for anomaly types not yet
represented in labeled/proxy training data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


class UnsupervisedAnomalyDetector:
    def __init__(self) -> None:
        self.model = IsolationForest(
            n_estimators=150,
            contamination=0.05,
            max_samples="auto",
            random_state=42,
            n_jobs=-1,
        )
        self.scaler = StandardScaler()
        self.feature_names: list[str] | None = None

    def train(self, X: pd.DataFrame) -> None:
        self.feature_names = list(X.columns)
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X_scaled = self.scaler.transform(X[self.feature_names])
        return self.model.predict(X_scaled)  # 1 = normal, -1 = anomaly

    def anomaly_score(self, X: pd.DataFrame) -> np.ndarray:
        """Higher = more anomalous (negated so it's intuitive; sklearn's raw
        decision_function is higher for normal points)."""
        X_scaled = self.scaler.transform(X[self.feature_names])
        return -self.model.decision_function(X_scaled)
