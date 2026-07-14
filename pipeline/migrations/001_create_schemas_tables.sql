-- ============================================================
-- KYRO AML Pipeline — Master DDL Script
-- PostgreSQL 15+  |  Run as superuser or schema owner
-- ============================================================
-- Execution order matters — run top to bottom.
-- ============================================================

-- ── Extensions ────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";        -- fuzzy text search
CREATE EXTENSION IF NOT EXISTS "btree_gin";       -- GIN on scalar types
CREATE EXTENSION IF NOT EXISTS "btree_gist";      -- GIST for exclusion constraints

-- ── Schemas ───────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS raw_data;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS cleaned;
CREATE SCHEMA IF NOT EXISTS warehouse;
CREATE SCHEMA IF NOT EXISTS feature_store;
CREATE SCHEMA IF NOT EXISTS metadata;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS logs;
CREATE SCHEMA IF NOT EXISTS ml;
CREATE SCHEMA IF NOT EXISTS analytics;

COMMENT ON SCHEMA raw_data      IS 'Exact source records with zero transformations';
COMMENT ON SCHEMA staging       IS 'Intermediate staging area during ETL';
COMMENT ON SCHEMA cleaned       IS 'Cleaned, validated records ready for warehouse';
COMMENT ON SCHEMA warehouse     IS 'Normalized 3NF/BCNF business tables';
COMMENT ON SCHEMA feature_store IS 'ML-ready feature vectors and feature registry';
COMMENT ON SCHEMA metadata      IS 'Pipeline execution metadata and lineage';
COMMENT ON SCHEMA audit         IS 'Immutable audit trails for all DML operations';
COMMENT ON SCHEMA logs          IS 'Structured pipeline log entries';
COMMENT ON SCHEMA ml            IS 'ML model registry and inference results';
COMMENT ON SCHEMA analytics     IS 'Materialized views and analytical aggregations';

-- ── Enum Types ────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE warehouse.risk_level_enum AS ENUM ('LOW','MEDIUM','HIGH');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE warehouse.kyc_status_enum AS ENUM ('COMPLETE','PENDING','EXPIRED','PARTIAL');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE warehouse.account_status_enum AS ENUM ('ACTIVE','CLOSED','FROZEN','SUSPENDED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE metadata.pipeline_status_enum AS ENUM ('RUNNING','SUCCESS','FAILED','PARTIAL','CANCELLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE audit.operation_enum AS ENUM ('INSERT','UPDATE','DELETE','UPSERT');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ============================================================
-- SCHEMA: raw_data
-- Purpose: Land source data exactly as received — no transforms.
-- Normalization: 1NF only (atomic columns, JSONB for semi-structured).
-- ============================================================

CREATE TABLE IF NOT EXISTS raw_data.customers (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id         VARCHAR(20)   NOT NULL,
    full_name           VARCHAR(255),
    email               VARCHAR(255),
    phone               VARCHAR(60),
    date_of_birth       VARCHAR(20),
    country             VARCHAR(10),
    residency_country   VARCHAR(10),
    kyc_status          VARCHAR(20),
    kyc_last_review     VARCHAR(20),
    pep_flag            BOOLEAN,
    sanctions_flag      BOOLEAN,
    adverse_media_flag  BOOLEAN,
    risk_level          VARCHAR(20)   CHECK (risk_level IN ('LOW','MEDIUM','HIGH')),
    risk_score          NUMERIC(8,4)  CHECK (risk_score BETWEEN 0 AND 100),
    customer_type       VARCHAR(30),
    customer_metadata   JSONB,
    -- Pipeline audit columns
    ingestion_id        UUID,
    source_file         VARCHAR(512),
    batch_id            VARCHAR(100),
    is_valid            BOOLEAN       NOT NULL DEFAULT TRUE,
    validation_errors   JSONB,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_raw_customer_id UNIQUE (customer_id)
);

COMMENT ON TABLE raw_data.customers IS
    'Raw customer records as received from the AML data generator. Zero transformations applied.';

CREATE TABLE IF NOT EXISTS raw_data.accounts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id          VARCHAR(40)   NOT NULL,
    customer_id         VARCHAR(20)   NOT NULL,
    account_type        VARCHAR(30),
    account_status      VARCHAR(20),
    currency            VARCHAR(5),
    balance             NUMERIC(18,2),
    opened_date         VARCHAR(20),
    account_metadata    JSONB,
    ingestion_id        UUID,
    source_file         VARCHAR(512),
    batch_id            VARCHAR(100),
    is_valid            BOOLEAN       NOT NULL DEFAULT TRUE,
    validation_errors   JSONB,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_raw_account_id UNIQUE (account_id)
);

-- Partitioned transactions table (RANGE by transaction_date)
-- Each monthly partition named: raw_data.transactions_YYYY_MM
CREATE TABLE IF NOT EXISTS raw_data.transactions (
    id                          UUID          NOT NULL DEFAULT uuid_generate_v4(),
    transaction_id              VARCHAR(80)   NOT NULL,
    customer_id                 VARCHAR(20)   NOT NULL,
    account_id                  VARCHAR(40)   NOT NULL,
    transaction_date            VARCHAR(30),
    transaction_type            VARCHAR(30),
    amount                      NUMERIC(18,2) CHECK (amount > 0),
    currency                    VARCHAR(5),
    risk_flags                  JSONB,
    source_system               VARCHAR(30),
    meta_counterparty           VARCHAR(255),
    meta_counterparty_type      VARCHAR(30),
    meta_location               VARCHAR(255),
    meta_country                VARCHAR(100),
    meta_country_code           VARCHAR(5),
    meta_destination_country    VARCHAR(5),
    meta_origin_country         VARCHAR(5),
    meta_source                 VARCHAR(50),
    ingestion_id                UUID,
    source_file                 VARCHAR(512),
    batch_id                    VARCHAR(100),
    is_valid                    BOOLEAN       NOT NULL DEFAULT TRUE,
    validation_errors           JSONB,
    created_at                  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_raw_txn_id UNIQUE (transaction_id, created_at)
) PARTITION BY RANGE (created_at);

-- Default partition catches anything outside explicit monthly ranges
CREATE TABLE IF NOT EXISTS raw_data.transactions_default
    PARTITION OF raw_data.transactions DEFAULT;

-- Rejected / quarantine records
CREATE TABLE IF NOT EXISTS raw_data.rejected_records (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type         VARCHAR(30)   NOT NULL,
    source_id           VARCHAR(100),
    ingestion_id        UUID,
    batch_id            VARCHAR(100),
    raw_payload         JSONB         NOT NULL,
    validation_errors   JSONB         NOT NULL,
    rejection_reason    TEXT,
    reprocessed         BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- ============================================================
-- SCHEMA: warehouse
-- Normalization: 3NF / BCNF
-- Lookup tables eliminate transitive dependencies.
-- SCD Type 2 on customers (wh_valid_from / wh_valid_to / wh_is_current).
-- ============================================================

-- Lookup: Countries (3NF — removes country_name ↔ is_high_risk redundancy)
CREATE TABLE IF NOT EXISTS warehouse.countries (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code            VARCHAR(5)  NOT NULL,
    name            VARCHAR(100),
    is_high_risk    BOOLEAN     NOT NULL DEFAULT FALSE,
    fatf_category   VARCHAR(50),
    region          VARCHAR(50),
    CONSTRAINT uq_country_code UNIQUE (code)
);

-- Lookup: Currencies (3NF — ISO 4217 attributes normalized)
CREATE TABLE IF NOT EXISTS warehouse.currencies (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code            VARCHAR(5)   NOT NULL,
    name            VARCHAR(100),
    symbol          VARCHAR(10),
    decimal_places  SMALLINT,
    CONSTRAINT uq_currency_code UNIQUE (code)
);

-- Lookup: KYC Statuses
CREATE TABLE IF NOT EXISTS warehouse.kyc_statuses (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    status_code         VARCHAR(20) NOT NULL,
    description         VARCHAR(255),
    requires_renewal    BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_kyc_status_code UNIQUE (status_code)
);

-- Lookup: Risk Levels (ordinal with score boundaries)
CREATE TABLE IF NOT EXISTS warehouse.risk_levels (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    level_code      VARCHAR(20)  NOT NULL,
    ordinal_rank    SMALLINT     NOT NULL,
    min_score       NUMERIC(6,2) NOT NULL,
    max_score       NUMERIC(6,2) NOT NULL,
    CONSTRAINT uq_risk_level_code UNIQUE (level_code),
    CONSTRAINT chk_risk_score_range CHECK (min_score < max_score)
);

-- Warehouse customers (SCD Type 2)
CREATE TABLE IF NOT EXISTS warehouse.customers (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id             VARCHAR(20)      NOT NULL,
    full_name               VARCHAR(255)     NOT NULL,
    email                   VARCHAR(255)     NOT NULL,
    phone                   VARCHAR(60),
    date_of_birth           DATE,
    country_id              UUID             REFERENCES warehouse.countries(id),
    residency_country_id    UUID             REFERENCES warehouse.countries(id),
    kyc_status_id           UUID             REFERENCES warehouse.kyc_statuses(id),
    kyc_last_review         DATE,
    pep_flag                BOOLEAN          NOT NULL DEFAULT FALSE,
    sanctions_flag          BOOLEAN          NOT NULL DEFAULT FALSE,
    adverse_media_flag      BOOLEAN          NOT NULL DEFAULT FALSE,
    risk_level_id           UUID             REFERENCES warehouse.risk_levels(id),
    risk_score              NUMERIC(8,4)     NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    customer_type           VARCHAR(30)      NOT NULL,
    -- SCD Type 2 versioning
    wh_valid_from           TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    wh_valid_to             TIMESTAMPTZ,
    wh_is_current           BOOLEAN          NOT NULL DEFAULT TRUE,
    raw_customer_id         UUID,
    -- Soft delete
    is_deleted              BOOLEAN          NOT NULL DEFAULT FALSE,
    deleted_at              TIMESTAMPTZ,
    created_at              TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_wh_cust_scd2 UNIQUE (customer_id, wh_valid_from),
    CONSTRAINT chk_wh_scd2_dates CHECK (wh_valid_to IS NULL OR wh_valid_to > wh_valid_from)
);

-- Warehouse accounts
CREATE TABLE IF NOT EXISTS warehouse.accounts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id      VARCHAR(40)  NOT NULL,
    customer_id     UUID         NOT NULL REFERENCES warehouse.customers(id) ON DELETE RESTRICT,
    account_type    VARCHAR(30)  NOT NULL,
    account_status  VARCHAR(20)  NOT NULL,
    currency_id     UUID         REFERENCES warehouse.currencies(id),
    balance         NUMERIC(18,2) NOT NULL,
    opened_date     DATE,
    raw_account_id  UUID,
    is_deleted      BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_wh_account_id UNIQUE (account_id)
);

-- Warehouse transactions
CREATE TABLE IF NOT EXISTS warehouse.transactions (
    id                          UUID NOT NULL DEFAULT uuid_generate_v4(),
    transaction_id              VARCHAR(80)   NOT NULL,
    customer_id                 UUID          NOT NULL REFERENCES warehouse.customers(id),
    account_id                  UUID          NOT NULL REFERENCES warehouse.accounts(id),
    transaction_date            TIMESTAMPTZ,
    transaction_type            VARCHAR(30)   NOT NULL,
    amount                      NUMERIC(18,2) NOT NULL CHECK (amount > 0),
    currency_id                 UUID          REFERENCES warehouse.currencies(id),
    risk_flags                  JSONB,
    source_system               VARCHAR(30),
    meta_counterparty           VARCHAR(255),
    meta_counterparty_type      VARCHAR(30),
    meta_country_id             UUID          REFERENCES warehouse.countries(id),
    meta_destination_country_id UUID          REFERENCES warehouse.countries(id),
    meta_origin_country_id      UUID          REFERENCES warehouse.countries(id),
    is_outlier                  BOOLEAN       NOT NULL DEFAULT FALSE,
    raw_transaction_id          UUID,
    created_at                  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_wh_txn_id UNIQUE (transaction_id, transaction_date)
) PARTITION BY RANGE (transaction_date);

CREATE TABLE IF NOT EXISTS warehouse.transactions_default
    PARTITION OF warehouse.transactions DEFAULT;

-- ============================================================
-- SCHEMA: metadata  (pipeline execution tracking)
-- ============================================================

CREATE TABLE IF NOT EXISTS metadata.pipeline_executions (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    execution_id            VARCHAR(50)     NOT NULL UNIQUE,
    pipeline_name           VARCHAR(100)    NOT NULL,
    pipeline_version        VARCHAR(20)     NOT NULL,
    schema_version          VARCHAR(20),
    source                  VARCHAR(255),
    source_format           VARCHAR(20),
    status                  VARCHAR(20)     NOT NULL DEFAULT 'RUNNING',
    started_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    finished_at             TIMESTAMPTZ,
    duration_seconds        FLOAT,
    rows_ingested           INTEGER,
    rows_valid              INTEGER,
    rows_rejected           INTEGER,
    rows_inserted           INTEGER,
    rows_updated            INTEGER,
    duplicates_removed      INTEGER,
    outliers_flagged        INTEGER,
    missing_values_filled   INTEGER,
    quality_score           FLOAT,
    error_message           TEXT,
    config_snapshot         JSONB,
    triggered_by            VARCHAR(100),
    host                    VARCHAR(100),
    peak_memory_mb          FLOAT,
    avg_cpu_percent         FLOAT,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS metadata.transformation_history (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    execution_id            VARCHAR(50)     NOT NULL,
    step_order              SMALLINT        NOT NULL,
    entity_type             VARCHAR(30)     NOT NULL,
    transformation_name     VARCHAR(100)    NOT NULL,
    transformation_type     VARCHAR(50),
    columns_affected        JSONB,
    parameters              JSONB,
    rows_before             INTEGER,
    rows_after              INTEGER,
    duration_seconds        FLOAT,
    status                  VARCHAR(20),
    notes                   TEXT,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ============================================================
-- SCHEMA: audit  (immutable, INSERT-only)
-- ============================================================

CREATE TABLE IF NOT EXISTS audit.audit_logs (
    id              UUID NOT NULL DEFAULT uuid_generate_v4(),
    entity_type     VARCHAR(50)     NOT NULL,
    record_id       VARCHAR(100)    NOT NULL,
    operation       VARCHAR(10)     NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE','UPSERT')),
    old_values      JSONB,
    new_values      JSONB,
    changed_columns JSONB,
    event_timestamp TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    performed_by    VARCHAR(100),
    execution_id    VARCHAR(50),
    db_user         VARCHAR(100)    DEFAULT current_user,
    client_ip       VARCHAR(45)
) PARTITION BY RANGE (event_timestamp);

CREATE TABLE IF NOT EXISTS audit.audit_logs_default
    PARTITION OF audit.audit_logs DEFAULT;

-- ============================================================
-- SCHEMA: logs
-- ============================================================

CREATE TABLE IF NOT EXISTS logs.pipeline_logs (
    id              UUID NOT NULL DEFAULT uuid_generate_v4(),
    execution_id    VARCHAR(50),
    level           VARCHAR(10)     NOT NULL,
    stage           VARCHAR(50),
    message         TEXT            NOT NULL,
    details         JSONB,
    log_timestamp   TIMESTAMPTZ     NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (log_timestamp);

CREATE TABLE IF NOT EXISTS logs.pipeline_logs_default
    PARTITION OF logs.pipeline_logs DEFAULT;

-- ============================================================
-- SCHEMA: feature_store
-- ============================================================

CREATE TABLE IF NOT EXISTS feature_store.feature_definitions (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    feature_name            VARCHAR(100)    NOT NULL,
    version                 VARCHAR(20)     NOT NULL DEFAULT '1.0.0',
    entity_type             VARCHAR(30)     NOT NULL,
    description             TEXT,
    feature_type            VARCHAR(30),
    source_columns          JSONB,
    transformation_logic    TEXT,
    owner                   VARCHAR(100),
    tags                    JSONB,
    statistics              JSONB,
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_feature_version UNIQUE (feature_name, version)
);

CREATE TABLE IF NOT EXISTS feature_store.feature_sets (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    set_name        VARCHAR(100)    NOT NULL,
    version         VARCHAR(20)     NOT NULL,
    description     TEXT,
    feature_ids     JSONB           NOT NULL,
    execution_id    VARCHAR(50),
    row_count       INTEGER,
    dataset_type    VARCHAR(20)     CHECK (dataset_type IN ('training','validation','inference')),
    quality_score   FLOAT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_featureset_version UNIQUE (set_name, version)
);

CREATE TABLE IF NOT EXISTS feature_store.customer_features (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id                 VARCHAR(20)     NOT NULL,
    feature_set_version         VARCHAR(20)     NOT NULL,
    risk_level_encoded          FLOAT,
    kyc_status_encoded          FLOAT,
    customer_type_encoded       FLOAT,
    risk_score_scaled           FLOAT,
    account_count               INTEGER,
    total_balance_scaled        FLOAT,
    pep_flag                    SMALLINT,
    sanctions_flag              SMALLINT,
    adverse_media_flag          SMALLINT,
    is_high_risk_country        SMALLINT,
    txn_count_30d               INTEGER,
    txn_amount_sum_30d          FLOAT,
    txn_amount_avg_30d          FLOAT,
    high_value_txn_count        INTEGER,
    unique_countries_count      INTEGER,
    feature_vector              JSONB,
    label_aml_risk              SMALLINT,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cust_feat_version UNIQUE (customer_id, feature_set_version)
);

CREATE TABLE IF NOT EXISTS feature_store.transaction_features (
    id                          UUID NOT NULL DEFAULT uuid_generate_v4(),
    transaction_id              VARCHAR(80)     NOT NULL,
    customer_id                 VARCHAR(20)     NOT NULL,
    account_id                  VARCHAR(40)     NOT NULL,
    feature_set_version         VARCHAR(20)     NOT NULL,
    transaction_date            TIMESTAMPTZ,
    txn_year                    SMALLINT,
    txn_month                   SMALLINT,
    txn_day                     SMALLINT,
    txn_dayofweek               SMALLINT,
    txn_quarter                 SMALLINT,
    txn_is_weekend              SMALLINT,
    amount_scaled               FLOAT,
    amount_lag_1                FLOAT,
    amount_lag_3                FLOAT,
    amount_lag_7                FLOAT,
    amount_rolling_7_mean       FLOAT,
    amount_rolling_30_mean      FLOAT,
    amount_rolling_30_std       FLOAT,
    is_high_value               SMALLINT,
    is_high_risk_country        SMALLINT,
    txn_type_encoded            FLOAT,
    feature_vector              JSONB,
    label_suspicious            SMALLINT,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_txn_feat_version UNIQUE (transaction_id, feature_set_version, transaction_date)
) PARTITION BY RANGE (transaction_date);

CREATE TABLE IF NOT EXISTS feature_store.transaction_features_default
    PARTITION OF feature_store.transaction_features DEFAULT;

-- ============================================================
-- SCHEMA: ml  (model registry)
-- ============================================================

CREATE TABLE IF NOT EXISTS ml.model_registry (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_name          VARCHAR(100)    NOT NULL,
    version             VARCHAR(20)     NOT NULL,
    algorithm           VARCHAR(100),
    framework           VARCHAR(50),
    feature_set_id      UUID            REFERENCES feature_store.feature_sets(id),
    training_execution  VARCHAR(50),
    metrics             JSONB,
    hyperparameters     JSONB,
    artifact_path       VARCHAR(512),
    status              VARCHAR(20)     DEFAULT 'REGISTERED',
    deployed_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_model_version UNIQUE (model_name, version)
);

CREATE TABLE IF NOT EXISTS ml.inference_results (
    id                  UUID NOT NULL DEFAULT uuid_generate_v4(),
    model_id            UUID            REFERENCES ml.model_registry(id),
    entity_type         VARCHAR(30)     NOT NULL,
    entity_id           VARCHAR(100)    NOT NULL,
    prediction_score    FLOAT,
    prediction_label    INTEGER,
    confidence          FLOAT,
    feature_snapshot    JSONB,
    inferred_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (inferred_at);

CREATE TABLE IF NOT EXISTS ml.inference_results_default
    PARTITION OF ml.inference_results DEFAULT;
