"""
ml/models/anomaly_classifier.py — Random Forest classifier: is this
transaction anomalous (binary), trained against a labeled proxy target.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler


class AnomalyClassifier:
    def __init__(self) -> None:
        self.model = RandomForestClassifier(
            n_estimators=200,
            max_depth=12,
            min_samples_split=20,
            class_weight="balanced",
            random_state=42,
        )
        self.scaler = StandardScaler()
        self.feature_names: list[str] | None = None

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.feature_names = list(X.columns)
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X_scaled = self.scaler.transform(X[self.feature_names])
        return self.model.predict(X_scaled)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        X_scaled = self.scaler.transform(X[self.feature_names])
        return self.model.predict_proba(X_scaled)[:, 1]
