"""
schemas/alert.py — Alert queue schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AlertStatus = Literal["OPEN", "ASSIGNED", "IN_REVIEW", "RESOLVED", "ESCALATED"]
RecommendedAction = Literal[
    "REVIEW", "ENHANCED_DUE_DILIGENCE", "SAR", "CLOSE", "BATCH_REVIEW", "IMMEDIATE_REVIEW"
]

# Disposition taxonomy (docs/plans/COMPLIANCE_AI_PLAN.md §9.6). The codes are
# the labels the false-positive model and rule-tuning backlog are built from.
ResolutionOutcome = Literal["SAR_FILED", "ESCALATED", "TRUE_POSITIVE_NO_SAR", "FALSE_POSITIVE"]
FinalOutcome = Literal["SAR_FILED", "TRUE_POSITIVE_NO_SAR", "FALSE_POSITIVE"]

RESOLUTION_OUTCOMES: dict[str, str] = {
    "SAR_FILED": "Suspicion confirmed; SAR/STR filed",
    "ESCALATED": "Passed to senior compliance / MLRO for decision",
    "TRUE_POSITIVE_NO_SAR": "Activity matched the rule and needed review, but no suspicion after investigation",
    "FALSE_POSITIVE": "Alert did not represent the risk the rule targets",
}
RESOLUTION_REASONS: dict[str, str] = {
    "EXPECTED_ACTIVITY_DOCUMENTED": "Expected activity, documented",
    "CUSTOMER_EXPLANATION_VERIFIED": "Customer explanation verified",
    "KNOWN_COUNTERPARTY": "Known counterparty",
    "RULE_TOO_BROAD": "Rule too broad",
    "THRESHOLD_TOO_LOW": "Threshold too low",
    "DATA_QUALITY_ISSUE": "Data quality issue",
    "DUPLICATE_ALERT": "Duplicate alert",
    "SCREENING_NAME_MISMATCH": "Screening name mismatch",
    "STRUCTURING_SUSPECTED": "Structuring suspected",
    "LAYERING_SUSPECTED": "Layering suspected",
    "SANCTIONS_EXPOSURE": "Sanctions exposure",
    "UNEXPLAINED_SOURCE_OF_FUNDS": "Unexplained source of funds",
    "OTHER": "Other (explain in notes)",
}
_SUSPICION_REASONS = (
    "STRUCTURING_SUSPECTED", "LAYERING_SUSPECTED", "SANCTIONS_EXPOSURE", "UNEXPLAINED_SOURCE_OF_FUNDS", "OTHER",
)
# Which reasons make sense for which outcome, so labels stay consistent
OUTCOME_REASONS: dict[str, tuple[str, ...]] = {
    "SAR_FILED": _SUSPICION_REASONS,
    "ESCALATED": _SUSPICION_REASONS,
    "TRUE_POSITIVE_NO_SAR": ("EXPECTED_ACTIVITY_DOCUMENTED", "CUSTOMER_EXPLANATION_VERIFIED", "OTHER"),
    "FALSE_POSITIVE": (
        "KNOWN_COUNTERPARTY", "RULE_TOO_BROAD", "THRESHOLD_TOO_LOW", "DATA_QUALITY_ISSUE",
        "DUPLICATE_ALERT", "SCREENING_NAME_MISMATCH", "OTHER",
    ),
}


def _check_reasons(outcome: str, reasons: list[str]) -> list[str]:
    reasons = list(dict.fromkeys(reasons))  # de-duplicate, keep order
    invalid = [r for r in reasons if r not in OUTCOME_REASONS[outcome]]
    if invalid:
        raise ValueError(f"Reason(s) {', '.join(invalid)} are not valid for outcome {outcome}")
    return reasons


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    alert_type: str | None = None
    risk_score: int
    confidence: float | None = None
    triggered_rules: dict[str, Any] | list[Any] | None = None
    ml_explanation: dict[str, Any] | None = None
    recommended_action: RecommendedAction | None = None
    status: AlertStatus
    assigned_to: uuid.UUID | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: uuid.UUID | None = None
    resolution_notes: str | None = None
    is_false_positive: bool | None = None
    resolution_outcome: ResolutionOutcome | None = None
    resolution_reasons: list[str] | None = None
    sar_reference: str | None = None
    ml_version: str | None = None


class AlertAssign(BaseModel):
    assigned_to: uuid.UUID


class AlertResolve(BaseModel):
    """Final disposition. `is_false_positive` is derived from the outcome."""

    outcome: FinalOutcome
    reasons: list[str] = Field(min_length=1)
    resolution_notes: str
    sar_reference: str | None = Field(default=None, max_length=100)

    @field_validator("resolution_notes")
    @classmethod
    def _notes_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Resolution notes are required")
        return value

    @model_validator(mode="after")
    def _reasons_match_outcome(self) -> "AlertResolve":
        self.reasons = _check_reasons(self.outcome, self.reasons)
        return self


class AlertEscalate(BaseModel):
    resolution_notes: str | None = None
    reasons: list[str] = Field(default_factory=list)

    @field_validator("reasons")
    @classmethod
    def _valid_reasons(cls, value: list[str]) -> list[str]:
        return _check_reasons("ESCALATED", value)


class ResolutionOption(BaseModel):
    code: str
    label: str


class ResolutionOutcomeOption(ResolutionOption):
    reasons: list[str]


class ResolutionOptions(BaseModel):
    outcomes: list[ResolutionOutcomeOption]
    reasons: list[ResolutionOption]
