"""
routers/case_file.py — What an investigator needs around one case: notes and
the case timeline, the customer's earlier cases, and the customer's recent
activity against their own baseline.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_permission
from app.models.alert import Alert
from app.models.alert_note import AlertNote
from app.models.audit import AuditLog
from app.models.customer import Customer
from app.models.document import Document
from app.models.user import User
from app.services import pattern_service

router = APIRouter(prefix="/api/v1", tags=["case-file"], dependencies=[Depends(require_permission("cases.view"))])

HISTORY_LIMIT = 8


class NoteIn(BaseModel):
    body: str = Field(max_length=4000)

    @field_validator("body")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Write the note before saving it")
        return value


def _alert_or_404(db: Session, alert_id: uuid.UUID) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    return alert


def _rules(alert: Alert) -> list[str]:
    triggered = alert.triggered_rules
    return list(triggered.get("rules") or []) if isinstance(triggered, dict) else []


def _human(code: str | None) -> str:
    return (code or "").replace("_", " ").capitalize()


def _audit_event(row: AuditLog, names: dict[uuid.UUID, str]) -> tuple[str, str, str | None]:
    """(kind, title, detail) for one audit entry on an alert."""
    values = row.new_values or {}
    if "assigned_to" in values:
        try:
            assignee = names.get(uuid.UUID(str(values["assigned_to"])))
        except ValueError:
            assignee = None
        return "assigned", f"Assigned to {assignee or 'a user'}", None
    if "qa_result" in values:
        passed = values["qa_result"] == "PASS"
        return "qa", f"Quality check {'passed' if passed else 'failed'}", values.get("qa_notes")
    if "resolution_outcome" in values:
        reasons = ", ".join(_human(r) for r in values.get("resolution_reasons") or [])
        title = f"Resolved: {_human(values['resolution_outcome'])}" + (f" ({reasons})" if reasons else "")
        return "resolved", title, values.get("resolution_notes")
    if values.get("status") == "ESCALATED":
        reasons = ", ".join(_human(r) for r in values.get("resolution_reasons") or [])
        return "escalated", "Escalated" + (f" ({reasons})" if reasons else ""), None
    return "updated", "Updated", None


# ── Notes and timeline ───────────────────────────────────────────────────

@router.get("/alerts/{alert_id}/timeline")
def case_timeline(alert_id: uuid.UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Everything that has happened on the case, newest first: notes, decisions and documents."""
    alert = _alert_or_404(db, alert_id)
    notes = db.query(AlertNote).filter(AlertNote.alert_id == alert.id).all()
    audits = db.query(AuditLog).filter(AuditLog.entity_type == "ALERT", AuditLog.entity_id == alert.id).all()
    documents = db.query(Document).filter(Document.alert_id == alert.id).all()

    user_ids: set[uuid.UUID] = {n.author_id for n in notes} | {a.performed_by for a in audits} | {d.uploaded_by for d in documents}
    for audit in audits:
        assigned = (audit.new_values or {}).get("assigned_to")
        if assigned:
            try:
                user_ids.add(uuid.UUID(str(assigned)))
            except ValueError:
                pass
    user_ids.discard(None)
    names = {u.id: u.full_name or u.username for u in db.query(User).filter(User.id.in_(user_ids))} if user_ids else {}
    who = lambda user_id: names.get(user_id) or ("System" if user_id is None else "Unknown user")

    events: list[dict[str, Any]] = [{
        "kind": "created", "at": alert.created_at, "by": "System", "title": "Alert created",
        "detail": f"Risk score {alert.risk_score}" + (f"; rules {', '.join(_rules(alert))}" if _rules(alert) else ""),
    }]
    events += [{"kind": "note", "id": str(n.id), "at": n.created_at, "by": who(n.author_id), "title": "Note", "detail": n.body} for n in notes]
    for audit in audits:
        kind, title, detail = _audit_event(audit, names)
        events.append({"kind": kind, "at": audit.performed_at, "by": who(audit.performed_by), "title": title, "detail": detail})
    events += [{
        "kind": "document", "at": d.uploaded_at, "by": who(d.uploaded_by), "title": f"Document uploaded: {d.filename}",
        "detail": _human(d.doc_type),
    } for d in documents]

    events.sort(key=lambda e: e["at"], reverse=True)
    return {"alert_id": str(alert.id), "note_count": len(notes), "events": [{**e, "at": e["at"].isoformat()} for e in events]}


@router.post("/alerts/{alert_id}/notes", status_code=status.HTTP_201_CREATED)
def add_note(
    alert_id: uuid.UUID,
    data: NoteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("cases.view")),
) -> dict[str, Any]:
    """Add an investigation note. Notes cannot be edited or removed afterwards."""
    alert = _alert_or_404(db, alert_id)
    note = AlertNote(alert_id=alert.id, author_id=user.id, body=data.body)
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"id": str(note.id), "at": note.created_at.isoformat(), "by": user.full_name or user.username, "detail": note.body}


# ── The customer's earlier cases ─────────────────────────────────────────

@router.get("/customers/{customer_id}/case-history")
def case_history(customer_id: uuid.UUID, alert_id: uuid.UUID | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    How this customer's earlier alerts ended. With `alert_id`, also says how
    earlier alerts on the same rules ended, leaving that alert itself out.
    """
    if db.get(Customer, customer_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    alerts = db.query(Alert).filter(Alert.customer_id == customer_id, Alert.id != alert_id).order_by(Alert.created_at.desc()).all()
    resolved = [a for a in alerts if a.status == "RESOLVED"]

    outcomes: dict[str, int] = {}
    for a in resolved:
        key = a.resolution_outcome or "NOT_RECORDED"
        outcomes[key] = outcomes.get(key, 0) + 1

    same_rules = []
    current = db.get(Alert, alert_id) if alert_id else None
    if current is not None and current.customer_id == customer_id:
        for rule in _rules(current):
            earlier = [a for a in resolved if rule in _rules(a)]
            same_rules.append({
                "rule": rule,
                "resolved": len(earlier),
                "false_positive": sum(1 for a in earlier if a.resolution_outcome == "FALSE_POSITIVE"),
                "sar_filed": sum(1 for a in earlier if a.resolution_outcome == "SAR_FILED"),
            })

    resolved.sort(key=lambda a: a.resolved_at or a.created_at, reverse=True)
    return {
        "total": len(alerts),
        "open": len(alerts) - len(resolved),
        "resolved": len(resolved),
        "outcomes": outcomes,
        "same_rules": same_rules,
        "recent": [
            {
                "id": str(a.id), "created_at": a.created_at.isoformat(),
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                "risk_score": a.risk_score, "rules": _rules(a), "outcome": a.resolution_outcome,
                "reasons": a.resolution_reasons or [], "sar_reference": a.sar_reference,
            }
            for a in resolved[:HISTORY_LIMIT]
        ],
    }


# ── Activity against the customer's own baseline ─────────────────────────

@router.get("/customers/{customer_id}/activity")
def customer_activity(customer_id: uuid.UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    """The last 30 days of transactions beside the customer's previous 90, and what changed."""
    if db.get(Customer, customer_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return pattern_service.customer_activity(db, customer_id)
