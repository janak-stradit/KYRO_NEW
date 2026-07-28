"""
migrations/env.py — Alembic environment configuration.
Reads SQLAlchemy engine from pipeline config; supports both online and offline modes.
All 10 schemas are included in the autogenerate target metadata.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure pipeline package is importable from migrations directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pipeline.core.config import load_config, get_db_url
from pipeline.models.base import Base

# Import ALL models so Alembic can discover them for autogenerate
from pipeline.models import (  # noqa: F401
    RawCustomer, RawAccount, RawTransaction, RejectedRecord,
    Country, Currency, KycStatusLookup, RiskLevelLookup,
    WCustomer, WAccount, WTransaction,
    PipelineExecution, TransformationHistory,
    AuditLog, PipelineLog,
    FeatureDefinition, FeatureSet, CustomerFeatures, TransactionFeatures,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Override sqlalchemy.url with value from pipeline config
pipeline_cfg = load_config()
config.set_main_option("sqlalchemy.url", get_db_url(pipeline_cfg))

# Include all pipeline schemas in autogenerate
INCLUDE_SCHEMAS = {
    "raw_data", "staging", "cleaned", "warehouse",
    "feature_store", "metadata", "audit", "logs", "ml", "analytics",
}


def include_object(object, name, type_, reflected, compare_to):
    """Tell Alembic which schemas/tables to include in autogenerate."""
    if type_ == "table":
        schema = getattr(object, "schema", None)
        return schema in INCLUDE_SCHEMAS
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
        version_table_schema="metadata",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = get_db_url(pipeline_cfg)
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
            version_table_schema="metadata",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
