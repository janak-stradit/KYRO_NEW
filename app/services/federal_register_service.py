"""
services/federal_register_service.py — Rules and proposed rules from the
Federal Register (https://www.federalregister.gov/developers/documentation/api/v1)
that amend a CFR part KYRO has loaded. Free, no key; public domain.

Only documents that cite a loaded part are fetched, so everything stored is
relevant by construction. No model is involved.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.regulatory import RegulatorySource
from app.models.regulatory_notice import RegulatoryNotice
from app.services.audit_service import log_action

API_URL = "https://www.federalregister.gov/api/v1/documents.json"
LOOKBACK_DAYS = 365
_FIELDS = (
    "document_number", "title", "type", "action", "abstract", "agencies",
    "publication_date", "effective_on", "comments_close_on", "html_url",
)


def loaded_parts(db: Session) -> list[tuple[int, str]]:
    """
    Distinct (title, part) pairs of the enabled sources that load a whole
    part. A source that loads a single section is skipped: the API can only
    filter by part, and a large part would bring in mostly unrelated notices.
    """
    parts = {
        (int(s.config["title"]), str(s.config["part"]))
        for s in db.query(RegulatorySource).filter(RegulatorySource.is_enabled.is_(True))
        if s.config.get("title") and s.config.get("part") and not s.config.get("section")
    }
    return sorted(parts)


def fetch_part(title: int, part: str, since: date) -> list[dict[str, Any]]:
    """Rules and proposed rules citing one CFR part, published on or after `since`."""
    params: list[tuple[str, str]] = [
        ("conditions[cfr][title]", str(title)),
        ("conditions[cfr][part]", part),
        ("conditions[type][]", "RULE"),
        ("conditions[type][]", "PRORULE"),
        ("conditions[publication_date][gte]", since.isoformat()),
        ("order", "newest"),
        ("per_page", "100"),
    ] + [("fields[]", f) for f in _FIELDS]
    with httpx.Client(timeout=get_settings().watchlist_http_timeout_seconds, follow_redirects=True) as client:
        response = client.get(API_URL, params=params)
        response.raise_for_status()
        return response.json().get("results") or []


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def sync(db: Session) -> dict[str, Any]:
    """Fetch notices for every loaded part and store the new ones. Existing notices keep their assessment."""
    since = date.today() - timedelta(days=LOOKBACK_DAYS)
    found: dict[str, dict[str, Any]] = {}
    failed: list[str] = []
    for title, part in loaded_parts(db):
        label = f"{title} CFR Part {part}"
        try:
            results = fetch_part(title, part, since)
        except (httpx.HTTPError, ValueError) as exc:
            failed.append(f"{label}: {type(exc).__name__}")
            continue
        for item in results:
            number = item.get("document_number")
            if not number or not _date(item.get("publication_date")):
                continue
            found.setdefault(number, {**item, "matched_parts": []})["matched_parts"].append(label)

    existing = {
        n.document_number: n
        for n in db.query(RegulatoryNotice).filter(RegulatoryNotice.document_number.in_(list(found)))
    } if found else {}
    added = 0
    for number, item in found.items():
        values = {
            "title": item.get("title") or number,
            "notice_type": item.get("type") or "Rule",
            "action": item.get("action"),
            "abstract": item.get("abstract"),
            "agencies": [a.get("name") or a.get("raw_name") for a in item.get("agencies") or [] if isinstance(a, dict)],
            "publication_date": _date(item["publication_date"]),
            "effective_on": _date(item.get("effective_on")),
            "comments_close_on": _date(item.get("comments_close_on")),
            "url": item.get("html_url") or "",
            "matched_parts": sorted(set(item["matched_parts"])),
        }
        notice = existing.get(number)
        if notice is None:
            db.add(RegulatoryNotice(document_number=number, **values))
            added += 1
        else:
            for key, value in values.items():  # dates and abstracts get corrected after publication
                setattr(notice, key, value)
    db.commit()
    return {"parts_checked": len(loaded_parts(db)), "notices_found": len(found), "notices_added": added, "failed": failed}


def assess(db: Session, notice: RegulatoryNotice, *, status: str, notes: str | None, user_id: uuid.UUID) -> RegulatoryNotice:
    old_status = notice.status
    notice.status = status
    notice.assessment_notes = notes
    notice.assessed_by = user_id
    notice.assessed_at = datetime.now(timezone.utc)
    log_action(
        db, entity_type="REGULATORY_CHANGE", entity_id=notice.id, action="REVIEW", performed_by=user_id,
        old_values={"status": old_status},
        new_values={"status": status, "notes": notes, "federal_register_document": notice.document_number},
    )
    db.commit()
    db.refresh(notice)
    return notice
