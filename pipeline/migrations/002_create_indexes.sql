-- ============================================================
-- KYRO AML — Index Strategy Script
-- ============================================================
-- Each index is explained below. Indexes are tuned to AML query patterns:
--   - Risk/compliance dashboards (filter by risk_level, kyc_status, flags)
--   - Time-range transaction queries (BRIN on date columns)
--   - JSONB risk_flags queries (GIN)
--   - Full-text search on counterparty/name (GIN + pg_trgm)
--   - Aggregation by customer/account (composite B-Tree)
-- ============================================================

-- ── raw_data.customers ────────────────────────────────────────
-- B-Tree on natural business key (most frequent join target)
CREATE INDEX IF NOT EXISTS ix_raw_cust_customer_id   ON raw_data.customers (customer_id);
-- Compliance dashboard filter
CREATE INDEX IF NOT EXISTS ix_raw_cust_risk_level     ON raw_data.customers (risk_level);
CREATE INDEX IF NOT EXISTS ix_raw_cust_kyc_status     ON raw_data.customers (kyc_status);
CREATE INDEX IF NOT EXISTS ix_raw_cust_country        ON raw_data.customers (country);
-- Partial index: only active-pipeline records (avoids scanning invalid rows)
CREATE INDEX IF NOT EXISTS ix_raw_cust_valid          ON raw_data.customers (customer_id) WHERE is_valid = TRUE;
-- Ingestion batching lookup
CREATE INDEX IF NOT EXISTS ix_raw_cust_ingestion_id   ON raw_data.customers (ingestion_id);
-- Timestamp (BRIN is efficient for monotonically inserted rows, low overhead)
CREATE INDEX IF NOT EXISTS ix_raw_cust_created_brin   ON raw_data.customers USING BRIN (created_at);

-- ── raw_data.accounts ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_raw_acc_account_id      ON raw_data.accounts (account_id);
CREATE INDEX IF NOT EXISTS ix_raw_acc_customer_id     ON raw_data.accounts (customer_id);
CREATE INDEX IF NOT EXISTS ix_raw_acc_status          ON raw_data.accounts (account_status);
-- Composite: customer + status (common dashboard filter)
CREATE INDEX IF NOT EXISTS ix_raw_acc_cust_status     ON raw_data.accounts (customer_id, account_status);
CREATE INDEX IF NOT EXISTS ix_raw_acc_created_brin    ON raw_data.accounts USING BRIN (created_at);

-- ── raw_data.transactions ─────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_raw_txn_transaction_id  ON raw_data.transactions (transaction_id);
CREATE INDEX IF NOT EXISTS ix_raw_txn_customer_id     ON raw_data.transactions (customer_id);
CREATE INDEX IF NOT EXISTS ix_raw_txn_account_id      ON raw_data.transactions (account_id);
CREATE INDEX IF NOT EXISTS ix_raw_txn_type            ON raw_data.transactions (transaction_type);
-- BRIN: very efficient for large append-only tables on monotone date columns
CREATE INDEX IF NOT EXISTS ix_raw_txn_created_brin    ON raw_data.transactions USING BRIN (created_at);
-- GIN on JSONB risk_flags: supports @> containment queries e.g. WHERE risk_flags @> '["HIGH_VALUE"]'
CREATE INDEX IF NOT EXISTS ix_raw_txn_risk_flags_gin  ON raw_data.transactions USING GIN (risk_flags);
-- GIN + pg_trgm: fuzzy counterparty name search (AML analyst use-case)
CREATE INDEX IF NOT EXISTS ix_raw_txn_counterparty_trgm
    ON raw_data.transactions USING GIN (meta_counterparty gin_trgm_ops);
-- Composite: account + type for per-account transaction type breakdown
CREATE INDEX IF NOT EXISTS ix_raw_txn_acc_type        ON raw_data.transactions (account_id, transaction_type);
-- Partial: only suspicious transactions (sparse index = very fast)
CREATE INDEX IF NOT EXISTS ix_raw_txn_high_amount
    ON raw_data.transactions (amount) WHERE amount > 10000;

-- ── raw_data.rejected_records ─────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_rejected_entity         ON raw_data.rejected_records (entity_type);
CREATE INDEX IF NOT EXISTS ix_rejected_ingestion      ON raw_data.rejected_records (ingestion_id);
CREATE INDEX IF NOT EXISTS ix_rejected_reprocessed    ON raw_data.rejected_records (reprocessed) WHERE reprocessed = FALSE;

-- ── warehouse.customers ───────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_wh_cust_customer_id     ON warehouse.customers (customer_id);
-- Partial: current SCD-2 version only (most queries only need current)
CREATE INDEX IF NOT EXISTS ix_wh_cust_current         ON warehouse.customers (customer_id) WHERE wh_is_current = TRUE;
CREATE INDEX IF NOT EXISTS ix_wh_cust_risk_level      ON warehouse.customers (risk_level_id);
CREATE INDEX IF NOT EXISTS ix_wh_cust_kyc_status      ON warehouse.customers (kyc_status_id);
CREATE INDEX IF NOT EXISTS ix_wh_cust_pep             ON warehouse.customers (customer_id) WHERE pep_flag = TRUE;
CREATE INDEX IF NOT EXISTS ix_wh_cust_sanctioned      ON warehouse.customers (customer_id) WHERE sanctions_flag = TRUE;
-- Composite: country + risk (geo-risk dashboard)
CREATE INDEX IF NOT EXISTS ix_wh_cust_country_risk    ON warehouse.customers (country_id, risk_level_id) WHERE wh_is_current = TRUE;
CREATE INDEX IF NOT EXISTS ix_wh_cust_valid_from_brin ON warehouse.customers USING BRIN (wh_valid_from);

-- ── warehouse.accounts ────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_wh_acc_account_id       ON warehouse.accounts (account_id);
CREATE INDEX IF NOT EXISTS ix_wh_acc_customer_id      ON warehouse.accounts (customer_id);
CREATE INDEX IF NOT EXISTS ix_wh_acc_status           ON warehouse.accounts (account_status);
CREATE INDEX IF NOT EXISTS ix_wh_acc_currency         ON warehouse.accounts (currency_id);
-- Composite: customer + status (account portfolio view)
CREATE INDEX IF NOT EXISTS ix_wh_acc_cust_status      ON warehouse.accounts (customer_id, account_status);

-- ── warehouse.transactions ────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_wh_txn_transaction_id   ON warehouse.transactions (transaction_id);
CREATE INDEX IF NOT EXISTS ix_wh_txn_customer_id      ON warehouse.transactions (customer_id);
CREATE INDEX IF NOT EXISTS ix_wh_txn_account_id       ON warehouse.transactions (account_id);
CREATE INDEX IF NOT EXISTS ix_wh_txn_type             ON warehouse.transactions (transaction_type);
CREATE INDEX IF NOT EXISTS ix_wh_txn_amount           ON warehouse.transactions (amount);
CREATE INDEX IF NOT EXISTS ix_wh_txn_date_brin        ON warehouse.transactions USING BRIN (transaction_date);
CREATE INDEX IF NOT EXISTS ix_wh_txn_risk_flags_gin   ON warehouse.transactions USING GIN (risk_flags);
-- Composite: customer + date (transaction history per customer)
CREATE INDEX IF NOT EXISTS ix_wh_txn_cust_date        ON warehouse.transactions (customer_id, transaction_date DESC);
-- Partial: only outlier transactions
CREATE INDEX IF NOT EXISTS ix_wh_txn_outlier          ON warehouse.transactions (customer_id) WHERE is_outlier = TRUE;

-- ── metadata.pipeline_executions ─────────────────────────────
CREATE INDEX IF NOT EXISTS ix_meta_exec_execution_id  ON metadata.pipeline_executions (execution_id);
CREATE INDEX IF NOT EXISTS ix_meta_exec_status        ON metadata.pipeline_executions (status);
CREATE INDEX IF NOT EXISTS ix_meta_exec_started_brin  ON metadata.pipeline_executions USING BRIN (started_at);

-- ── metadata.transformation_history ──────────────────────────
CREATE INDEX IF NOT EXISTS ix_txhist_exec_id          ON metadata.transformation_history (execution_id);
CREATE INDEX IF NOT EXISTS ix_txhist_entity           ON metadata.transformation_history (entity_type);

-- ── audit.audit_logs ──────────────────────────────────────────
-- GIN on old_values/new_values: supports JSONB field-level queries
CREATE INDEX IF NOT EXISTS ix_audit_entity            ON audit.audit_logs (entity_type);
CREATE INDEX IF NOT EXISTS ix_audit_record_id         ON audit.audit_logs (record_id);
CREATE INDEX IF NOT EXISTS ix_audit_operation         ON audit.audit_logs (operation);
CREATE INDEX IF NOT EXISTS ix_audit_ts_brin           ON audit.audit_logs USING BRIN (event_timestamp);
CREATE INDEX IF NOT EXISTS ix_audit_exec_id           ON audit.audit_logs (execution_id);

-- ── logs.pipeline_logs ────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_plog_exec_id            ON logs.pipeline_logs (execution_id);
CREATE INDEX IF NOT EXISTS ix_plog_level              ON logs.pipeline_logs (level);
CREATE INDEX IF NOT EXISTS ix_plog_ts_brin            ON logs.pipeline_logs USING BRIN (log_timestamp);

-- ── feature_store.customer_features ──────────────────────────
CREATE INDEX IF NOT EXISTS ix_cust_feat_customer_id   ON feature_store.customer_features (customer_id);
CREATE INDEX IF NOT EXISTS ix_cust_feat_risk          ON feature_store.customer_features (risk_score_scaled DESC);
CREATE INDEX IF NOT EXISTS ix_cust_feat_label         ON feature_store.customer_features (label_aml_risk) WHERE label_aml_risk = 1;

-- ── feature_store.transaction_features ───────────────────────
CREATE INDEX IF NOT EXISTS ix_txn_feat_customer_id    ON feature_store.transaction_features (customer_id);
CREATE INDEX IF NOT EXISTS ix_txn_feat_account_id     ON feature_store.transaction_features (account_id);
CREATE INDEX IF NOT EXISTS ix_txn_feat_date_brin      ON feature_store.transaction_features USING BRIN (transaction_date);
CREATE INDEX IF NOT EXISTS ix_txn_feat_suspicious     ON feature_store.transaction_features (customer_id) WHERE label_suspicious = 1;

-- ── ml.model_registry ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_ml_model_name           ON ml.model_registry (model_name, version);
CREATE INDEX IF NOT EXISTS ix_ml_model_status         ON ml.model_registry (status);

-- ── ml.inference_results ──────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_ml_inf_entity           ON ml.inference_results (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_ml_inf_model            ON ml.inference_results (model_id);
CREATE INDEX IF NOT EXISTS ix_ml_inf_ts_brin          ON ml.inference_results USING BRIN (inferred_at);
