"""
services/mapping_service.py — Obligation → control mapping, coverage gaps and
the traceability matrix (Phase 11.4).

Only CONFIRMED obligations are mapped, and only CONFIRMED mappings count as
coverage. A confirmed obligation with no confirmed mapping is a gap.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ai import AIGateway
from app.models.obligation import Obligation
from app.models.obligation_mapping import ObligationMapping
from app.models.rule_config import GLOBAL_JURISDICTION, RuleConfig
from app.services import feedback_service
from app.services.audit_service import log_action
from app.services.control_catalogue import CONTROLS, CONTROLS_BY_CODE, catalogue_text


def propose_for_obligation(
    db: Session, obligation: Obligation, *, requested_by: uuid.UUID | None = None
) -> list[ObligationMapping]:
    """Ask the AI which controls meet one obligation. Reviewed mappings are left alone."""
    existing = {m.control_code: m for m in db.query(ObligationMapping).filter_by(obligation_id=obligation.id)}
    result = AIGateway(db).run(
        "regulatory.map_obligation",
        {
            "section_ref": obligation.section_ref,
            "obligated_party": obligation.obligated_party,
            "action": obligation.action,
            "category": obligation.category,
            "deadline": obligation.deadline or "none stated",
            "catalogue": catalogue_text(),
        },
        entity_type="OBLIGATION",
        entity_id=obligation.id,
        requested_by=requested_by,
    )

    created: list[ObligationMapping] = []
    for item in (result.data or {}).get("mappings") or []:
        code = str(item.get("control_code") or "").strip().upper() if isinstance(item, dict) else ""
        if code not in CONTROLS_BY_CODE or code in existing:
            continue  # not a real control, or already proposed / decided
        mapping = ObligationMapping(
            obligation_id=obligation.id,
            control_code=code,
            rationale=str(item.get("rationale") or "").strip() or None,
            proposed_by=result.provider,
            ai_interaction_id=result.interaction_id,
        )
        db.add(mapping)
        existing[code] = mapping
        created.append(mapping)
    db.commit()
    return created


def propose_for_unmapped(db: Session, *, requested_by: uuid.UUID | None = None) -> dict[str, int]:
    """Propose mappings for every confirmed obligation that has none yet."""
    mapped = {row[0] for row in db.query(ObligationMapping.obligation_id).distinct()}
    obligations = db.query(Obligation).filter(Obligation.status == "CONFIRMED").order_by(Obligation.section_ref).all()
    processed = proposed = 0
    for obligation in obligations:
        if obligation.id in mapped:
            continue
        proposed += len(propose_for_obligation(db, obligation, requested_by=requested_by))
        processed += 1
    return {"obligations_processed": processed, "mappings_proposed": proposed}


def add_manual(db: Session, obligation: Obligation, *, control_code: str, rationale: str | None, user_id: uuid.UUID) -> ObligationMapping:
    """A reviewer maps a control directly; it is confirmed straight away."""
    mapping = db.query(ObligationMapping).filter_by(obligation_id=obligation.id, control_code=control_code).first()
    if mapping is None:
        mapping = ObligationMapping(obligation_id=obligation.id, control_code=control_code, proposed_by="user")
        db.add(mapping)
        db.flush()
    if rationale:
        mapping.rationale = rationale
    return review(db, mapping, decision="CONFIRMED", reviewer_id=user_id)


def review(db: Session, mapping: ObligationMapping, *, decision: str, reviewer_id: uuid.UUID) -> ObligationMapping:
    mapping.status = decision
    mapping.reviewed_by = reviewer_id
    mapping.reviewed_at = datetime.now(timezone.utc)
    log_action(
        db,
        entity_type="OBLIGATION_MAPPING",
        entity_id=mapping.id,
        action="APPROVE" if decision == "CONFIRMED" else "REJECT",
        performed_by=reviewer_id,
        new_values={"obligation_id": str(mapping.obligation_id), "control_code": mapping.control_code, "status": decision},
    )
    db.commit()
    db.refresh(mapping)
    return mapping


def traceability(db: Session, *, days: int = 90) -> dict[str, Any]:
    """
    Regulation version → obligation → control → live rule config → alerts.
    One row per (confirmed obligation, mapping); a confirmed obligation with
    no open or confirmed mapping appears once as a GAP row.
    """
    obligations = db.query(Obligation).filter(Obligation.status == "CONFIRMED").order_by(Obligation.section_ref, Obligation.created_at).all()
    mappings: dict[uuid.UUID, list[ObligationMapping]] = {}
    for m in db.query(ObligationMapping).filter(ObligationMapping.status != "REJECTED").order_by(ObligationMapping.control_code):
        mappings.setdefault(m.obligation_id, []).append(m)

    config = {
        r.key: r.value.get("value") if isinstance(r.value, dict) else r.value
        for r in db.query(RuleConfig).filter(RuleConfig.jurisdiction == GLOBAL_JURISDICTION, RuleConfig.is_active.is_(True))
    }
    alerts = {row["rule"]: row for row in feedback_service.disposition_baseline(db, days=days)["by_rule"]}

    rows: list[dict[str, Any]] = []
    covered = pending = gaps = 0
    confirmed_controls: set[str] = set()
    for o in obligations:
        base = {
            "obligation_id": str(o.id),
            "section_ref": o.section_ref,
            "section_version": o.section_version,
            "obligated_party": o.obligated_party,
            "action": o.action,
            "deadline": o.deadline,
            "category": o.category,
        }
        own = mappings.get(o.id, [])
        if any(m.status == "CONFIRMED" for m in own):
            covered += 1
        elif own:
            pending += 1
        else:
            gaps += 1
            rows.append({**base, "mapping_id": None, "mapping_status": "GAP", "control_code": None, "control_name": None,
                         "control_kind": None, "rationale": None, "rule_config": {}, "alerts": None, "false_positive_rate": None})
        for m in own:
            control = CONTROLS_BY_CODE.get(m.control_code)
            if m.status == "CONFIRMED":
                confirmed_controls.add(m.control_code)
            stats = alerts.get(m.control_code) if control and control.kind == "RULE" else None
            rows.append({
                **base,
                "mapping_id": str(m.id),
                "mapping_status": m.status,
                "control_code": m.control_code,
                "control_name": control.name if control else m.control_code,
                "control_kind": control.kind if control else None,
                "rationale": m.rationale,
                "rule_config": {k: config.get(k) for k in (control.config_keys if control else ())},
                "alerts": stats["alerts"] if stats else (0 if control and control.kind == "RULE" else None),
                "false_positive_rate": stats["false_positive_rate"] if stats else None,
            })

    return {
        "window_days": days,
        "summary": {
            "confirmed_obligations": len(obligations),
            "covered": covered,
            "awaiting_mapping_review": pending,
            "gaps": gaps,
            # Rules that enforce nothing traceable: either internal policy or a missing obligation
            "rules_without_obligation": [c.code for c in CONTROLS if c.kind == "RULE" and c.code not in confirmed_controls],
        },
        "rows": rows,
    }
