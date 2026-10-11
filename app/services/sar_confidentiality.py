"""
services/sar_confidentiality.py — What a role without "sar.view" may see of
a SAR-sensitive case.

A case becomes SAR-sensitive when it is escalated as a potential SAR
(alerts.sar_candidate_at). A filed SAR is hidden altogether by app/visibility.py;
a potential SAR stays visible so the team lead can follow it, but:

  * the escalation notes and reasons, the SAR reference, any case summary
    written after the escalation, the narratives and the notes added after
    the escalation are withheld;
  * its progress is shown as a general compliance status (compliance_status),
    which never says "SAR".

Every response that carries these fields goes through this module.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.alert import Alert
from app.models.user import User
from app.visibility import SAR_OUTCOME, sees_sar

WITHHELD = ("resolution_notes", "resolution_reasons", "sar_reference")


def is_sensitive(alert: Alert) -> bool:
    return alert.sar_candidate_at is not None or alert.resolution_outcome == SAR_OUTCOME


def restricted_for(user: User, alert: Alert) -> bool:
    """True when this user sees the case but not its SAR content."""
    return is_sensitive(alert) and not sees_sar(user)


def compliance_status(alert: Alert) -> str:
    """Where the case is, in words that are safe for every role."""
    if alert.status == "RESOLVED":
        return "CLOSED"
    if alert.status == "ESCALATED":
        return "WITH_MLRO"
    return "IN_PROGRESS"


def mask_alert(item: dict[str, Any], alert: Alert, user: User) -> dict[str, Any]:
    """An alert as returned by the API (a dict), with SAR content removed for roles that may not see it."""
    item["compliance_status"] = compliance_status(alert)
    item["restricted"] = restricted_for(user, alert)
    item["potential_sar"] = (alert.sar_candidate_at is not None) if sees_sar(user) else None
    if item["restricted"]:
        for field in WITHHELD:
            if field in item:
                item[field] = None
        since = alert.sar_candidate_at
        if alert.summary_at is not None and (since is None or alert.summary_at >= since) and "summary" in item:
            item.update(summary=None, summary_at=None, summary_provider=None)
    return item


def note_visible(user: User, alert: Alert, written_at: datetime) -> bool:
    """Notes written once the case became a potential SAR belong to the SAR work."""
    if not restricted_for(user, alert):
        return True
    return alert.sar_candidate_at is not None and written_at < alert.sar_candidate_at
