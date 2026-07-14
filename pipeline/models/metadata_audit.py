"""
models/metadata_audit.py — Metadata, audit, logging, and feature store models.
Schemas: metadata, audit, logs, feature_store, ml
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pipeline.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


# ══════════════════════════════════════════════════════════════
# SCHEMA: metadata
# ══════════════════════════════════════════════════════════════

class PipelineExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One record per pipeline run — tracks all execution metadata."""
    __tablename__ = "pipeline_executions"
    __table_args__ = (
        Index("ix_meta_exec_status", "status"),
        Index("ix_meta_exec_started", "started_at"),
        {"schema": "metadata"},
    )
    execution_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    pipeline_name: Mapped[str] = mapped_column(String(100), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_version: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str | None] = mapped_column(String(255))
    source_format: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    rows_ingested: Mapped[int | None] = mapped_column(Integer)
    rows_valid: Mapped[int | None] = mapped_column(Integer)
    rows_rejected: Mapped[int | None] = mapped_column(Integer)
    rows_inserted: Mapped[int | None] = mapped_column(Integer)
    rows_updated: Mapped[int | None] = mapped_column(Integer)
    duplicates_removed: Mapped[int | None] = mapped_column(Integer)
    outliers_flagged: Mapped[int | None] = mapped_column(Integer)
    missing_values_filled: Mapped[int | None] = mapped_column(Integer)
    quality_score: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    triggered_by: Mapped[str | None] = mapped_column(String(100))
    host: Mapped[str | None] = mapped_column(String(100))
    peak_memory_mb: Mapped[float | None] = mapped_column(Float)
    avg_cpu_percent: Mapped[float | None] = mapped_column(Float)


class TransformationHistory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Records every transformation applied to a dataset for full lineage."""
    __tablename__ = "transformation_history"
    __table_args__ = (
        Index("ix_txhist_exec_id", "execution_id"),
        Index("ix_txhist_entity", "entity_type"),
        {"schema": "metadata"},
    )
    execution_id: Mapped[str] = mapped_column(String(50), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    transformation_name: Mapped[str] = mapped_column(String(100), nullable=False)
    transformation_type: Mapped[str | None] = mapped_column(String(50))
    columns_affected: Mapped[list | None] = mapped_column(JSONB)
    parameters: Mapped[dict | None] = mapped_column(JSONB)
    rows_before: Mapped[int | None] = mapped_column(Integer)
    rows_after: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)


# ══════════════════════════════════════════════════════════════
# SCHEMA: audit
# ══════════════════════════════════════════════════════════════

class AuditLog(Base, UUIDPrimaryKeyMixin):
    """Immutable audit trail: INSERT / UPDATE / DELETE with old/new values."""
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type"),
        Index("ix_audit_operation", "operation"),
        Index("ix_audit_record_id", "record_id"),
        Index("ix_audit_ts_brin", "event_timestamp", postgresql_using="brin"),
        {"schema": "audit"},
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    record_id: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(10), nullable=False)  # INSERT|UPDATE|DELETE
    old_values: Mapped[dict | None] = mapped_column(JSONB)
    new_values: Mapped[dict | None] = mapped_column(JSONB)
    changed_columns: Mapped[list | None] = mapped_column(JSONB)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    performed_by: Mapped[str | None] = mapped_column(String(100))
    execution_id: Mapped[str | None] = mapped_column(String(50))
    db_user: Mapped[str | None] = mapped_column(String(100))
    client_ip: Mapped[str | None] = mapped_column(String(45))


# ══════════════════════════════════════════════════════════════
# SCHEMA: logs
# ══════════════════════════════════════════════════════════════

class PipelineLog(Base, UUIDPrimaryKeyMixin):
    """Structured pipeline log entries stored in the database."""
    __tablename__ = "pipeline_logs"
    __table_args__ = (
        Index("ix_plog_exec_id", "execution_id"),
        Index("ix_plog_level", "level"),
        Index("ix_plog_ts_brin", "log_timestamp", postgresql_using="brin"),
        {"schema": "logs"},
    )
    execution_id: Mapped[str | None] = mapped_column(String(50))
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB)
    log_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ══════════════════════════════════════════════════════════════
# SCHEMA: feature_store
# ══════════════════════════════════════════════════════════════

class FeatureDefinition(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Feature registry — metadata about each ML feature."""
    __tablename__ = "feature_definitions"
    __table_args__ = (
        UniqueConstraint("feature_name", "version", name="uq_feature_version"),
        Index("ix_feat_entity", "entity_type"),
        {"schema": "feature_store"},
    )
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    feature_type: Mapped[str | None] = mapped_column(String(30))  # numerical|categorical|boolean
    source_columns: Mapped[list | None] = mapped_column(JSONB)
    transformation_logic: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[list | None] = mapped_column(JSONB)
    statistics: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class FeatureSet(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A named collection of features for a specific ML use-case."""
    __tablename__ = "feature_sets"
    __table_args__ = (
        UniqueConstraint("set_name", "version", name="uq_featureset_version"),
        {"schema": "feature_store"},
    )
    set_name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    feature_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    execution_id: Mapped[str | None] = mapped_column(String(50))
    row_count: Mapped[int | None] = mapped_column(Integer)
    dataset_type: Mapped[str | None] = mapped_column(String(20))  # training|validation|inference
    quality_score: Mapped[float | None] = mapped_column(Float)


class CustomerFeatures(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """ML-ready customer feature vector."""
    __tablename__ = "customer_features"
    __table_args__ = (
        UniqueConstraint("customer_id", "feature_set_version", name="uq_cust_feat_version"),
        Index("ix_cust_feat_customer", "customer_id"),
        Index("ix_cust_feat_risk", "risk_score_scaled"),
        {"schema": "feature_store"},
    )
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    feature_set_version: Mapped[str] = mapped_column(String(20), nullable=False)
    # Encoded categoricals
    risk_level_encoded: Mapped[float | None] = mapped_column(Float)
    kyc_status_encoded: Mapped[float | None] = mapped_column(Float)
    customer_type_encoded: Mapped[float | None] = mapped_column(Float)
    # Scaled numerics
    risk_score_scaled: Mapped[float | None] = mapped_column(Float)
    account_count: Mapped[int | None] = mapped_column(Integer)
    total_balance_scaled: Mapped[float | None] = mapped_column(Float)
    # Flags (1/0)
    pep_flag: Mapped[int | None] = mapped_column(Integer)
    sanctions_flag: Mapped[int | None] = mapped_column(Integer)
    adverse_media_flag: Mapped[int | None] = mapped_column(Integer)
    is_high_risk_country: Mapped[int | None] = mapped_column(Integer)
    # KPIs
    txn_count_30d: Mapped[int | None] = mapped_column(Integer)
    txn_amount_sum_30d: Mapped[float | None] = mapped_column(Float)
    txn_amount_avg_30d: Mapped[float | None] = mapped_column(Float)
    high_value_txn_count: Mapped[int | None] = mapped_column(Integer)
    unique_countries_count: Mapped[int | None] = mapped_column(Integer)
    # Full feature vector for arbitrary ML use
    feature_vector: Mapped[dict | None] = mapped_column(JSONB)
    label_aml_risk: Mapped[int | None] = mapped_column(Integer)  # 0/1 target


class TransactionFeatures(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """ML-ready transaction feature vector."""
    __tablename__ = "transaction_features"
    __table_args__ = (
        UniqueConstraint("transaction_id", "feature_set_version", name="uq_txn_feat_version"),
        Index("ix_txn_feat_customer", "customer_id"),
        Index("ix_txn_feat_date_brin", "transaction_date", postgresql_using="brin"),
        {"schema": "feature_store"},
    )
    transaction_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    account_id: Mapped[str] = mapped_column(String(40), nullable=False)
    feature_set_version: Mapped[str] = mapped_column(String(20), nullable=False)
    transaction_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Date features
    txn_year: Mapped[int | None] = mapped_column(Integer)
    txn_month: Mapped[int | None] = mapped_column(Integer)
    txn_day: Mapped[int | None] = mapped_column(Integer)
    txn_dayofweek: Mapped[int | None] = mapped_column(Integer)
    txn_quarter: Mapped[int | None] = mapped_column(Integer)
    txn_is_weekend: Mapped[int | None] = mapped_column(Integer)
    # Scaled
    amount_scaled: Mapped[float | None] = mapped_column(Float)
    # Lag features
    amount_lag1: Mapped[float | None] = mapped_column(Float)
    amount_lag3: Mapped[float | None] = mapped_column(Float)
    amount_lag7: Mapped[float | None] = mapped_column(Float)
    # Rolling
    amount_rolling_7d_mean: Mapped[float | None] = mapped_column(Float)
    amount_rolling_30d_mean: Mapped[float | None] = mapped_column(Float)
    amount_rolling_30d_std: Mapped[float | None] = mapped_column(Float)
    # Flags
    is_high_value: Mapped[int | None] = mapped_column(Integer)
    is_high_risk_country: Mapped[int | None] = mapped_column(Integer)
    # Encoded
    txn_type_encoded: Mapped[float | None] = mapped_column(Float)
    # Full vector
    feature_vector: Mapped[dict | None] = mapped_column(JSONB)
    label_suspicious: Mapped[int | None] = mapped_column(Integer)
