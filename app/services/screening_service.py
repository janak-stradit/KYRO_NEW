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

Names are compared after transliteration (Cyrillic, Arabic, Greek, Chinese
... to Latin letters) and after mapping common spelling variants of the same
name to one form. Candidates are found by the primary name, by any alias and
by how the name sounds (metaphone codes). A name whose every part sounds the
same as the listed name but is spelt differently scores SCREENING_PHONETIC_SCORE,
which is kept below the confirmed score: sound alone never confirms a match.
Thresholds come from screening_policy.py.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone

import jellyfish
from anyascii import anyascii
from rapidfuzz import fuzz
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.beneficial_ownership import BeneficialOwner
from app.models.customer import Customer, PEPSanctionsScreening
from app.models.watchlist import WatchlistEntity
from app.services import screening_policy

_DOB_MATCH_BOOST = 8.0
_CANDIDATE_LIMIT = 25
_TRIGRAM_SIMILARITY_FLOOR = 0.25
_NAME_PART_FLOOR = 88.0    # two name parts count as the same person's name above this
_EXTRA_PART_SCORE = 88.0   # every part of the shorter name found, plus one extra part (e.g. a middle name)
_NAME_PART_MINIMUM = 60.0  # below this a name part has no counterpart in the other name
_NOT_A_MATCH_CEILING = 70.0  # the most a name with an unmatched part can score (under the review floor)
_WORD_SIMILARITY_FLOOR = 0.6  # alias and phonetic candidate search (pg_trgm word similarity)
_DEFAULT_PHONETIC_SCORE = 85.0

# Spellings of the same name, mapped to one form before comparing. Transliteration and
# phonetic codes catch most variants; this covers the frequent ones they do not.
_VARIANTS: dict[str, str] = {
    variant: canonical
    for canonical, variants in {
        "MUHAMMAD": ("MOHAMMED", "MOHAMED", "MOHAMMAD", "MOHAMAD", "MUHAMMED", "MUHAMED", "MUHAMAD", "MOHAMMET", "MEHMET", "MEHMED"),
        "YUSUF": ("YOUSEF", "YOUSSEF", "YOUSUF", "YUSEF", "JOSEF", "YOSEF"),
        "HUSSEIN": ("HUSSAIN", "HUSAIN", "HUSEIN", "HOSSEIN", "HOSEIN"),
        "ABDUL": ("ABDEL", "ABD AL", "ABDOUL", "ABDUL"),
        "ALEKSANDR": ("ALEXANDER", "ALEXANDR", "ALEKSANDER", "OLEKSANDR"),
        "SERGEI": ("SERGEY", "SERGIY", "SERHIY"),
        "YURI": ("YURIY", "IURII", "YURIJ", "JURIJ"),
    }.items()
    for variant in (canonical, *variants)
}


def normalize_name(name: str) -> str:
    """Uppercase, strip diacritics/punctuation, collapse whitespace — the
    canonical form both customer names and watchlist entries are compared
    in, and what the trigram index on normalized_name is built over."""
    stripped = anyascii(unicodedata.normalize("NFKC", name or ""))  # other scripts to Latin letters
    stripped = unicodedata.normalize("NFKD", stripped).encode("ascii", "ignore").decode("ascii")
    stripped = stripped.replace("'", "")  # O'Brien -> OBrien, not "O BRIEN"
    stripped = re.sub(r"[^A-Za-z0-9 ]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip().upper()


def _canonical_parts(normalized: str) -> list[str]:
    return [_VARIANTS.get(part, part) for part in normalized.split()]


def _sound(part: str) -> str | None:
    """Metaphone code of one name part; initials and very short parts have none."""
    return jellyfish.metaphone(part) or None if len(part) >= 3 else None


def phonetic_key(name: str) -> str:
    """How a whole name sounds, independent of word order: sorted metaphone codes of its parts."""
    return " ".join(sorted(code for code in (_sound(p) for p in _canonical_parts(normalize_name(name))) if code))


def name_score(a: str, b: str, phonetic_score: float = _DEFAULT_PHONETIC_SCORE) -> float:
    """
    How alike two names are as whole names, 0-100, ignoring word order.

    Deliberately not a substring match: "Jordan Mcdaniel" is not a match for a
    list entry called "DANIEL", and sharing only a given name or only a
    surname is not a match. Every part of the shorter name has to have a
    counterpart in the other. A name that differs only by one extra part
    ("John Smith" / "John Michael Smith") still scores as a possible match.
    """
    a_parts, b_parts = _canonical_parts(normalize_name(a)), _canonical_parts(normalize_name(b))
    if not a_parts or not b_parts:
        return 0.0
    a, b = " ".join(a_parts), " ".join(b_parts)
    score = float(max(fuzz.ratio(a, b), fuzz.token_sort_ratio(a, b)))

    def alike(part: str, other: str) -> float:
        """Spelling similarity, or the phonetic score when two parts sound the same."""
        spelt = float(fuzz.ratio(part, other))
        sound = _sound(part)
        return max(spelt, phonetic_score) if phonetic_score and sound and sound == _sound(other) else spelt

    # Pair each part of the shorter name with its closest unused part of the longer one
    short, long_ = sorted((a_parts, b_parts), key=len)
    remaining = list(long_)
    weakest = 100.0
    for part in short:
        best = max(remaining, key=lambda other: alike(part, other))
        weakest = min(weakest, alike(part, best))
        remaining.remove(best)

    if weakest < _NAME_PART_MINIMUM or (len(short) == 1 and remaining):
        # A part with no counterpart, or a one-word name against a longer one: not the same name
        return min(score, _NOT_A_MATCH_CEILING)
    if len(short) >= 2 and len(remaining) == 1 and weakest >= _NAME_PART_FLOOR:
        score = max(score, _EXTRA_PART_SCORE)
    if phonetic_score and not remaining and weakest >= min(phonetic_score, _NAME_PART_FLOOR):
        # Every part has a counterpart that is spelt alike or sounds the same
        score = max(score, min(phonetic_score, weakest))
    return score


def search_columns(primary_name: str, aka_names: list[str] | None) -> dict[str, str | None]:
    """What a watchlist entry is searched by besides its primary name (WatchlistEntity.alias_text / phonetic_text)."""
    aliases = [a for a in (aka_names or []) if a and normalize_name(a)]
    return {
        "alias_text": " | ".join(normalize_name(a) for a in aliases) or None,
        "phonetic_text": " | ".join(k for k in (phonetic_key(n) for n in [primary_name, *aliases]) if k) or None,
    }


@dataclass
class MatchResult:
    entity: WatchlistEntity
    score: float
    matched_name: str
    dob_match: bool


def score_match(
    customer_name: str, customer_dob: date | None, entity: WatchlistEntity, phonetic_score: float = _DEFAULT_PHONETIC_SCORE,
) -> MatchResult:
    normalized_customer = normalize_name(customer_name)
    candidates = [entity.primary_name, *(entity.aka_names or [])]

    best_name = entity.primary_name
    best_score = 0.0
    for candidate in candidates:
        candidate_score = name_score(normalized_customer, candidate, phonetic_score)
        if candidate_score > best_score:
            best_score = candidate_score
            best_name = candidate

    dob_match = bool(customer_dob and entity.date_of_birth and customer_dob == entity.date_of_birth)
    score = min(100.0, best_score + (_DOB_MATCH_BOOST if dob_match else 0.0))
    return MatchResult(entity=entity, score=score, matched_name=best_name, dob_match=dob_match)


def _candidate_entities(db: Session, name: str) -> list[WatchlistEntity]:
    """Active list entries whose primary name looks alike, whose aliases contain a similar name, or whose names sound alike."""
    normalized_name = normalize_name(name)
    if not normalized_name:
        return []
    # set_limit() / set_config() scope the trigram floors to this session, rather than depending
    # on Postgres's (possibly reconfigured) default pg_trgm thresholds.
    db.execute(text("SELECT set_limit(CAST(:floor AS real))"), {"floor": _TRIGRAM_SIMILARITY_FLOOR})
    db.execute(text("SELECT set_config('pg_trgm.word_similarity_threshold', :floor, false)"),
               {"floor": str(_WORD_SIMILARITY_FLOOR)})
    ids = db.execute(
        text(
            # Three index-friendly searches joined, rather than one OR that the planner cannot index
            """
            WITH hits AS (
                SELECT id, similarity(normalized_name, :q) AS s FROM app.watchlist_entities
                WHERE is_active = true AND normalized_name % :q
                UNION ALL
                SELECT id, word_similarity(:q, alias_text) FROM app.watchlist_entities
                WHERE is_active = true AND :q <% alias_text
                UNION ALL
                SELECT id, word_similarity(:pk, phonetic_text) FROM app.watchlist_entities
                WHERE is_active = true AND :pk <> '' AND :pk <% phonetic_text
            )
            SELECT id FROM hits GROUP BY id ORDER BY max(s) DESC LIMIT :limit
            """
        ),
        {"q": normalized_name, "pk": phonetic_key(name), "limit": _CANDIDATE_LIMIT},
    ).scalars().all()
    if not ids:
        return []
    rows = db.query(WatchlistEntity).filter(WatchlistEntity.id.in_(ids)).all()
    by_id = {row.id: row for row in rows}
    return [by_id[i] for i in ids if i in by_id]


def _matches_for(db: Session, name: str, dob: date | None, rules: dict[str, float]) -> list[MatchResult]:
    candidates = _candidate_entities(db, name)
    if not candidates:
        return []
    results = [score_match(name, dob, entity, rules["phonetic"]) for entity in candidates]
    results = [r for r in results if r.score >= rules["potential"]]
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

    rules = screening_policy.policy(db, customer)
    results = _matches_for(db, customer.full_name, customer.date_of_birth, rules)
    if not results:
        db.flush()
        return []

    created: list[PEPSanctionsScreening] = []
    for result in results:
        is_confirmed = result.score >= rules["confirmed"]
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

    customer = db.get(Customer, owner.customer_id)
    rules = screening_policy.policy(db, customer)
    results = _matches_for(db, owner.full_name, owner.date_of_birth, rules)
    if not results:
        db.flush()
        return []

    created: list[PEPSanctionsScreening] = []
    for result in results:
        is_confirmed = result.score >= rules["confirmed"]
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
