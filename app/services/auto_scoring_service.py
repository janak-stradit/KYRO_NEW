"""
services/auto_scoring_service.py — Scores every newly ingested transaction
with the ML models (risk scorer, anomaly classifier, isolation detector),
straight after the rules engine has run.

The result is kept as an ml_scores row. If the rules engine opened an alert
for the transaction, the model's explanation is added to that alert instead
of opening a second one; otherwise an alert is opened only when the models
flag the transaction as an anomaly.

Scoring never stops a transaction from being recorded: if the ML libraries
cannot be loaded, no model has been trained, or scoring fails, the
transaction keeps its rules-engine result and this returns None.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.alert import Alert
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.services.alert_service import ML_VERSION, AlertRouter

logger = logging.getLogger("kyro.auto_scoring")

MODEL_NAMES = ("risk_scorer", "anomaly_classifier", "isolation_detector")

_scoring_module: Any = None  # app.ml.scoring.real_time_scorer once imported; False if it cannot be


def _scoring() -> Any:
    """The scoring module, or None where the ML stack cannot be imported
    (e.g. scikit-learn blocked by Windows Smart App Control)."""
    global _scoring_module
    if _scoring_module is None:
        try:
            from app.ml.scoring import real_time_scorer

            _scoring_module = real_time_scorer
        except ImportError as exc:
            logger.warning("Transactions will not be ML-scored: the ML libraries failed to import: %s", exc)
            _scoring_module = False
    return _scoring_module or None


def unavailable_reason() -> str | None:
    """Why new transactions are not being ML-scored, or None if they are."""
    if not get_settings().ml_auto_score:
        return "it is turned off (ML_AUTO_SCORE)"
    if _scoring() is None:
        return "the ML libraries cannot be loaded on this machine"
    from app.ml.registry.model_registry import ModelRegistry

    registry = ModelRegistry()
    if not all(registry.list_versions(name) for name in MODEL_NAMES):
        return "the models have not been trained yet"
    return None


def score_ingested(db: Session, txn: Transaction, customer: Customer, rules_alert: Alert | None) -> dict | None:
    """Score a transaction that has just been through the rules engine. The caller commits."""
    if not get_settings().ml_auto_score:
        return None
    scoring = _scoring()
    if scoring is None:
        return None
    try:
        # A savepoint, so a failed score cannot undo the transaction itself
        with db.begin_nested():
            result = scoring.RealTimeScorer().score_transaction(db, txn, customer)
            if rules_alert is not None:
                rules_alert.ml_explanation = result["explanation"]
                rules_alert.ml_version = ML_VERSION
            elif result["anomaly_flag"]:
                alert = AlertRouter().route(
                    db,
                    customer=customer,
                    risk_score=result["risk_score"],
                    confidence=result["anomaly_probability"],
                    explanation=result["explanation"],
                )
                if alert is not None:
                    # A new alert can change the customer's rating
                    from app.services import customer_risk_service  # imported here to avoid an import cycle

                    customer_risk_service.assess_customer(db, customer)
                    result["alert_id"] = str(alert.id)
            db.flush()
        return result
    except scoring.ScoringUnavailableError:
        return None  # no trained model yet
    except Exception:
        logger.exception("ML scoring failed for transaction %s; it keeps its rules-engine result", txn.id)
        return None
