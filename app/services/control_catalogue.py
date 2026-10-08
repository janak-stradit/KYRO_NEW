"""
services/control_catalogue.py — The controls KYRO actually operates, which
obligations can be mapped to (Phase 11.4). Rule entries name the
`rule_configs` keys that tune them, so the traceability matrix can show the
live threshold next to the obligation it enforces.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Control:
    code: str
    kind: str  # RULE | SCREENING | REVIEW | RECORD | PROCESS
    name: str
    description: str
    config_keys: tuple[str, ...] = ()


CONTROLS: tuple[Control, ...] = (
    Control("R001", "RULE", "Amount Threshold", "Flags a transaction above the reporting threshold.", ("AMOUNT_THRESHOLD",)),
    Control("R002", "RULE", "Velocity (daily)", "Flags more transactions per day than the limit.", ("VELOCITY_DAILY_LIMIT",)),
    Control("R003", "RULE", "Velocity (hourly)", "Flags more transactions per hour than the limit.", ("VELOCITY_HOURLY_LIMIT",)),
    Control("R004", "RULE", "High-Risk Country", "Flags counterparties in sanctioned or high-risk jurisdictions.", ("HIGH_RISK_COUNTRIES",)),
    Control("R005", "RULE", "PEP Match", "Flags transactions by politically exposed persons."),
    Control("R006", "RULE", "Sanctions Match", "Flags transactions by customers matched on a sanctions list."),
    Control("R007", "RULE", "New Counterparty", "Flags the first transaction with a counterparty."),
    Control("R008", "RULE", "Weekend Activity", "Flags transactions made on a weekend."),
    Control("R009", "RULE", "Round Amount", "Flags suspiciously round transaction amounts."),
    Control("R010", "RULE", "Rapid Succession", "Flags several transactions within a short window.", ("RAPID_SUCCESSION_WINDOW_SECONDS",)),
    Control("SCREENING", "SCREENING", "Watchlist screening", "Screens customers and beneficial owners against sanctions and PEP lists, nightly and on demand."),
    Control("CUSTOMER_ONBOARDING", "RECORD", "Customer identification", "Captures name, date of birth, address and identification details on the customer record."),
    Control("UBO_REGISTER", "RECORD", "Beneficial ownership register", "Records beneficial owners and controllers of corporate and fund customers."),
    Control("KYC_REVIEW", "REVIEW", "Periodic KYC reviews", "Schedules risk-based re-reviews of customers and tracks overdue reviews."),
    Control("CASE_DISPOSITION", "PROCESS", "Alert investigation and disposition", "Analysts investigate alerts and record an outcome, reasons and SAR reference."),
    Control("AUDIT_LOG", "RECORD", "Audit trail", "Keeps an immutable record of changes, decisions and AI calls."),
    Control("EXTERNAL_PROCESS", "PROCESS", "Handled outside KYRO", "Met by a manual or third-party process that KYRO does not operate."),
)

CONTROLS_BY_CODE: dict[str, Control] = {c.code: c for c in CONTROLS}


def catalogue_text() -> str:
    """The catalogue as shown to the model when it proposes mappings."""
    return "\n".join(f"- {c.code}: {c.name} — {c.description}" for c in CONTROLS)
