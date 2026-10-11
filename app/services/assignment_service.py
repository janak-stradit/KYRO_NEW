"""
services/assignment_service.py — Gives every new alert an owner automatically.

1. Routing: assignment rules are checked in priority order; the first rule whose
   conditions all match sends the alert to its team. No match: the alert stays in
   the unassigned pool for a Team Lead.
2. Within the team: the available member with the fewest open cases (then fewest
   overdue, then the one assigned least recently) — or plain round-robin when
   AUTO_ASSIGN_METHOD=round_robin. A member must be active, available and hold a
   role that can work cases.
3. The assignment is audited with the rule and team that decided it; anyone with
   alerts.assign can still reassign.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.alert import Alert
from app.models.assignment import AssignmentRule, Team, TeamMember
from app.models.customer import Customer
from app.models.user import User
from app.permissions import has_permission, is_read_only
from app.services import deadline_service
from app.services.audit_service import log_action

UNRESOLVED = ("OPEN", "ASSIGNED", "IN_REVIEW", "ESCALATED")
CASE_WORK = ("alerts.close_false_positive", "alerts.close", "alerts.escalate", "sar.approve")
CONDITION_KEYS = ("alert_types", "rules_any", "min_score", "max_score", "segments", "countries", "recommended_actions")


def can_work_cases(role: str) -> bool:
    return not is_read_only(role) and any(has_permission(role, p) for p in CASE_WORK)


def _rules_of(alert: Alert) -> list[str]:
    rules = alert.triggered_rules.get("rules") if isinstance(alert.triggered_rules, dict) else None
    return [str(r) for r in rules or []]


def matches(conditions: dict[str, Any], alert: Alert, customer: Customer | None) -> bool:
    c = conditions or {}
    if c.get("alert_types") and (alert.alert_type or "") not in c["alert_types"]:
        return False
    if c.get("rules_any") and not set(c["rules_any"]) & set(_rules_of(alert)):
        return False
    if c.get("min_score") is not None and alert.risk_score < c["min_score"]:
        return False
    if c.get("max_score") is not None and alert.risk_score > c["max_score"]:
        return False
    if c.get("recommended_actions") and (alert.recommended_action or "") not in c["recommended_actions"]:
        return False
    if c.get("segments") and (customer is None or (customer.segment or "") not in c["segments"]):
        return False
    if c.get("countries"):
        countries = {x.upper() for x in c["countries"]}
        if customer is None or not {(customer.residency_country or "").upper(), (customer.country or "").upper()} & countries:
            return False
    return True


def route(db: Session, alert: Alert, customer: Customer | None) -> AssignmentRule | None:
    rules = (
        db.query(AssignmentRule).join(Team, Team.id == AssignmentRule.team_id)
        .filter(AssignmentRule.is_active.is_(True), Team.is_active.is_(True))
        .order_by(AssignmentRule.priority, AssignmentRule.created_at).all()
    )
    return next((r for r in rules if matches(r.conditions, alert, customer)), None)


def candidates(db: Session, team_id: uuid.UUID) -> list[tuple[TeamMember, User]]:
    rows = (
        db.query(TeamMember, User).join(User, User.id == TeamMember.user_id)
        .filter(TeamMember.team_id == team_id, TeamMember.available.is_(True), User.is_active.is_(True)).all()
    )
    return [(m, u) for m, u in rows if can_work_cases(u.role)]


def workload(db: Session, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    """Open and overdue cases per person."""
    if not user_ids:
        return {}
    overdue = func.sum(case((deadline_service.overdue_condition(), 1), else_=0))
    rows = (
        db.query(Alert.assigned_to, func.count(Alert.id), overdue)
        .filter(Alert.assigned_to.in_(user_ids), Alert.status.in_(UNRESOLVED)).group_by(Alert.assigned_to).all()
    )
    return {uid: (count, int(late or 0)) for uid, count, late in rows}


def pick(db: Session, team_id: uuid.UUID) -> tuple[TeamMember, User] | None:
    pool = candidates(db, team_id)
    if not pool:
        return None
    never = datetime.min.replace(tzinfo=timezone.utc)
    if get_settings().auto_assign_method == "round_robin":
        return min(pool, key=lambda mu: (mu[0].last_assigned_at or never, mu[1].username))
    load = workload(db, [u.id for _, u in pool])
    return min(pool, key=lambda mu: (*load.get(mu[1].id, (0, 0)), mu[0].last_assigned_at or never, mu[1].username))


def assign_new(db: Session, alert: Alert, customer: Customer | None, *, performed_by: uuid.UUID | None = None) -> User | None:
    """Route and assign one unassigned alert. Returns the new owner, or None if it stays in the pool."""
    if not get_settings().auto_assign_enabled or alert.assigned_to is not None or alert.status not in ("OPEN",):
        return None
    rule = route(db, alert, customer)
    if rule is None:
        return None
    chosen = pick(db, rule.team_id)
    alert.team_id = rule.team_id
    if chosen is None:
        return None  # team known, nobody available: the Team Lead sees it in the pool
    member, user = chosen
    alert.assigned_to = user.id
    alert.status = "ASSIGNED"
    member.last_assigned_at = datetime.now(timezone.utc)
    team = db.get(Team, rule.team_id)
    log_action(db, entity_type="ALERT", entity_id=alert.id, action="UPDATE", performed_by=performed_by,
               new_values={"assigned_to": str(user.id), "auto_assigned": True, "team": team.name if team else None,
                           "assignment_rule": rule.name})
    db.flush()
    return user


def assign_backlog(db: Session, *, limit: int = 500, performed_by: uuid.UUID | None = None) -> dict[str, int]:
    """Route the unassigned pool, highest risk and oldest first. Nothing already owned is touched."""
    pending = (
        db.query(Alert).filter(Alert.status == "OPEN", Alert.assigned_to.is_(None))
        .order_by(Alert.risk_score.desc(), Alert.created_at).limit(limit).all()
    )
    customers = {c.id: c for c in db.query(Customer).filter(Customer.id.in_({a.customer_id for a in pending}))} if pending else {}
    assigned = no_rule = no_member = 0
    for alert in pending:
        if assign_new(db, alert, customers.get(alert.customer_id), performed_by=performed_by) is not None:
            assigned += 1
        elif alert.team_id is not None:
            no_member += 1
        else:
            no_rule += 1
    db.commit()
    return {"checked": len(pending), "assigned": assigned, "no_matching_rule": no_rule, "no_one_available": no_member}


def explain(db: Session, alert: Alert, customer: Customer | None) -> dict[str, Any]:
    """Which rule, team and person a new alert like this would go to, and why — for the routing screen."""
    rule = route(db, alert, customer)
    if rule is None:
        return {"rule": None, "team": None, "assignee": None, "reason": "No rule matches: the alert stays in the unassigned pool"}
    team = db.get(Team, rule.team_id)
    chosen = pick(db, rule.team_id)
    return {
        "rule": rule.name, "team": team.name if team else None,
        "assignee": (chosen[1].full_name or chosen[1].username) if chosen else None,
        "reason": None if chosen else "Nobody in the team is available",
    }
