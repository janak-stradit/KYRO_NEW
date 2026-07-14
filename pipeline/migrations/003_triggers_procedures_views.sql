-- ============================================================
-- KYRO AML — Triggers, Functions & Stored Procedures
-- ============================================================

-- ── 1. Auto-update updated_at on any table that has it ───────
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

-- Apply to all warehouse tables
DO $$
DECLARE
    t RECORD;
BEGIN
    FOR t IN
        SELECT schemaname, tablename
        FROM pg_tables
        WHERE schemaname IN ('raw_data','warehouse','feature_store','metadata','ml')
          AND tablename NOT LIKE '%_default'
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_set_updated_at ON %I.%I;
             CREATE TRIGGER trg_set_updated_at
             BEFORE UPDATE ON %I.%I
             FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();',
            t.schemaname, t.tablename,
            t.schemaname, t.tablename
        );
    END LOOP;
END;
$$;

-- ── 2. Immutable audit trigger (fires on INSERT/UPDATE/DELETE) ─
CREATE OR REPLACE FUNCTION audit.record_audit()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_old       JSONB := NULL;
    v_new       JSONB := NULL;
    v_changed   JSONB := NULL;
    v_op        TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_op  := 'INSERT';
        v_new := to_jsonb(NEW);
    ELSIF TG_OP = 'UPDATE' THEN
        v_op    := 'UPDATE';
        v_old   := to_jsonb(OLD);
        v_new   := to_jsonb(NEW);
        -- Only store keys where value actually changed
        SELECT jsonb_object_agg(key, value)
        INTO v_changed
        FROM jsonb_each(v_new)
        WHERE v_new->key IS DISTINCT FROM v_old->key;
    ELSIF TG_OP = 'DELETE' THEN
        v_op  := 'DELETE';
        v_old := to_jsonb(OLD);
    END IF;

    INSERT INTO audit.audit_logs (
        entity_type, record_id, operation,
        old_values, new_values, changed_columns,
        event_timestamp, db_user
    ) VALUES (
        TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
        COALESCE((v_new->>'id'), (v_old->>'id')),
        v_op,
        v_old, v_new, v_changed,
        NOW(), current_user
    );

    RETURN COALESCE(NEW, OLD);
END;
$$;

-- Apply audit trigger to warehouse core tables
CREATE OR REPLACE FUNCTION audit.attach_audit_triggers() RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['warehouse.customers','warehouse.accounts','warehouse.transactions']
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_audit ON %s;
             CREATE TRIGGER trg_audit
             AFTER INSERT OR UPDATE OR DELETE ON %s
             FOR EACH ROW EXECUTE FUNCTION audit.record_audit();',
            t, t
        );
    END LOOP;
END;
$$;

SELECT audit.attach_audit_triggers();

-- ── 3. Risk level consistency enforcement trigger ─────────────
CREATE OR REPLACE FUNCTION warehouse.enforce_risk_consistency()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    expected_level VARCHAR(20);
BEGIN
    expected_level := CASE
        WHEN NEW.risk_score >= 66 THEN 'HIGH'
        WHEN NEW.risk_score >= 33 THEN 'MEDIUM'
        ELSE 'LOW'
    END;
    -- Resolve level_code from risk_levels lookup
    IF NOT EXISTS (
        SELECT 1 FROM warehouse.risk_levels
        WHERE id = NEW.risk_level_id AND level_code = expected_level
    ) THEN
        RAISE WARNING 'Risk score %.4f does not match risk level for customer %s. Auto-correcting.',
            NEW.risk_score, NEW.customer_id;
        SELECT id INTO NEW.risk_level_id
        FROM warehouse.risk_levels WHERE level_code = expected_level;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_risk_consistency ON warehouse.customers;
CREATE TRIGGER trg_risk_consistency
BEFORE INSERT OR UPDATE ON warehouse.customers
FOR EACH ROW EXECUTE FUNCTION warehouse.enforce_risk_consistency();

-- ── 4. SCD Type 2 expire procedure ───────────────────────────
CREATE OR REPLACE PROCEDURE warehouse.expire_customer_scd2(
    p_customer_id VARCHAR,
    p_expired_at  TIMESTAMPTZ DEFAULT NOW()
)
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE warehouse.customers
    SET wh_valid_to  = p_expired_at,
        wh_is_current = FALSE,
        updated_at   = NOW()
    WHERE customer_id = p_customer_id
      AND wh_is_current = TRUE;
END;
$$;

-- ── 5. Pipeline execution logging procedure ───────────────────
CREATE OR REPLACE PROCEDURE metadata.log_execution(
    p_execution_id  VARCHAR,
    p_pipeline      VARCHAR,
    p_version       VARCHAR,
    p_source        VARCHAR DEFAULT NULL
)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO metadata.pipeline_executions (
        execution_id, pipeline_name, pipeline_version, source, status, started_at
    ) VALUES (
        p_execution_id, p_pipeline, p_version, p_source, 'RUNNING', NOW()
    )
    ON CONFLICT (execution_id) DO NOTHING;
END;
$$;

CREATE OR REPLACE PROCEDURE metadata.complete_execution(
    p_execution_id  VARCHAR,
    p_status        VARCHAR,
    p_rows_inserted INTEGER DEFAULT 0,
    p_quality_score FLOAT   DEFAULT NULL,
    p_error_msg     TEXT    DEFAULT NULL
)
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE metadata.pipeline_executions SET
        status          = p_status,
        finished_at     = NOW(),
        duration_seconds= EXTRACT(EPOCH FROM (NOW() - started_at)),
        rows_inserted   = p_rows_inserted,
        quality_score   = p_quality_score,
        error_message   = p_error_msg,
        updated_at      = NOW()
    WHERE execution_id = p_execution_id;
END;
$$;

-- ── 6. Data retention / cleanup procedure ─────────────────────
CREATE OR REPLACE PROCEDURE logs.purge_old_logs(p_retention_days INTEGER DEFAULT 90)
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM logs.pipeline_logs
    WHERE log_timestamp < NOW() - (p_retention_days || ' days')::INTERVAL;

    DELETE FROM audit.audit_logs
    WHERE event_timestamp < NOW() - (p_retention_days * 3 || ' days')::INTERVAL;  -- 3x retention for audit

    RAISE NOTICE 'Log purge complete: logs older than % days removed.', p_retention_days;
END;
$$;

-- ── 7. Materialized view: customer risk summary ───────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.customer_risk_summary AS
SELECT
    c.customer_id,
    c.full_name,
    c.email,
    rl.level_code                                           AS risk_level,
    c.risk_score,
    c.pep_flag,
    c.sanctions_flag,
    c.adverse_media_flag,
    ks.status_code                                          AS kyc_status,
    COUNT(DISTINCT a.id)                                    AS account_count,
    SUM(a.balance)                                          AS total_balance,
    COUNT(DISTINCT t.id)                                    AS total_transactions,
    SUM(t.amount)                                           AS total_txn_volume,
    MAX(t.transaction_date)                                 AS last_transaction_date,
    COUNT(DISTINCT t.id) FILTER (WHERE t.amount > 10000)    AS high_value_txn_count
FROM warehouse.customers c
LEFT JOIN warehouse.risk_levels  rl ON c.risk_level_id  = rl.id
LEFT JOIN warehouse.kyc_statuses ks ON c.kyc_status_id  = ks.id
LEFT JOIN warehouse.accounts     a  ON a.customer_id    = c.id AND NOT a.is_deleted
LEFT JOIN warehouse.transactions t  ON t.customer_id    = c.id
WHERE c.wh_is_current = TRUE AND NOT c.is_deleted
GROUP BY c.id, c.customer_id, c.full_name, c.email, rl.level_code,
         c.risk_score, c.pep_flag, c.sanctions_flag, c.adverse_media_flag, ks.status_code
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS uix_cust_risk_summary
    ON analytics.customer_risk_summary (customer_id);

-- ── 8. Materialized view: transaction velocity per customer ───
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.txn_velocity_30d AS
SELECT
    t.customer_id,
    c.customer_id   AS customer_natural_id,
    COUNT(*)        AS txn_count_30d,
    SUM(t.amount)   AS txn_volume_30d,
    AVG(t.amount)   AS avg_txn_amount_30d,
    MAX(t.amount)   AS max_txn_amount_30d,
    COUNT(DISTINCT cu.code) AS unique_currencies_30d
FROM warehouse.transactions  t
JOIN warehouse.customers      c  ON t.customer_id  = c.id AND c.wh_is_current = TRUE
LEFT JOIN warehouse.currencies cu ON t.currency_id = cu.id
WHERE t.transaction_date >= NOW() - INTERVAL '30 days'
GROUP BY t.customer_id, c.customer_id
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS uix_txn_velocity_30d
    ON analytics.txn_velocity_30d (customer_id);

-- Refresh helper procedure
CREATE OR REPLACE PROCEDURE analytics.refresh_all_views()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.customer_risk_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.txn_velocity_30d;
    RAISE NOTICE 'All materialized views refreshed at %', NOW();
END;
$$;

-- ── 9. ML Feature views ───────────────────────────────────────
CREATE OR REPLACE VIEW ml.v_customer_ml_features AS
SELECT
    cf.*,
    c.customer_type,
    rl.level_code AS risk_level_label
FROM feature_store.customer_features cf
JOIN warehouse.customers  c  ON cf.customer_id = c.customer_id AND c.wh_is_current = TRUE
JOIN warehouse.risk_levels rl ON c.risk_level_id = rl.id;

CREATE OR REPLACE VIEW ml.v_transaction_ml_features AS
SELECT
    tf.*,
    c.risk_score,
    c.pep_flag,
    c.sanctions_flag,
    rl.level_code AS customer_risk_level
FROM feature_store.transaction_features tf
JOIN warehouse.customers   c  ON tf.customer_id = c.customer_id AND c.wh_is_current = TRUE
JOIN warehouse.risk_levels rl ON c.risk_level_id = rl.id;
