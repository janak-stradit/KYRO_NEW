"""
services/case_stage.py — Where each case stands, for lists: opened, assigned,
under investigation, (escalated), decided, quality-checked.

The case page builds the same path from the full timeline (routers/case_file.py:
_case_stages); here it is worked out for a page of alerts at once, with one query
per source, so the work queue can show every case's path under its row.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.alert_note import AlertNote
from app.models.alert_request import AlertRequest
from app.models.audit import AuditLog
from app.models.document import Document

STATUS_LABELS = {
    "OPEN": "Open", "ASSIGNED": "Assigned", "IN_REVIEW": "In review", "ESCALATED": "With the MLRO", "RESOLVED": "Closed",
}


def _first_by_alert(db: Session, alert_column, created, ids) -> dict[uuid.UUID, Any]:
    return dict(db.query(alert_column, func.min(created)).filter(alert_column.in_(ids)).group_by(alert_column).all())


def stage_paths(db: Session, alerts: list[Alert]) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """For each alert: [{key, label, state, at}] where state is done, current, todo or skipped."""
    ids = [a.id for a in alerts]
    if not ids:
        return {}
    worked: dict[uuid.UUID, Any] = {}
    for model, created in ((AlertNote, AlertNote.created_at), (AlertRequest, AlertRequest.created_at), (Document, Document.uploaded_at)):
        for alert_id, at in _first_by_alert(db, model.alert_id, created, ids).items():
            worked[alert_id] = min(worked[alert_id], at) if alert_id in worked else at
    escalated = dict(
        db.query(AuditLog.entity_id, func.min(AuditLog.performed_at))
        .filter(AuditLog.entity_type == "ALERT", AuditLog.entity_id.in_(ids), AuditLog.new_values["status"].astext == "ESCALATED")
        .group_by(AuditLog.entity_id).all()
    )

    paths: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for alert in alerts:
        resolved = alert.status == "RESOLVED"
        escalated_at = escalated.get(alert.id) or (alert.created_at if alert.status == "ESCALATED" else None)
        stages = [
            ("opened", "Opened", alert.created_at),
            ("assigned", "Assigned", alert.created_at if alert.assigned_to else None),
            ("investigation", "Investigation", worked.get(alert.id) or escalated_at),
        ]
        if escalated_at:
            stages.append(("escalated", "With the MLRO", escalated_at))
        stages.append(("decision", "Decision", alert.resolved_at if resolved else None))
        stages.append(("quality", "Quality check", alert.qa_at if alert.qa_result else None))

        path, current_found = [], False
        for key, label, at in stages:
            if at is not None:
                state = "done"
            elif resolved and key in ("assigned", "investigation"):
                state = "skipped"  # decided straight from the queue
            elif not current_found:
                state, current_found = "current", True
            else:
                state = "todo"
            path.append({"key": key, "label": label, "state": state, "at": at.isoformat() if at else None})
        paths[alert.id] = path
    return paths


# What the current stage means for the case, in words
WAITING_FOR = {
    "assigned": "Waiting for an owner", "investigation": "Under investigation", "escalated": "With the MLRO",
    "decision": "Awaiting decision", "quality": "Awaiting quality check",
}


def current_label(path: list[dict[str, Any]]) -> str:
    current = next((s for s in path if s["state"] == "current"), None)
    return WAITING_FOR.get(current["key"], current["label"]) if current else "Complete"
