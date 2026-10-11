"""
services/deadline_service.py — Case and filing deadlines.

Three clocks, each set when it starts so a later policy change does not move
a deadline already running:

  case SLA          from the alert's creation, days by risk band (CASE_SLA_DAYS)
  potential SAR     from the moment a case is escalated as a potential SAR,
                    days to the MLRO's decision (SAR_DECISION_DAYS)
  SAR filing        from the date of initial detection (SAR_FILING_DAYS);
                    null means the jurisdiction sets no fixed number of days

The values are policy, not code: they are rule configs (GLOBAL or per
jurisdiction) changed through the maker-checker flow in change_service.py.
The defaults below are proposals that Compliance must confirm.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.alert import Alert
from app.models.customer import Customer
from app.services import rule_config_service

UNRESOLVED = ("OPEN", "ASSIGNED", "IN_REVIEW", "ESCALATED")
BANDS = ("HIGH", "MEDIUM", "LOW")


def _settings_sla() -> dict[str, int]:
    settings = get_settings()
    return {"HIGH": settings.case_target_days_high, "MEDIUM": settings.case_target_days_medium, "LOW": settings.case_target_days_low}


def defaults() -> dict[str, Any]:
    return {
        "CASE_SLA_DAYS": _settings_sla(),
        "SAR_DECISION_DAYS": 5,
        "SAR_FILING_DAYS": 30,
        "DEADLINE_WARNING_PERCENT": 75,
    }


def validate(key: str, value: Any) -> str | None:
    """Why `value` is not acceptable for `key`, or None when it is."""
    def whole_days(v: Any) -> bool:
        return isinstance(v, int) and not isinstance(v, bool) and 0 < v <= 365

    if key == "CASE_SLA_DAYS":
        if not isinstance(value, dict) or set(value) != set(BANDS) or not all(whole_days(v) for v in value.values()):
            return "CASE_SLA_DAYS must be an object with HIGH, MEDIUM and LOW whole days (1-365)"
    elif key == "SAR_DECISION_DAYS":
        if not whole_days(value):
            return "SAR_DECISION_DAYS must be whole days (1-365)"
    elif key == "SAR_FILING_DAYS":
        if value is not None and not whole_days(value):
            return "SAR_FILING_DAYS must be whole days (1-365), or null where no fixed deadline applies"
    elif key == "DEADLINE_WARNING_PERCENT":
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 99:
            return "DEADLINE_WARNING_PERCENT must be a whole number from 1 to 99"
    return None


def policy(db: Session, customer: Customer | None = None) -> dict[str, Any]:
    jurisdiction = (customer.residency_country or customer.country) if customer is not None else None
    return rule_config_service.get_effective_config(db, defaults(), jurisdiction)


def band(risk_score: int) -> str:
    return "HIGH" if risk_score >= 80 else "MEDIUM" if risk_score >= 60 else "LOW"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Starting clocks ──────────────────────────────────────────────────────

def start_case_clock(db: Session, alert: Alert, customer: Customer) -> None:
    """Called when an alert is created."""
    alert.detected_at = alert.detected_at or alert.created_at or _now()
    alert.sla_days = int(policy(db, customer)["CASE_SLA_DAYS"][band(alert.risk_score)])


def mark_potential_sar(db: Session, alert: Alert, customer: Customer | None) -> None:
    """Called when a case is escalated as a potential SAR; starts the decision and filing clocks once."""
    if alert.sar_candidate_at is not None:
        return
    rules = policy(db, customer)
    alert.sar_candidate_at = _now()
    alert.sar_decision_days = int(rules["SAR_DECISION_DAYS"])
    filing_days = rules["SAR_FILING_DAYS"]
    detected = alert.detected_at or alert.created_at
    alert.filing_due_at = detected + timedelta(days=int(filing_days)) if filing_days is not None else None


# ── Reading clocks ───────────────────────────────────────────────────────

def target_days(alert: Alert) -> int:
    return alert.sla_days or _settings_sla()[band(alert.risk_score)]


def _status(start: datetime, days: int, end: datetime | None, warning_percent: int) -> str:
    """ON_TRACK / DUE_SOON / OVERDUE while running; MET / MISSED once stopped. Overdue after `days` full days."""
    elapsed = ((end or _now()) - start).days
    if end is not None:
        return "MISSED" if elapsed > days else "MET"
    if elapsed > days:
        return "OVERDUE"
    return "DUE_SOON" if elapsed >= days * warning_percent / 100 else "ON_TRACK"


def is_overdue(alert: Alert) -> bool:
    if alert.status not in UNRESOLVED:
        return False
    now = _now()
    if (now - alert.created_at).days > target_days(alert):
        return True
    return alert.sar_candidate_at is not None and (now - alert.sar_candidate_at).days > (alert.sar_decision_days or 0)


def overdue_condition():
    """SQL version of is_overdue, for queue filters and counts."""
    now = _now()
    defaults_by_band = _settings_sla()  # for alerts created before clocks were stored
    sla_breached = or_(*(
        and_(
            Alert.risk_score >= low, Alert.risk_score < high,
            Alert.created_at < now - func.make_interval(0, 0, 0, func.coalesce(Alert.sla_days, defaults_by_band[name]) + 1),
        )
        for name, (low, high) in (("HIGH", (80, 1_000)), ("MEDIUM", (60, 80)), ("LOW", (-1_000, 60)))
    ))
    decision_breached = and_(
        Alert.sar_candidate_at.isnot(None),
        Alert.sar_candidate_at < now - func.make_interval(0, 0, 0, func.coalesce(Alert.sar_decision_days, 0) + 1),
    )
    return and_(Alert.status.in_(UNRESOLVED), or_(sla_breached, decision_breached))


def summary(db: Session, alert: Alert, customer: Customer | None, *, include_sar: bool) -> dict[str, Any]:
    """Every clock on one case. The SAR clocks are left out for roles that may not see SAR work."""
    warning = int(policy(db, customer)["DEADLINE_WARNING_PERCENT"])
    stopped = alert.resolved_at if alert.status not in UNRESOLVED else None
    days = target_days(alert)
    out: dict[str, Any] = {
        "case": {
            "started_at": alert.created_at.isoformat(), "target_days": days,
            "due_at": (alert.created_at + timedelta(days=days)).isoformat(),
            "status": _status(alert.created_at, days, stopped, warning),
        },
    }
    if include_sar:
        sar: dict[str, Any] = {"potential_sar": alert.sar_candidate_at is not None,
                               "detected_at": (alert.detected_at or alert.created_at).isoformat()}
        if alert.sar_candidate_at is not None:
            decided = alert.resolved_at if alert.status not in UNRESOLVED else None
            sar["decision"] = {
                "started_at": alert.sar_candidate_at.isoformat(), "target_days": alert.sar_decision_days,
                "due_at": (alert.sar_candidate_at + timedelta(days=alert.sar_decision_days or 0)).isoformat(),
                "status": _status(alert.sar_candidate_at, alert.sar_decision_days or 0, decided, warning),
            }
            filed = alert.resolved_at if alert.resolution_outcome == "SAR_FILED" else None
            if alert.filing_due_at is None:
                sar["filing"] = {"due_at": None, "status": "FILED" if filed else "NO_FIXED_DEADLINE"}
            else:
                late = (filed or _now()) > alert.filing_due_at
                sar["filing"] = {
                    "due_at": alert.filing_due_at.isoformat(),
                    "status": ("FILED_LATE" if late else "FILED") if filed else ("OVERDUE" if late else "OPEN"),
                }
        out["sar"] = sar
    return out
