"""
services/customer_risk_service.py — Rule-based customer risk rating.

A customer's rating is the sum of the weights of the risk factors that apply
(capped at 100), mapped to LOW / MEDIUM / HIGH with the same cut-offs used for
alert routing. Every factor that contributed is stored in
`customer_risk_profiles`, so the rating can always be explained.

The weights below are a starting policy for compliance to review, not a
regulatory standard.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.customer import Customer, CustomerRiskProfile
from app.services.alert_service import LOW_MAX, MEDIUM_MAX
from app.services.audit_service import log_action

# (category, description, weight)
SANCTIONS = ("SCREENING", "Sanctions list match", 80)
PEP = ("SCREENING", "Politically exposed person", 40)
ADVERSE_MEDIA = ("SCREENING", "Adverse media", 25)
HIGH_RISK_COUNTRY = ("GEOGRAPHIC", "Country or residency in a high-risk jurisdiction", 25)
SAR_FILED = ("BEHAVIORAL", "SAR filed in the last 12 months", 50)
OPEN_ALERT_HIGH = ("BEHAVIORAL", "Unresolved alert with a risk score of 80 or more", 35)
OPEN_ALERT_MEDIUM = ("BEHAVIORAL", "Unresolved alert with a risk score of 60 to 79", 20)
OPEN_ALERT_LOW = ("BEHAVIORAL", "Unresolved alert", 10)
ALERT_VOLUME = ("BEHAVIORAL", "Ten or more unresolved alerts", 10)

_SYSTEM = "SYSTEM"


def _level(score: int) -> str:
    return "LOW" if score <= LOW_MAX else "MEDIUM" if score <= MEDIUM_MAX else "HIGH"


def _alert_stats(db: Session, customer_ids: list[uuid.UUID] | None = None) -> dict[uuid.UUID, dict[str, Any]]:
    """Unresolved-alert count and top score, and recent SAR filings, per customer."""
    stats: dict[uuid.UUID, dict[str, Any]] = {}
    open_query = db.query(Alert.customer_id, func.count(Alert.id), func.max(Alert.risk_score)).filter(
        Alert.status != "RESOLVED"
    )
    sar_query = db.query(Alert.customer_id).filter(
        Alert.resolution_outcome == "SAR_FILED",
        Alert.resolved_at >= datetime.now(timezone.utc) - timedelta(days=365),
    )
    if customer_ids is not None:
        open_query = open_query.filter(Alert.customer_id.in_(customer_ids))
        sar_query = sar_query.filter(Alert.customer_id.in_(customer_ids))
    for customer_id, count, top in open_query.group_by(Alert.customer_id):
        stats[customer_id] = {"open": count, "top": top or 0, "sar": False}
    for (customer_id,) in sar_query.distinct():
        stats.setdefault(customer_id, {"open": 0, "top": 0, "sar": False})["sar"] = True
    return stats


def _factors(customer: Customer, stats: dict[str, Any], high_risk_countries: set[str]) -> list[tuple[str, str, int]]:
    factors = []
    if customer.sanctions_flag:
        factors.append(SANCTIONS)
    if customer.pep_flag:
        factors.append(PEP)
    if customer.adverse_media_flag:
        factors.append(ADVERSE_MEDIA)
    countries = {str(c).strip().upper() for c in (customer.country, customer.residency_country) if c}
    if countries & high_risk_countries:
        factors.append(HIGH_RISK_COUNTRY)
    if stats.get("sar"):
        factors.append(SAR_FILED)
    if stats.get("open"):
        top = stats["top"]
        factors.append(OPEN_ALERT_HIGH if top >= 80 else OPEN_ALERT_MEDIUM if top >= 60 else OPEN_ALERT_LOW)
        if stats["open"] >= 10:
            factors.append(ALERT_VOLUME)
    return factors


def _apply(
    db: Session, customer: Customer, stats: dict[str, Any], high_risk_countries: set[str], performed_by: uuid.UUID | None
) -> dict[str, Any]:
    factors = _factors(customer, stats, high_risk_countries)
    score = min(100, sum(weight for _, _, weight in factors))
    level = _level(score)
    old = {"risk_score": customer.risk_score, "risk_level": customer.risk_level}
    changed = (score, level) != (customer.risk_score, customer.risk_level)

    # The stored factors always describe the current rating
    db.query(CustomerRiskProfile).filter(
        CustomerRiskProfile.customer_id == customer.id, CustomerRiskProfile.assessed_by == _SYSTEM
    ).delete(synchronize_session=False)
    db.add_all(
        CustomerRiskProfile(
            customer_id=customer.id, risk_category=category, risk_factor=description, risk_weight=weight, assessed_by=_SYSTEM
        )
        for category, description, weight in factors
    )

    if changed:
        customer.risk_score = score
        customer.risk_level = level
        log_action(
            db,
            entity_type="CUSTOMER",
            entity_id=customer.id,
            action="UPDATE",
            performed_by=performed_by,
            old_values=old,
            new_values={"risk_score": score, "risk_level": level, "factors": [d for _, d, _ in factors]},
        )
    return {
        "customer_id": customer.id,
        "risk_score": score,
        "risk_level": level,
        "changed": changed,
        "previous_risk_level": old["risk_level"],
        "factors": [{"category": c, "factor": d, "weight": w} for c, d, w in factors],
    }


def _high_risk_countries(db: Session, customer: Customer | None = None) -> set[str]:
    from app.services.rules_engine import HIGH_RISK_COUNTRIES, resolve_config  # avoids an import cycle

    if customer is None:
        return {c.upper() for c in HIGH_RISK_COUNTRIES}
    return {str(c).upper() for c in resolve_config(db, customer)["HIGH_RISK_COUNTRIES"]}


def assess_customer(db: Session, customer: Customer, *, performed_by: uuid.UUID | None = None) -> dict[str, Any]:
    """Recalculate one customer's rating. The caller commits."""
    db.flush()  # count alerts created earlier in this transaction
    stats = _alert_stats(db, [customer.id]).get(customer.id, {})
    result = _apply(db, customer, stats, _high_risk_countries(db, customer), performed_by)
    db.flush()
    return result


def assess_all(db: Session, *, performed_by: uuid.UUID | None = None) -> dict[str, Any]:
    """Recalculate every customer's rating. The caller commits."""
    stats = _alert_stats(db)
    countries = _high_risk_countries(db)
    levels = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    changed = 0
    customers = db.query(Customer).all()
    for customer in customers:
        result = _apply(db, customer, stats.get(customer.id, {}), countries, performed_by)
        levels[result["risk_level"]] += 1
        changed += result["changed"]
    db.flush()
    return {"customers": len(customers), "changed": changed, "by_level": levels}
