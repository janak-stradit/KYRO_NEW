"""
ml/models/risk_scorer.py — Random Forest regressor predicting a continuous
0-100 risk score per transaction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler


class RiskScorerModel:
    def __init__(self) -> None:
        self.model = RandomForestRegressor(
            n_estimators=200,
            max_depth=15,
            min_samples_split=10,
            min_samples_leaf=5,
            max_features="sqrt",
            bootstrap=True,
            random_state=42,
            n_jobs=-1,
        )
        self.scaler = StandardScaler()
        self.feature_names: list[str] | None = None

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.feature_names = list(X.columns)
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X_scaled = self.scaler.transform(X[self.feature_names])
        scores = self.model.predict(X_scaled)
        return np.clip(scores, 0, 100)

    def feature_importance(self) -> dict[str, float]:
        if self.feature_names is None:
            return {}
        return dict(zip(self.feature_names, self.model.feature_importances_))
