"""
ml/explainability/shap_explainer.py — SHAP-based explanation for the Risk
Scorer's prediction, translated into an analyst-readable summary.
"""
from __future__ import annotations

import pandas as pd
import shap

_DESCRIPTIONS = {
    "amount": "Transaction amount is {dir}",
    "rolling_avg_7d": "7-day average amount is {dir}",
    "txn_count_24h": "Transaction frequency in the last 24h is {dir}",
    "geo_diversity_score": "Geographic diversity is {dir}",
    "new_counterparty_flag": "Counterparty is new to this customer",
    "high_risk_country_flag": "Transaction involves a high-risk jurisdiction",
    "amount_zscore": "Amount deviates {mag} from the global baseline",
    "pattern_break_score": "Behavior deviates {mag} from this customer's own baseline",
    "pep_flag": "Customer is a Politically Exposed Person",
    "sanctions_flag": "Customer matched on a sanctions list",
}


def _describe(feature: str, value: float) -> str:
    template = _DESCRIPTIONS.get(feature)
    if template is None:
        return f"Feature '{feature}' contributes to the risk assessment"
    if "{dir}" in template:
        return template.format(dir="unusually high" if value > 0 else "within normal range")
    if "{mag}" in template:
        return template.format(mag="significantly" if abs(value) > 2 else "moderately")
    return template


def _summarize(top: list[tuple[str, float]]) -> str:
    increasing = [f for f in top if f[1] > 0]
    if not increasing:
        return "No significant risk factors identified."
    return "; ".join(_describe(name, value) for name, value in increasing[:3])


class ExplainabilityEngine:
    """Explains a RiskScorerModel's (RandomForestRegressor) prediction.
    TreeExplainer is exact and fast for tree ensembles — no sampling needed.
    """

    def __init__(self, risk_scorer_model, feature_names: list[str], top_k: int = 5) -> None:
        self._scaler = risk_scorer_model.scaler
        self.explainer = shap.TreeExplainer(risk_scorer_model.model)
        self.feature_names = feature_names
        self.top_k = top_k

    def explain(self, features: dict[str, float]) -> dict:
        X = pd.DataFrame([features])[self.feature_names]
        X_scaled = self._scaler.transform(X)
        shap_values = self.explainer.shap_values(X_scaled)
        row = shap_values[0]

        pairs = sorted(zip(self.feature_names, row), key=lambda p: abs(p[1]), reverse=True)
        top = pairs[: self.top_k]

        expected = self.explainer.expected_value
        base_value = float(expected[0] if hasattr(expected, "__len__") else expected)
        prediction = base_value + float(sum(v for _, v in pairs))

        return {
            "top_features": [
                {
                    "feature": name,
                    "impact": round(float(value), 4),
                    "direction": "INCREASES_RISK" if value > 0 else "DECREASES_RISK",
                    "description": _describe(name, value),
                }
                for name, value in top
            ],
            "base_value": round(base_value, 2),
            "prediction": round(prediction, 2),
            "summary": _summarize(top),
        }
