"""
services/alert_service.py — Routes an ML score to a log-only outcome or a
persisted Alert, per Phase 2's LOW/MEDIUM/HIGH thresholds.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.customer import Customer

LOW_MAX = 30
MEDIUM_MAX = 70
ML_VERSION = "phase2-v1"

_FEATURE_TO_ALERT_TYPE = {
    "pep_flag": "PEP",
    "sanctions_flag": "SANCTIONS",
    "high_risk_country_flag": "GEOGRAPHY",
    "counterparty_country_risk": "GEOGRAPHY",
    "destination_country_risk": "GEOGRAPHY",
    "origin_country_risk": "GEOGRAPHY",
    "geo_diversity_score": "GEOGRAPHY",
    "new_counterparty_flag": "COUNTERPARTY",
    "unique_counterparties_7d": "COUNTERPARTY",
    "unique_counterparties_30d": "COUNTERPARTY",
    "txn_count_1h": "VELOCITY",
    "txn_count_24h": "VELOCITY",
    "txn_count_7d": "VELOCITY",
    "amount": "AMOUNT",
    "amount_zscore": "AMOUNT",
    "amount_percentile_customer": "AMOUNT",
    "amount_percentile_global": "AMOUNT",
    "pattern_break_score": "BEHAVIORAL_ANOMALY",
    "hour_deviation": "BEHAVIORAL_ANOMALY",
    "geo_deviation": "BEHAVIORAL_ANOMALY",
    "deviation_from_avg_amount": "BEHAVIORAL_ANOMALY",
    "deviation_from_avg_frequency": "BEHAVIORAL_ANOMALY",
}


def _infer_alert_type(explanation: dict) -> str:
    for feature in explanation.get("top_features", []):
        alert_type = _FEATURE_TO_ALERT_TYPE.get(feature["feature"])
        if alert_type:
            return alert_type
    return "BEHAVIORAL_ANOMALY"


class AlertRouter:
    def route(
        self,
        db: Session,
        *,
        customer: Customer,
        risk_score: float,
        confidence: float,
        explanation: dict,
    ) -> Alert | None:
        if risk_score <= LOW_MAX:
            return None  # log-only; the ml_scores row already records this

        action = "BATCH_REVIEW" if risk_score <= MEDIUM_MAX else "IMMEDIATE_REVIEW"
        confidence_pct = round(confidence * 100, 2) if confidence <= 1 else round(confidence, 2)

        alert = Alert(
            customer_id=customer.id,
            alert_type=_infer_alert_type(explanation),
            risk_score=round(risk_score),
            confidence=confidence_pct,
            ml_explanation=explanation,
            recommended_action=action,
            status="OPEN",
            ml_version=ML_VERSION,
        )
        db.add(alert)
        db.flush()
        return alert
