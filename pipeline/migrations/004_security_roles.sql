-- ============================================================
-- KYRO AML — Security: Roles, Privileges, Row-Level Security
-- ============================================================

-- ── Create roles ──────────────────────────────────────────────
DO $$ BEGIN CREATE ROLE kyro_pipeline_writer;  EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE kyro_analyst_ro;        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE kyro_ml_user;           EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE kyro_audit_reader;      EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── kyro_pipeline_writer: full DML on pipeline schemas ───────
GRANT USAGE ON SCHEMA raw_data, staging, cleaned, warehouse,
               feature_store, metadata, logs, ml, analytics TO kyro_pipeline_writer;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA raw_data, staging, cleaned, warehouse TO kyro_pipeline_writer;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA feature_store, metadata, logs, ml TO kyro_pipeline_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA raw_data, warehouse, feature_store TO kyro_pipeline_writer;

-- ── kyro_analyst_ro: read-only on warehouse + analytics ──────
GRANT USAGE ON SCHEMA warehouse, analytics, feature_store, ml TO kyro_analyst_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA warehouse, analytics, feature_store, ml TO kyro_analyst_ro;

-- ── kyro_ml_user: read feature store + write inference results
GRANT USAGE ON SCHEMA feature_store, ml TO kyro_ml_user;
GRANT SELECT ON ALL TABLES IN SCHEMA feature_store TO kyro_ml_user;
GRANT SELECT, INSERT ON ml.model_registry, ml.inference_results TO kyro_ml_user;

-- ── kyro_audit_reader: read-only on audit + logs ─────────────
GRANT USAGE ON SCHEMA audit, logs, metadata TO kyro_audit_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA audit, logs, metadata TO kyro_audit_reader;

-- ── Revoke public access to sensitive schemas ─────────────────
REVOKE ALL ON SCHEMA raw_data, audit, metadata, logs FROM PUBLIC;

-- ── Alter default privileges for future tables ───────────────
ALTER DEFAULT PRIVILEGES IN SCHEMA warehouse
    GRANT SELECT ON TABLES TO kyro_analyst_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA feature_store
    GRANT SELECT ON TABLES TO kyro_ml_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit
    GRANT SELECT ON TABLES TO kyro_audit_reader;

-- ── Row-Level Security: analysts only see non-deleted customers
ALTER TABLE warehouse.customers ENABLE ROW LEVEL SECURITY;

CREATE POLICY customers_analyst_policy ON warehouse.customers
    FOR SELECT TO kyro_analyst_ro
    USING (NOT is_deleted AND wh_is_current = TRUE);

-- Pipeline writer sees all rows
CREATE POLICY customers_writer_policy ON warehouse.customers
    FOR ALL TO kyro_pipeline_writer
    USING (TRUE);

-- ── SSL: enforce SSL for all non-localhost connections ────────
-- Set in postgresql.conf:
--   ssl = on
--   ssl_cert_file = 'server.crt'
--   ssl_key_file  = 'server.key'
-- In pg_hba.conf:
--   hostssl all all 0.0.0.0/0 md5

-- ── Audit: log all connections ────────────────────────────────
-- Set in postgresql.conf:
--   log_connections = on
--   log_disconnections = on
--   log_statement = 'ddl'
--   log_min_duration_statement = 500
