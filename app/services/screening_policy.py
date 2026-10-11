"""
services/screening_policy.py — Thresholds that decide what a watchlist match
means, edited as rule configs through the maker-checker flow (globally or per
jurisdiction), like deadline_service.py.

  SCREENING_CONFIRMED_SCORE   at or above: confirmed match, sanctions flag set
  SCREENING_POTENTIAL_SCORE   at or above: potential match, for an analyst
  SCREENING_PHONETIC_SCORE    score given when every part of the name sounds
                              the same but is spelt differently; 0 turns
                              phonetic matching off. Kept below the confirmed
                              score, so sound alone never confirms a match.
  SCREENING_IDENTIFIER_BOOST  added when a passport, national ID, tax,
                              registration or IMO number is the same on both
                              sides; such a match is never below the potential score
  SCREENING_IDENTIFIER_PENALTY  taken off when both sides hold the same kind
                              of number and the numbers differ
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.customer import Customer
from app.services import rule_config_service


def defaults() -> dict[str, Any]:
    settings = get_settings()
    return {
        "SCREENING_CONFIRMED_SCORE": settings.watchlist_confirmed_match_score,
        "SCREENING_POTENTIAL_SCORE": settings.watchlist_potential_match_score,
        "SCREENING_PHONETIC_SCORE": 85.0,
        "SCREENING_IDENTIFIER_BOOST": 15.0,
        "SCREENING_IDENTIFIER_PENALTY": 15.0,
    }


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate(key: str, value: Any) -> str | None:
    if key in ("SCREENING_CONFIRMED_SCORE", "SCREENING_POTENTIAL_SCORE") and not (_number(value) and 50 <= value <= 100):
        return f"{key} must be a score from 50 to 100"
    if key == "SCREENING_PHONETIC_SCORE" and not (_number(value) and (value == 0 or 50 <= value < 100)):
        return "SCREENING_PHONETIC_SCORE must be 0 (off) or a score from 50 to 99"
    if key in ("SCREENING_IDENTIFIER_BOOST", "SCREENING_IDENTIFIER_PENALTY") and not (_number(value) and 0 <= value <= 50):
        return f"{key} must be from 0 to 50"
    return None


def policy(db: Session, customer: Customer | None = None) -> dict[str, float]:
    jurisdiction = (customer.residency_country or customer.country) if customer is not None else None
    rules = rule_config_service.get_effective_config(db, defaults(), jurisdiction)
    confirmed = float(rules["SCREENING_CONFIRMED_SCORE"])
    potential = min(float(rules["SCREENING_POTENTIAL_SCORE"]), confirmed)
    phonetic = float(rules["SCREENING_PHONETIC_SCORE"])
    # Sound alone may raise a name to review, never to a confirmed match
    phonetic = min(phonetic, confirmed - 0.01) if phonetic else 0.0
    return {
        "confirmed": confirmed, "potential": potential, "phonetic": phonetic,
        "identifier_boost": float(rules["SCREENING_IDENTIFIER_BOOST"]),
        "identifier_penalty": float(rules["SCREENING_IDENTIFIER_PENALTY"]),
    }
