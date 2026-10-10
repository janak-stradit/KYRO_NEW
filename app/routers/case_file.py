"""
routers/case_file.py — What an investigator needs around one case: notes and
the case timeline, the customer's earlier cases, and the customer's recent
activity against their own baseline.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.ai import AIDisabledError, AIGateway, AIProviderError
from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user, require_permission
from app.models.account import Account
from app.models.alert import Alert
from app.models.alert_note import AlertNote
from app.models.alert_request import AlertRequest
from app.models.audit import AuditLog
from app.models.beneficial_ownership import BeneficialOwner
from app.models.customer import Customer, PEPSanctionsScreening
from app.models.document import Document
from app.models.obligation import Obligation
from app.models.obligation_mapping import ObligationMapping
from app.models.transaction import Transaction
from app.models.user import User
from app.models.watchlist import WatchlistEntity, WatchlistSource
from app.services import customer_risk_service, pattern_service, rule_config_service
from app.services.audit_service import log_action
from app.services.control_catalogue import CONTROLS
from app.visibility import alert_conditions, alert_visible, sees_sar, visible_alert_or_404, visible_customer_or_404

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


def _customer_or_404(db: Session, customer_id: uuid.UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return customer


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


def _case_stages(alert: Alert, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Where the case stands: opened, assigned, under investigation, (escalated),
    decided, quality-checked. A stage is done when the record shows it
    happened; the first one that has not is the current stage.
    """
    first = lambda *kinds: min((e["at"] for e in events if e["kind"] in kinds), default=None)
    last = lambda *kinds: max((e["at"] for e in events if e["kind"] in kinds), default=None)
    resolved = alert.status == "RESOLVED"
    escalated_at = first("escalated")
    worked_at = first("note", "request", "document")
    stages = [
        ("opened", "Opened", alert.created_at, f"Risk score {alert.risk_score}"),
        ("assigned", "Assigned", (last("assigned") or alert.created_at) if alert.assigned_to else None, None),
        ("investigation", "Investigation", worked_at or escalated_at, None),
    ]
    if escalated_at or alert.status == "ESCALATED":
        stages.append(("escalated", "Escalated to MLRO", escalated_at or alert.created_at, None))
    stages.append(("decision", "Decision", alert.resolved_at if resolved else None,
                   _human(alert.resolution_outcome) if resolved and alert.resolution_outcome else None))
    stages.append(("quality", "Quality check", alert.qa_at if alert.qa_result else None,
                   {"PASS": "Passed", "FAIL": "Failed"}.get(alert.qa_result or "")))

    out, current_found = [], False
    for key, label, at, detail in stages:
        done = at is not None
        # A case decided without being assigned or worked skipped those stages; they are not "current"
        skipped = not done and resolved and key in ("assigned", "investigation")
        current = not done and not skipped and not current_found
        current_found = current_found or current
        out.append({"key": key, "label": label, "done": done, "skipped": skipped, "current": current,
                    "at": at.isoformat() if at else None, "detail": detail if done else None})
    return out


# ── Notes and timeline ───────────────────────────────────────────────────

@router.get("/alerts/{alert_id}/timeline")
def case_timeline(alert_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Everything that has happened on the case, newest first: notes, decisions and documents."""
    alert = visible_alert_or_404(db, user, alert_id)
    notes = db.query(AlertNote).filter(AlertNote.alert_id == alert.id).all()
    audits = db.query(AuditLog).filter(AuditLog.entity_type == "ALERT", AuditLog.entity_id == alert.id).all()
    documents = db.query(Document).filter(Document.alert_id == alert.id).all()
    requests = db.query(AlertRequest).filter(AlertRequest.alert_id == alert.id).all()

    user_ids: set[uuid.UUID] = {n.author_id for n in notes} | {a.performed_by for a in audits} | {d.uploaded_by for d in documents}
    user_ids |= {r.requested_by for r in requests} | {r.closed_by for r in requests}
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

    for r in requests:
        events.append({"kind": "request", "at": r.created_at, "by": who(r.requested_by),
                       "title": f"Information requested from {r.requested_from}", "detail": f"{r.subject} (due {r.due_date:%d %b %Y})"})
        if r.closed_at:
            events.append({"kind": "request", "at": r.closed_at, "by": who(r.closed_by),
                           "title": "Information received" if r.status == "RECEIVED" else "Request withdrawn", "detail": r.response_note})

    events.sort(key=lambda e: e["at"], reverse=True)
    return {
        "alert_id": str(alert.id), "note_count": len(notes), "clock": _case_clock(alert, audits),
        "stages": _case_stages(alert, events),
        "events": [{**e, "at": e["at"].isoformat()} for e in events],
    }


@router.post("/alerts/{alert_id}/notes", status_code=status.HTTP_201_CREATED)
def add_note(
    alert_id: uuid.UUID,
    data: NoteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("cases.view")),
) -> dict[str, Any]:
    """Add an investigation note. Notes cannot be edited or removed afterwards."""
    alert = visible_alert_or_404(db, user, alert_id)
    note = AlertNote(alert_id=alert.id, author_id=user.id, body=data.body)
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"id": str(note.id), "at": note.created_at.isoformat(), "by": user.full_name or user.username, "detail": note.body}


# ── The customer's earlier cases ─────────────────────────────────────────

@router.get("/customers/{customer_id}/case-history")
def case_history(
    customer_id: uuid.UUID, alert_id: uuid.UUID | None = None, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    How this customer's earlier alerts ended. With `alert_id`, also says how
    earlier alerts on the same rules ended, leaving that alert itself out.
    """
    visible_customer_or_404(db, user, customer_id)
    # Only the cases this user may see; a SAR filing is not disclosed to roles without "sar.view"
    alerts = (
        db.query(Alert).filter(Alert.customer_id == customer_id, Alert.id != alert_id, *alert_conditions(user))
        .order_by(Alert.created_at.desc()).all()
    )
    resolved = [a for a in alerts if a.status == "RESOLVED"]

    outcomes: dict[str, int] = {}
    for a in resolved:
        key = a.resolution_outcome or "NOT_RECORDED"
        outcomes[key] = outcomes.get(key, 0) + 1

    same_rules = []
    current = db.get(Alert, alert_id) if alert_id else None
    if current is not None and current.customer_id == customer_id and alert_visible(user, current):
        for rule in _rules(current):
            earlier = [a for a in resolved if rule in _rules(a)]
            same_rules.append({
                "rule": rule,
                "resolved": len(earlier),
                "false_positive": sum(1 for a in earlier if a.resolution_outcome == "FALSE_POSITIVE"),
                "sar_filed": sum(1 for a in earlier if a.resolution_outcome == "SAR_FILED") if sees_sar(user) else 0,
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
def customer_activity(customer_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    """The last 30 days of transactions beside the customer's previous 90, and what changed."""
    visible_customer_or_404(db, user, customer_id)
    return pattern_service.customer_activity(db, customer_id)


# ── How long the case has been open ──────────────────────────────────────

def _case_clock(alert: Alert, audits: list[AuditLog]) -> dict[str, Any]:
    """Age of the case against the target for its risk band (config: CASE_TARGET_DAYS_*)."""
    settings = get_settings()
    band = "high" if alert.risk_score >= 80 else "medium" if alert.risk_score >= 60 else "low"
    target = {"high": settings.case_target_days_high, "medium": settings.case_target_days_medium, "low": settings.case_target_days_low}[band]
    end = alert.resolved_at or datetime.now(timezone.utc)
    age_days = max(0, (end - alert.created_at).days)
    assigned = [a.performed_at for a in audits if "assigned_to" in (a.new_values or {})]
    return {
        "opened_at": alert.created_at.isoformat(),
        "closed_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "age_days": age_days,
        "target_days": target,
        "risk_band": band,
        "overdue": age_days > target,
        "assigned_at": max(assigned).isoformat() if assigned else None,
    }


# ── Requests for information ─────────────────────────────────────────────

class RequestIn(BaseModel):
    requested_from: str = Field(min_length=1, max_length=150)
    subject: str = Field(min_length=1, max_length=2000)
    due_date: date

    @field_validator("requested_from", "subject")
    @classmethod
    def _stripped(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required")
        return value


class RequestClose(BaseModel):
    status: Literal["RECEIVED", "CANCELLED"]
    response_note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _received_needs_note(self) -> "RequestClose":
        if self.status == "RECEIVED" and not (self.response_note or "").strip():
            raise ValueError("Say what was received")
        return self


def _request_out(r: AlertRequest, names: dict[uuid.UUID, str]) -> dict[str, Any]:
    return {
        "id": str(r.id), "alert_id": str(r.alert_id), "requested_from": r.requested_from, "subject": r.subject,
        "due_date": r.due_date.isoformat(), "status": r.status, "response_note": r.response_note,
        "overdue": r.status == "OPEN" and r.due_date < date.today(),
        "requested_by_name": names.get(r.requested_by) or "Unknown user", "created_at": r.created_at.isoformat(),
        "closed_at": r.closed_at.isoformat() if r.closed_at else None,
        "closed_by_name": names.get(r.closed_by) if r.closed_by else None,
    }


def _names(db: Session, ids: set) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    return {u.id: u.full_name or u.username for u in db.query(User).filter(User.id.in_(ids))} if ids else {}


@router.get("/alerts/{alert_id}/requests")
def list_requests(alert_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    alert = visible_alert_or_404(db, user, alert_id)
    rows = db.query(AlertRequest).filter(AlertRequest.alert_id == alert.id).order_by(AlertRequest.created_at.desc()).all()
    names = _names(db, {r.requested_by for r in rows} | {r.closed_by for r in rows})
    return [_request_out(r, names) for r in rows]


@router.post("/alerts/{alert_id}/requests", status_code=status.HTTP_201_CREATED)
def create_request(
    alert_id: uuid.UUID,
    data: RequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("alerts.escalate")),
) -> dict[str, Any]:
    """Record that information was asked for. KYRO does not send the request itself."""
    alert = visible_alert_or_404(db, user, alert_id)
    if alert.status == "RESOLVED":
        raise HTTPException(status.HTTP_409_CONFLICT, "This case is resolved; reopen work on a new alert instead")
    if data.due_date < date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The due date cannot be in the past")
    row = AlertRequest(alert_id=alert.id, requested_from=data.requested_from, subject=data.subject, due_date=data.due_date,
                       requested_by=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _request_out(row, _names(db, {user.id}))


@router.put("/alerts/requests/{request_id}")
def close_request(
    request_id: uuid.UUID,
    data: RequestClose,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("alerts.escalate")),
) -> dict[str, Any]:
    row = db.get(AlertRequest, request_id)
    if row is None or not alert_visible(user, db.get(Alert, row.alert_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    if row.status != "OPEN":
        raise HTTPException(status.HTTP_409_CONFLICT, "This request is already closed")
    row.status = data.status
    row.response_note = (data.response_note or "").strip() or None
    row.closed_by = user.id
    row.closed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _request_out(row, _names(db, {row.requested_by, row.closed_by}))


# ── Screening matches: the list entry beside the customer, and the decision ──

class ScreeningDecision(BaseModel):
    decision: Literal["CLEARED", "CONFIRMED", "ESCALATED"]
    notes: str = Field(min_length=1, max_length=2000)

    @field_validator("notes")
    @classmethod
    def _stripped(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Give the reason for the decision")
        return value


def _screening_out(db: Session, s: PEPSanctionsScreening, customer: Customer, names: dict[uuid.UUID, str]) -> dict[str, Any]:
    entity = db.get(WatchlistEntity, s.watchlist_entity_id) if s.watchlist_entity_id else None
    source = db.get(WatchlistSource, entity.source_id) if entity else None
    owner = db.get(BeneficialOwner, s.beneficial_owner_id) if s.beneficial_owner_id else None
    details = s.match_details or {}
    return {
        "id": str(s.id), "screening_type": s.screening_type, "match_status": s.match_status,
        "match_score": float(s.match_score) if s.match_score is not None else None,
        "screened_at": s.screened_at.isoformat(), "resolution": s.resolution,
        "resolved_at": s.resolved_at.isoformat() if s.resolved_at else None,
        "resolved_by_name": names.get(s.resolved_by) if s.resolved_by else None,
        "resolution_notes": details.get("resolution_notes"),
        "subject": {
            "kind": "Beneficial owner" if owner else "Customer",
            "name": owner.full_name if owner else customer.full_name,
            "date_of_birth": (owner.date_of_birth if owner else customer.date_of_birth).isoformat()
            if (owner.date_of_birth if owner else customer.date_of_birth) else None,
            "country": (owner.nationality if owner else customer.country),
        },
        "listed": {
            "name": entity.primary_name if entity else details.get("entity_primary_name") or details.get("matched_name"),
            "matched_name": details.get("matched_name"),
            "aka_names": (entity.aka_names or [])[:6] if entity else [],
            "date_of_birth": entity.date_of_birth.isoformat() if entity and entity.date_of_birth else None,
            "nationalities": (entity.nationalities or []) if entity else [],
            "programs": (entity.programs if entity else details.get("programs")) or [],
            "list": source.name if source else None,
            "entity_type": entity.entity_type if entity else None,
            "remarks": entity.remarks if entity else None,
            "still_listed": entity.is_active if entity else None,
        },
        "dob_match": details.get("dob_match"),
    }


@router.get("/customers/{customer_id}/screening-matches")
def screening_matches(customer_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    """Possible and confirmed watchlist matches, each with the list entry it matched."""
    customer = visible_customer_or_404(db, user, customer_id)
    rows = (
        db.query(PEPSanctionsScreening)
        .filter(PEPSanctionsScreening.customer_id == customer.id, PEPSanctionsScreening.match_status != "NO_MATCH")
        .order_by(PEPSanctionsScreening.resolution.isnot(None), PEPSanctionsScreening.match_score.desc().nullslast())
        .limit(20).all()
    )
    names = _names(db, {r.resolved_by for r in rows})
    return [_screening_out(db, r, customer, names) for r in rows]


@router.put("/screening/{screening_id}/decision")
def decide_screening(
    screening_id: uuid.UUID,
    data: ScreeningDecision,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("screening.run")),
) -> dict[str, Any]:
    """Record whether a watchlist match is the same person. A confirmed sanctions match flags the customer."""
    row = db.get(PEPSanctionsScreening, screening_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screening result not found")
    customer = visible_customer_or_404(db, user, row.customer_id)
    old = {"resolution": row.resolution, "match_status": row.match_status}
    row.resolution = data.decision
    row.resolved_at = datetime.now(timezone.utc)
    row.resolved_by = user.id
    row.match_details = {**(row.match_details or {}), "resolution_notes": data.notes}
    if data.decision == "CONFIRMED":
        row.match_status = "CONFIRMED_MATCH"
        if row.screening_type == "SANCTIONS":
            customer.sanctions_flag = True
        elif row.screening_type == "PEP":
            customer.pep_flag = True
    log_action(db, entity_type="CUSTOMER", entity_id=customer.id, action="REVIEW", performed_by=user.id, old_values=old,
               new_values={"screening_id": str(row.id), "resolution": data.decision, "notes": data.notes})
    customer_risk_service.assess_customer(db, customer, performed_by=user.id)
    db.commit()
    db.refresh(row)
    return _screening_out(db, row, customer, _names(db, {row.resolved_by}))


# ── Counterparties and countries ─────────────────────────────────────────

COUNTERPARTY_LIMIT = 8


@router.get("/customers/{customer_id}/counterparties")
def counterparties(customer_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Who and where the customer dealt with over the last 120 days, most transactions first."""
    customer = visible_customer_or_404(db, user, customer_id)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=pattern_service.WINDOW_DAYS)
    start = window_start - timedelta(days=pattern_service.BASELINE_DAYS)
    rows = db.query(
        Transaction.transaction_date, Transaction.amount, Transaction.currency, Transaction.meta_counterparty, Transaction.meta_country
    ).filter(Transaction.customer_id == customer.id, Transaction.transaction_date >= start, Transaction.transaction_date <= now).all()
    earlier = {
        "counterparty": {v for (v,) in db.query(Transaction.meta_counterparty).filter(
            Transaction.customer_id == customer.id, Transaction.transaction_date < window_start).distinct() if v},
        "country": {v for (v,) in db.query(Transaction.meta_country).filter(
            Transaction.customer_id == customer.id, Transaction.transaction_date < window_start).distinct() if v},
    }
    from app.services.rules_engine import DEFAULTS  # avoids an import cycle

    high_risk = {str(c).upper() for c in rule_config_service.get_effective_config(db, DEFAULTS, None)["HIGH_RISK_COUNTRIES"]}

    def summarise(index: int, kind: str) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for when, amount, currency, counterparty, country in rows:
            key = (counterparty, country)[index]
            if not key:
                continue
            g = groups.setdefault(key, {"name": key, "transactions": 0, "totals": {}, "countries": set(), "last": when})
            g["transactions"] += 1
            g["totals"][currency or ""] = g["totals"].get(currency or "", 0.0) + float(amount)
            g["last"] = max(g["last"], when)
            if country:
                g["countries"].add(country)
        # Most transactions first; among equals, the largest amounts
        ordered = sorted(groups.values(), key=lambda g: (-g["transactions"], -max(g["totals"].values()), g["name"]))
        return [
            {
                "name": g["name"], "transactions": g["transactions"],
                "totals": [{"currency": c, "amount": round(a, 2)} for c, a in sorted(g["totals"].items(), key=lambda kv: -kv[1])],
                "countries": sorted(g["countries"]), "last_at": g["last"].isoformat(),
                "new": g["name"] not in earlier[kind],
                "high_risk": (g["name"].upper() in high_risk) if kind == "country" else bool({c.upper() for c in g["countries"]} & high_risk),
            }
            for g in ordered
        ]

    by_counterparty, by_country = summarise(0, "counterparty"), summarise(1, "country")
    return {
        "days": pattern_service.WINDOW_DAYS + pattern_service.BASELINE_DAYS,
        "new_since_days": pattern_service.WINDOW_DAYS,
        "transactions": len(rows),
        "counterparty_count": len(by_counterparty),
        "country_count": len(by_country),
        "counterparties": by_counterparty[:COUNTERPARTY_LIMIT],
        "countries": by_country[:COUNTERPARTY_LIMIT],
    }


# ── Why a rule exists: the confirmed obligations mapped to it ────────────

@router.get("/controls/basis")
def regulatory_basis(codes: str = Query(max_length=300), db: Session = Depends(get_db)) -> dict[str, list[dict[str, Any]]]:
    """For each rule code (comma-separated), the confirmed obligations a reviewer has mapped to it."""
    wanted = [c.strip().upper() for c in codes.split(",") if c.strip()][:20]
    out: dict[str, list[dict[str, Any]]] = {code: [] for code in wanted}
    if not wanted:
        return out
    rows = (
        db.query(ObligationMapping, Obligation)
        .join(Obligation, ObligationMapping.obligation_id == Obligation.id)
        .filter(ObligationMapping.control_code.in_(wanted), ObligationMapping.status == "CONFIRMED", Obligation.status == "CONFIRMED")
        .order_by(Obligation.section_ref)
    )
    for mapping, obligation in rows:
        out[mapping.control_code].append({
            "obligation_id": str(obligation.id), "citation": obligation.section_ref, "version": obligation.section_version,
            "who": obligation.obligated_party, "action": obligation.action, "deadline": obligation.deadline,
        })
    return out


# ── Draft narrative ──────────────────────────────────────────────────────

def _case_facts(db: Session, alert: Alert, customer: Customer) -> str:
    """The facts on file for one case, as labelled lines. Nothing here is inferred."""
    rule_names = {c.code: c.name for c in CONTROLS}
    rules = _rules(alert)
    txns = db.query(Transaction).filter(Transaction.customer_id == customer.id).order_by(Transaction.transaction_date.desc()).limit(500).all()
    flagged = [t for t in txns if ((t.risk_flags or {}).get("triggered_rules") if isinstance(t.risk_flags, dict) else None)]
    totals: dict[str, float] = {}
    for t in flagged:
        totals[t.currency or ""] = totals.get(t.currency or "", 0.0) + float(t.amount)
    counterparties = sorted({t.meta_counterparty for t in flagged if t.meta_counterparty})
    countries = sorted({t.meta_country for t in flagged if t.meta_country})
    notes = db.query(AlertNote).filter(AlertNote.alert_id == alert.id).order_by(AlertNote.created_at).all()
    requests = db.query(AlertRequest).filter(AlertRequest.alert_id == alert.id).order_by(AlertRequest.created_at).all()

    lines = [
        f"Who: {customer.full_name}; customer type {_human(customer.customer_type).lower() or 'not recorded'}; "
        f"country {customer.country or 'not recorded'}; risk rating {_human(customer.risk_level).lower() or 'not recorded'}; "
        f"KYC status {_human(customer.kyc_status).lower() or 'not recorded'}"
        + ("; politically exposed person" if customer.pep_flag else "") + ("; sanctions flag set" if customer.sanctions_flag else ""),
        f"Why it was flagged: alert opened {alert.created_at:%d %B %Y} with risk score {alert.risk_score}; rules "
        + (", ".join(f"{code} {rule_names.get(code, '')}".strip() for code in rules) or "none recorded"),
    ]
    if flagged:
        lines.append(
            f"What: {len(flagged)} flagged transactions totalling "
            + ", ".join(f"{amount:,.2f} {currency}".strip() for currency, amount in sorted(totals.items(), key=lambda kv: -kv[1]))
            + "; types " + ", ".join(sorted({_human(t.transaction_type).lower() for t in flagged if t.transaction_type}))
        )
        lines.append(f"When: flagged transactions dated {flagged[-1].transaction_date:%d %B %Y} to {flagged[0].transaction_date:%d %B %Y}")
        if counterparties or countries:
            lines.append(
                "Where: counterparties " + (", ".join(counterparties[:8]) or "not recorded")
                + (f" and {len(counterparties) - 8} more" if len(counterparties) > 8 else "")
                + "; countries " + (", ".join(countries) or "not recorded")
            )
    for note in notes:
        lines.append(f"What was done: note of {note.created_at:%d %B %Y}: {note.body}")
    for r in requests:
        lines.append(
            f"What was done: asked {r.requested_from} for {r.subject} (due {r.due_date:%d %B %Y}); "
            + {"OPEN": "no answer yet", "CANCELLED": "request withdrawn"}.get(r.status, f"received: {r.response_note}")
        )
    if alert.resolution_outcome:
        lines.append(
            f"What was done: case closed as {_human(alert.resolution_outcome).lower()}"
            + (f" ({', '.join(_human(x).lower() for x in alert.resolution_reasons or [])})" if alert.resolution_reasons else "")
            + (f"; {alert.resolution_notes}" if alert.resolution_notes else "")
        )
    return "\n".join(lines)


def _sensitive_names(db: Session, customer: Customer) -> dict[str, str]:
    """Names that must not reach the model: the customer and the parties they dealt with."""
    names = {customer.full_name: "PERSON"}
    for (counterparty,) in db.query(Transaction.meta_counterparty).filter(Transaction.customer_id == customer.id).distinct():
        if counterparty:
            names[counterparty] = "COUNTERPARTY"
    return names


@router.post("/alerts/{alert_id}/draft-narrative")
def draft_narrative(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("alerts.escalate")),
) -> dict[str, Any]:
    """A first draft of the case narrative from the facts on file, for the analyst to check and edit."""
    alert = visible_alert_or_404(db, user, alert_id)
    customer = _customer_or_404(db, alert.customer_id)
    facts = _case_facts(db, alert, customer)
    try:
        result = AIGateway(db).run(
            "cases.draft_narrative", {"facts": facts}, sensitive=_sensitive_names(db, customer),
            entity_type="ALERT", entity_id=alert.id, requested_by=user.id,
        )
    except AIDisabledError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except AIProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    return {
        "narrative": result.text.strip(), "provider": result.provider, "mock": result.provider == "mock",
        "interaction_id": str(result.interaction_id), "facts": facts,
    }


@router.post("/alerts/{alert_id}/summary")
def generate_summary(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("alerts.escalate")),
) -> dict[str, Any]:
    """Write a short summary of the case from the facts on file and keep it on the alert."""
    alert = visible_alert_or_404(db, user, alert_id)
    customer = _customer_or_404(db, alert.customer_id)
    try:
        result = AIGateway(db).run(
            "cases.summary", {"facts": _case_facts(db, alert, customer)}, sensitive=_sensitive_names(db, customer),
            entity_type="ALERT", entity_id=alert.id, requested_by=user.id,
        )
    except AIDisabledError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except AIProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    text = result.text.strip()
    if not text:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The model returned an empty summary")
    alert.summary = text
    alert.summary_at = datetime.now(timezone.utc)
    alert.summary_by = user.id
    alert.summary_provider = result.provider
    db.commit()
    return {
        "summary": alert.summary, "summary_at": alert.summary_at.isoformat(), "summary_provider": alert.summary_provider,
        "mock": result.provider == "mock", "by": user.full_name or user.username,
    }


# ── Accounts, with what has happened on each ─────────────────────────────

@router.get("/customers/{customer_id}/accounts-overview")
def accounts_overview(customer_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Each account with its last 30 days of activity, and the customer's actual turnover beside what was expected."""
    customer = visible_customer_or_404(db, user, customer_id)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=30)
    accounts = db.query(Account).filter(Account.customer_id == customer.id).order_by(Account.opened_date, Account.created_at).all()
    stats: dict[uuid.UUID, dict[str, Any]] = {}
    for account_id, when, amount, flags in db.query(
        Transaction.account_id, Transaction.transaction_date, Transaction.amount, Transaction.risk_flags
    ).filter(Transaction.customer_id == customer.id):
        st = stats.setdefault(account_id, {"transactions": 0, "last_at": None, "recent": 0, "recent_amount": 0.0, "flagged": 0})
        st["transactions"] += 1
        st["last_at"] = max(st["last_at"], when) if st["last_at"] else when
        if when >= since:
            st["recent"] += 1
            st["recent_amount"] += float(amount)
        if isinstance(flags, dict) and flags.get("triggered_rules"):
            st["flagged"] += 1

    rows = []
    turnover: dict[str, float] = {}
    for a in accounts:
        st = stats.get(a.id, {"transactions": 0, "last_at": None, "recent": 0, "recent_amount": 0.0, "flagged": 0})
        meta = a.account_metadata or {}
        turnover[a.currency] = turnover.get(a.currency, 0.0) + st["recent_amount"]
        rows.append({
            "id": str(a.id), "account_type": a.account_type, "account_status": a.account_status, "currency": a.currency,
            "balance": float(a.balance), "opened_date": a.opened_date.isoformat() if a.opened_date else None,
            "account_number": meta.get("account_number"), "product": meta.get("product"), "purpose": meta.get("purpose"),
            "branch": meta.get("branch"), "opened_channel": meta.get("opened_channel"), "sample_data": bool(meta.get("sample_data")),
            "transactions": st["transactions"], "flagged_transactions": st["flagged"],
            "last_transaction_at": st["last_at"].isoformat() if st["last_at"] else None,
            "last_30_days": {"transactions": st["recent"], "amount": round(st["recent_amount"], 2)},
        })
    expected = (customer.customer_metadata or {}).get("expected_monthly_turnover")
    return {
        "accounts": rows,
        "turnover_last_30_days": [{"currency": c, "amount": round(v, 2)} for c, v in sorted(turnover.items(), key=lambda kv: -kv[1]) if v],
        "expected_monthly_turnover": expected if isinstance(expected, dict) else None,
    }
