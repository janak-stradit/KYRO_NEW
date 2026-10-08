"""
services/screening_service.py — fuzzy name matching of customers against
ingested WatchlistEntity rows, and the PEPSanctionsScreening records that
result (Phase 4.1: real, ongoing sanctions screening).

Screening is intentionally conservative about auto-flagging: only a
near-exact match (high name-similarity score, boosted further by a DOB
match) auto-sets Customer.sanctions_flag. Weaker matches are recorded as
POTENTIAL_MATCH and left for an analyst to resolve via the existing
/customers/{id}/screening review queue — they never flip the flag on their
own.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone

from rapidfuzz import fuzz
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.beneficial_ownership import BeneficialOwner
from app.models.customer import Customer, PEPSanctionsScreening
from app.models.watchlist import WatchlistEntity

settings = get_settings()

_DOB_MATCH_BOOST = 8.0
_CANDIDATE_LIMIT = 25
_TRIGRAM_SIMILARITY_FLOOR = 0.25


def normalize_name(name: str) -> str:
    """Uppercase, strip diacritics/punctuation, collapse whitespace — the
    canonical form both customer names and watchlist entries are compared
    in, and what the trigram index on normalized_name is built over."""
    stripped = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    stripped = stripped.replace("'", "")  # O'Brien -> OBrien, not "O BRIEN"
    stripped = re.sub(r"[^A-Za-z0-9 ]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip().upper()


@dataclass
class MatchResult:
    entity: WatchlistEntity
    score: float
    matched_name: str
    dob_match: bool


def score_match(customer_name: str, customer_dob: date | None, entity: WatchlistEntity) -> MatchResult:
    normalized_customer = normalize_name(customer_name)
    candidates = [entity.primary_name, *(entity.aka_names or [])]

    best_name = entity.primary_name
    best_score = 0.0
    for candidate in candidates:
        candidate_score = fuzz.WRatio(normalized_customer, normalize_name(candidate))
        if candidate_score > best_score:
            best_score = candidate_score
            best_name = candidate

    dob_match = bool(customer_dob and entity.date_of_birth and customer_dob == entity.date_of_birth)
    score = min(100.0, best_score + (_DOB_MATCH_BOOST if dob_match else 0.0))
    return MatchResult(entity=entity, score=score, matched_name=best_name, dob_match=dob_match)


def _candidate_entities(db: Session, normalized_name: str) -> list[WatchlistEntity]:
    if not normalized_name:
        return []
    # set_limit() scopes the % operator's similarity floor to this session,
    # rather than depending on Postgres's (possibly reconfigured) default
    # pg_trgm.similarity_threshold GUC.
    db.execute(text("SELECT set_limit(CAST(:floor AS real))"), {"floor": _TRIGRAM_SIMILARITY_FLOOR})
    ids = db.execute(
        text(
            """
            SELECT id FROM app.watchlist_entities
            WHERE is_active = true AND normalized_name % :q
            ORDER BY similarity(normalized_name, :q) DESC
            LIMIT :limit
            """
        ),
        {"q": normalized_name, "limit": _CANDIDATE_LIMIT},
    ).scalars().all()
    if not ids:
        return []
    rows = db.query(WatchlistEntity).filter(WatchlistEntity.id.in_(ids)).all()
    by_id = {row.id: row for row in rows}
    return [by_id[i] for i in ids if i in by_id]


def _matches_for(db: Session, name: str, dob: date | None) -> list[MatchResult]:
    candidates = _candidate_entities(db, normalize_name(name))
    if not candidates:
        return []
    results = [score_match(name, dob, entity) for entity in candidates]
    results = [r for r in results if r.score >= settings.watchlist_potential_match_score]
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def _match_details(result: MatchResult) -> dict:
    return {
        "matched_name": result.matched_name,
        "entity_primary_name": result.entity.primary_name,
        "source_id": str(result.entity.source_id),
        "external_id": result.entity.external_id,
        "programs": result.entity.programs,
        "dob_match": result.dob_match,
    }


def screen_customer(db: Session, customer: Customer, *, triggered_by: str = "SYSTEM") -> list[PEPSanctionsScreening]:
    """Screen one customer against active watchlist entities. Writes a
    PEPSanctionsScreening row only when a candidate scores at or above the
    potential-match floor; always stamps last_screened_at so screening
    coverage/staleness can be reported on regardless of outcome."""
    customer.last_screened_at = datetime.now(timezone.utc)

    results = _matches_for(db, customer.full_name, customer.date_of_birth)
    if not results:
        db.flush()
        return []

    created: list[PEPSanctionsScreening] = []
    for result in results:
        is_confirmed = result.score >= settings.watchlist_confirmed_match_score
        screening = PEPSanctionsScreening(
            customer_id=customer.id,
            watchlist_entity_id=result.entity.id,
            match_score=round(result.score, 2),
            screening_type="SANCTIONS",
            match_status="CONFIRMED_MATCH" if is_confirmed else "POTENTIAL_MATCH",
            match_details=_match_details(result),
            screened_by=triggered_by,
        )
        db.add(screening)
        created.append(screening)

        if is_confirmed:
            customer.sanctions_flag = True

    db.flush()
    return created


def screen_beneficial_owner(
    db: Session, owner: BeneficialOwner, *, triggered_by: str = "SYSTEM"
) -> list[PEPSanctionsScreening]:
    """Screen one UBO against active watchlist entities. A confirmed match
    taints the owning corporate customer too — a sanctioned beneficial owner
    is a direct sanctions exposure for the entity they own/control, not just
    a data point on the owner record."""
    now = datetime.now(timezone.utc)
    owner.last_screened_at = now

    results = _matches_for(db, owner.full_name, owner.date_of_birth)
    if not results:
        db.flush()
        return []

    customer = db.get(Customer, owner.customer_id)

    created: list[PEPSanctionsScreening] = []
    for result in results:
        is_confirmed = result.score >= settings.watchlist_confirmed_match_score
        screening = PEPSanctionsScreening(
            customer_id=owner.customer_id,
            beneficial_owner_id=owner.id,
            watchlist_entity_id=result.entity.id,
            match_score=round(result.score, 2),
            screening_type="SANCTIONS",
            match_status="CONFIRMED_MATCH" if is_confirmed else "POTENTIAL_MATCH",
            match_details=_match_details(result),
            screened_by=triggered_by,
        )
        db.add(screening)
        created.append(screening)

        if is_confirmed:
            owner.sanctions_flag = True
            if customer is not None:
                customer.sanctions_flag = True

    db.flush()
    return created
