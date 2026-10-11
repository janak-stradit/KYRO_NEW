"""
services/obligation_service.py — Builds and maintains the obligations
register (Phase 11.3 step 4).

The AI proposes obligations from a section's text; nothing is CONFIRMED until
a compliance officer reviews it. Re-running extraction for a section replaces
its open proposals and leaves reviewed obligations alone.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ai import AIGateway
from app.ai.retrieval import chunk_text
from app.models.ai_interaction import AIInteraction
from app.models.obligation import OBLIGATION_CATEGORIES, Obligation
from app.models.regulatory import RegulatorySection
from app.services.audit_service import log_action

_EXTRACT_CHUNK_CHARS = 6000


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _clean(value: Any, limit: int | None = None) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value or value.lower() in ("null", "none", "n/a"):
        return None
    return value[:limit] if limit else value


def extract_for_section(
    db: Session, section: RegulatorySection, *, requested_by: uuid.UUID | None = None
) -> list[Obligation]:
    """Propose obligations for one section. Raises AIDisabledError / AIProviderError."""
    gateway = AIGateway(db)
    section_text = _normalise(section.content)
    reviewed_quotes = {
        _normalise(o.source_quote or "")
        for o in db.query(Obligation).filter(
            Obligation.section_id == section.id, Obligation.status.in_(("CONFIRMED", "REJECTED"))
        )
    }
    db.query(Obligation).filter(Obligation.section_id == section.id, Obligation.status == "PROPOSED").delete(
        synchronize_session=False
    )

    created: list[Obligation] = []
    seen_quotes: set[str] = set()
    for chunk in chunk_text(section.content, max_chars=_EXTRACT_CHUNK_CHARS, overlap=0):
        result = gateway.run(
            "regulatory.extract_obligations",
            {"section_ref": section.section_ref, "heading": section.heading or "", "text": chunk},
            entity_type="REGULATORY_SECTION",
            entity_id=section.id,
            requested_by=requested_by,
        )
        for item in (result.data or {}).get("obligations") or []:
            if not isinstance(item, dict):
                continue
            action = _clean(item.get("action"))
            if not action:
                continue
            quote = _clean(item.get("source_quote"))
            key = _normalise(quote or action)
            if key in seen_quotes or key in reviewed_quotes:
                continue  # already proposed in this run, or already decided by a reviewer
            seen_quotes.add(key)

            category = str(item.get("category") or "").upper()
            obligation = Obligation(
                section_id=section.id,
                section_ref=section.section_ref,
                section_version=section.version,
                obligated_party=_clean(item.get("obligated_party"), 255) or "Not stated",
                action=action,
                deadline=_clean(item.get("deadline"), 255),
                condition=_clean(item.get("condition")),
                category=category if category in OBLIGATION_CATEGORIES else "OTHER",
                source_quote=quote,
                # A quote that is not in the section is the model's wording, not the regulation's
                quote_verified=bool(quote) and _normalise(quote) in section_text,
                extracted_by=result.provider,
                ai_interaction_id=result.interaction_id,
            )
            db.add(obligation)
            created.append(obligation)

    db.commit()
    return created


def extract_for_source(
    db: Session, source_id: uuid.UUID, *, requested_by: uuid.UUID | None = None, only_missing: bool = True
) -> dict[str, int]:
    """Propose obligations for every current section of a source."""
    sections = (
        db.query(RegulatorySection)
        .filter(RegulatorySection.source_id == source_id, RegulatorySection.is_current.is_(True))
        .order_by(RegulatorySection.section_ref)
        .all()
    )
    done = {row[0] for row in db.query(Obligation.section_id).distinct()} if only_missing else set()
    processed = proposed = 0
    for section in sections:
        if section.id in done:
            continue
        proposed += len(extract_for_section(db, section, requested_by=requested_by))
        processed += 1
    return {"sections_processed": processed, "sections_skipped": len(sections) - processed, "obligations_proposed": proposed}


def review(
    db: Session,
    obligation: Obligation,
    *,
    decision: str,
    reviewer_id: uuid.UUID,
    edits: dict[str, Any] | None = None,
    notes: str | None = None,
) -> Obligation:
    """Record a reviewer's CONFIRMED / REJECTED decision, with optional edits."""
    edits = {k: v for k, v in (edits or {}).items() if v is not None}
    old = {k: getattr(obligation, k) for k in edits}
    for field, value in edits.items():
        setattr(obligation, field, value)

    obligation.status = decision
    obligation.reviewed_by = reviewer_id
    obligation.reviewed_at = datetime.now(timezone.utc)
    obligation.review_notes = notes

    # The same decision goes on the AI call that produced the proposal
    if obligation.ai_interaction_id:
        interaction = db.get(AIInteraction, obligation.ai_interaction_id)
        if interaction is not None and interaction.human_decision is None:
            interaction.human_decision = "REJECTED" if decision == "REJECTED" else ("EDITED" if edits else "ACCEPTED")
            interaction.decided_by = reviewer_id
            interaction.decided_at = obligation.reviewed_at

    log_action(
        db,
        entity_type="OBLIGATION",
        entity_id=obligation.id,
        action="APPROVE" if decision == "CONFIRMED" else "REJECT",
        performed_by=reviewer_id,
        old_values=old or None,
        new_values={"status": decision, "notes": notes, **edits},
    )
    db.commit()
    db.refresh(obligation)
    return obligation
