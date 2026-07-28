"""
core/exceptions.py — Custom exception hierarchy for the KYRO pipeline.
All pipeline exceptions inherit from PipelineError for easy catch-all handling.
"""
from __future__ import annotations


class PipelineError(Exception):
    """Base exception for all KYRO pipeline errors."""


# ── Ingestion ──────────────────────────────────────────────────
class IngestionError(PipelineError):
    """Raised when raw data cannot be read or parsed."""


class EncodingError(IngestionError):
    """File encoding cannot be detected or decoded."""


class SchemaEvolutionError(IngestionError):
    """Source schema has changed incompatibly with the target schema."""


# ── Validation ─────────────────────────────────────────────────
class ValidationError(PipelineError):
    """One or more validation rules failed."""

    def __init__(self, message: str, errors: list[dict] | None = None) -> None:
        super().__init__(message)
        self.errors: list[dict] = errors or []


class SchemaValidationError(ValidationError):
    """Required columns are missing or have wrong types."""


# ── Cleaning ───────────────────────────────────────────────────
class CleaningError(PipelineError):
    """Data cleaning step failed unexpectedly."""


# ── Transformation ─────────────────────────────────────────────
class TransformationError(PipelineError):
    """A transformation could not be applied."""


class ScalerNotFittedError(TransformationError):
    """Scaler object has not been fitted before being called for transform."""


# ── Database ───────────────────────────────────────────────────
class DatabaseError(PipelineError):
    """Generic database operation failure."""


class ConnectionPoolError(DatabaseError):
    """Cannot acquire a connection from the pool."""


class DeadlockError(DatabaseError):
    """Transaction deadlock detected; should trigger a retry."""


class ConstraintViolationError(DatabaseError):
    """A database constraint (PK, FK, UNIQUE, CHECK) was violated."""


class DuplicateKeyError(ConstraintViolationError):
    """Duplicate primary or unique key detected on insert/upsert."""


# ── Feature Store ──────────────────────────────────────────────
class FeatureStoreError(PipelineError):
    """Feature registration or retrieval failed."""


# ── Quality ────────────────────────────────────────────────────
class DataQualityError(PipelineError):
    """Quality score dropped below acceptable threshold."""

    def __init__(self, message: str, score: float = 0.0) -> None:
        super().__init__(message)
        self.score = score


# ── Retry ──────────────────────────────────────────────────────
class MaxRetriesExceededError(PipelineError):
    """Retry limit reached without success."""

    def __init__(self, operation: str, attempts: int) -> None:
        super().__init__(f"Max retries ({attempts}) exceeded for: {operation}")
        self.operation = operation
        self.attempts = attempts
