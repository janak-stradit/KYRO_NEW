"""
pipeline/run_pipeline.py — Master pipeline orchestrator.
Ties all layers together: Ingest → Validate → Clean → Transform → Feature Eng → Quality → Load.
Implements full execution tracking, audit logging, checkpointing, and error recovery.
"""
from __future__ import annotations

import logging
import os
import platform
import time
import uuid
import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import psutil

from pipeline.core.config import load_config, get_raw_db_url
from pipeline.core.database import get_engine, create_schemas, with_retry
from pipeline.core.exceptions import DataQualityError, PipelineError
from pipeline.core.logging_setup import setup_logging, PipelineTimer, new_execution_id
from pipeline.ingestion.ingestor import from_dict_list, ingest
from pipeline.validation.validator import AMLValidator
from pipeline.cleaning.cleaner import clean_customers, clean_accounts, clean_transactions, handle_duplicates
from pipeline.cleaning.outlier_detector import handle_outliers
from pipeline.transformation.transformer import (
    scale_columns, label_encode, ordinal_encode, extract_date_features
)
from pipeline.feature_engineering.engineer import build_customer_features, build_transaction_features
from pipeline.quality.data_quality import DataQualityChecker
from pipeline.loaders.bulk_loader import upsert_dataframe, get_last_checkpoint
from pipeline.monitoring.monitor import PipelineMonitor, QualityAlertManager

logger = logging.getLogger("kyro.pipeline")


class AMLPipeline:
    """
    Production-grade AML ETL/ELT pipeline orchestrator.

    Pipeline stages:
        1. Ingest raw data from generator / file / API
        2. Validate all entities
        3. Clean and deduplicate
        4. Detect and handle outliers
        5. Transform (encode, scale, date features)
        6. Build ML feature vectors
        7. Data quality checks
        8. Load to PostgreSQL (raw_data.* → feature_store.*)
        9. Log execution metadata
    """

    # Columns produced during feature-engineering / transformation that do NOT
    # exist in raw_data.* tables — must be excluded before the raw_data upsert.
    _RAW_CUSTOMER_DROP = {
        "risk_score_scaled", "risk_level_encoded", "account_count", "total_balance",
        "avg_balance", "max_balance", "active_accounts", "txn_count", "txn_amount_total",
        "txn_amount_mean", "txn_amount_max", "txn_high_value_count", "unique_currencies",
        "flag_high_value", "flag_structuring", "flag_high_risk_country", "flag_pep",
        "flag_sanctioned", "flag_adverse_media", "flag_any_compliance_alert",
        "risk_score_rank", "country_frequency",
    }
    _RAW_ACCOUNT_DROP: set[str] = {
        "balance_scaled",
    }
    _RAW_TXN_DROP = {
        "amount_scaled", "txn_year", "txn_month", "txn_day", "txn_dayofweek",
        "txn_quarter", "txn_is_weekend", "flag_high_value", "flag_structuring",
        "flag_high_risk_country", "amount_lag_1", "amount_lag_3", "amount_lag_7",
        "amount_rolling_7_mean", "amount_rolling_7_std", "amount_rolling_30_mean",
        "amount_rolling_30_std", "amount_rank", "transaction_type_frequency",
        "flag_pep", "flag_sanctioned", "flag_adverse_media", "flag_any_compliance_alert",
    }

    # Columns the feature_store.customer_features table actually expects
    _CUST_FEAT_COLS = [
        "customer_id", "feature_set_version",
        "risk_score_scaled", "pep_flag", "sanctions_flag", "adverse_media_flag",
        "account_count", "feature_vector",
    ]
    # Columns the feature_store.transaction_features table actually expects
    _TXN_FEAT_COLS = [
        "transaction_id", "customer_id", "account_id", "feature_set_version",
        "transaction_date",
        "txn_year", "txn_month", "txn_day", "txn_dayofweek", "txn_quarter", "txn_is_weekend",
        "amount_lag_1", "amount_lag_3", "amount_lag_7",
        "amount_rolling_7_mean", "amount_rolling_30_mean", "amount_rolling_30_std",
        "feature_vector",
    ]

    def __init__(self, config: dict | None = None) -> None:
        self.cfg = config or load_config()
        self.execution_id = new_execution_id()
        self.validator = AMLValidator(self.cfg.get("validation", {}))
        self.quality_checker = DataQualityChecker(self.cfg.get("data_quality", {}))
        self.monitor = PipelineMonitor()
        self.alert_manager = QualityAlertManager(
            threshold=self.cfg.get("monitoring", {}).get("quality_threshold", 0.90),
            channels=self.cfg.get("monitoring", {}).get("alert_channels", ["log"])
        )
        self._stats: dict[str, Any] = {
            "execution_id": self.execution_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Public entry point ────────────────────────────────────

    def run(
        self,
        dataset: dict | None = None,
        source_path: str | None = None,
        source_format: str = "dict",
        incremental: bool = False,
    ) -> dict:
        """
        Execute the full pipeline.

        Args:
            dataset: Pre-generated dict with 'customers', 'accounts', 'transactions'.
            source_path: File path if loading from CSV/Excel/JSON.
            source_format: Format string.
            incremental: If True, use last watermark for incremental load.

        Returns:
            Execution stats dictionary.
        """
        setup_logging(
            level=self.cfg["logging"]["level"],
            log_file=self.cfg["logging"]["file"],
        )
        logger.info("=" * 60)
        logger.info("Pipeline START  execution_id=%s", self.execution_id)

        t_start = time.perf_counter()
        self.monitor.start()

        try:
            # Ensure all DB schemas exist
            with PipelineTimer("create_schemas", logger):
                create_schemas(self.cfg)
            self.monitor.sample()

            # ── Stage 1: Ingest ──────────────────────────────
            with PipelineTimer("ingestion", logger):
                customers_raw, accounts_raw, transactions_raw = self._ingest(
                    dataset, source_path, source_format
                )
            self.monitor.sample()

            self._stats.update({
                "rows_ingested_customers": len(customers_raw),
                "rows_ingested_accounts": len(accounts_raw),
                "rows_ingested_transactions": len(transactions_raw),
            })

            # ── Stage 2: Validate ────────────────────────────
            with PipelineTimer("validation", logger):
                customers_raw, accounts_raw, transactions_raw = self._validate(
                    customers_raw, accounts_raw, transactions_raw
                )
            self.monitor.sample()

            # ── Stage 3: Clean ───────────────────────────────
            with PipelineTimer("cleaning", logger):
                customers_clean, accounts_clean, transactions_clean = self._clean(
                    customers_raw, accounts_raw, transactions_raw
                )
            self.monitor.sample()

            # ── Stage 4: Outlier detection ───────────────────
            with PipelineTimer("outlier_detection", logger):
                transactions_clean = self._handle_outliers(transactions_clean)
            self.monitor.sample()

            # ── Stage 5: Transform ───────────────────────────
            with PipelineTimer("transformation", logger):
                customers_t, accounts_t, transactions_t = self._transform(
                    customers_clean, accounts_clean, transactions_clean
                )
            self.monitor.sample()

            # ── Stage 6: Feature Engineering ────────────────
            with PipelineTimer("feature_engineering", logger):
                customer_features = build_customer_features(customers_t, accounts_t, transactions_t)
                transaction_features = build_transaction_features(transactions_t)
            self.monitor.sample()

            # ── Stage 7: Data Quality ────────────────────────
            with PipelineTimer("quality_check", logger):
                self._quality_check(customers_clean, accounts_clean, transactions_clean)

            # ── Stage 8: Load to PostgreSQL ──────────────────
            with PipelineTimer("db_load", logger):
                self._load_to_db(
                    customers_t, accounts_t, transactions_t,
                    customer_features, transaction_features,
                )

            elapsed = time.perf_counter() - t_start
            self._stats["status"] = "SUCCESS"
            self._stats["duration_seconds"] = round(elapsed, 2)
            self._stats["finished_at"] = datetime.now(timezone.utc).isoformat()
            
            # Stop monitor and add metrics to stats
            monitor_metrics = self.monitor.stop()
            self._stats.update(monitor_metrics)

            # Persist execution metadata
            self._persist_execution_stats()

            logger.info("Pipeline COMPLETE  execution_id=%s  elapsed=%.2fs", self.execution_id, elapsed)
            logger.info("=" * 60)
            return self._stats

        except Exception as exc:
            self._stats["status"] = "FAILED"
            self._stats["error"] = str(exc)
            self._stats.update(self.monitor.stop())
            self._persist_execution_stats()
            logger.exception("Pipeline FAILED  execution_id=%s: %s", self.execution_id, exc)
            raise

    # ── Stage implementations ─────────────────────────────────

    def _ingest(self, dataset, source_path, source_format):
        if dataset:
            customers = from_dict_list(dataset.get("customers", []))
            accounts = from_dict_list(dataset.get("accounts", []))
            transactions = from_dict_list(dataset.get("transactions", []))
        elif source_path:
            # Multi-sheet Excel
            customers = ingest(source_path, source_format, sheet_name="Customer")
            accounts = ingest(source_path, source_format, sheet_name="Accounts")
            transactions = ingest(source_path, source_format, sheet_name="Transactions")
        else:
            raise PipelineError("Must provide either `dataset` or `source_path`")
        logger.info("Ingested: %d customers / %d accounts / %d transactions",
                    len(customers), len(accounts), len(transactions))
        return customers, accounts, transactions

    def _validate(self, customers, accounts, transactions):
        # 1. Null filling (fill instead of reject)
        for df in (customers, accounts, transactions):
            for col in df.columns:
                if df[col].dtype == "object":
                    df[col] = df[col].fillna("UNKNOWN")
                elif df[col].dtype == "bool":
                    df[col] = df[col].fillna(False)
                elif pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].fillna(df[col].median())
                elif pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = df[col].fillna(pd.Timestamp.now())

        # 2. Smart deduplication (keep latest instead of rejecting both)
        if "customer_id" in customers.columns:
            customers = customers.drop_duplicates(subset=["customer_id"], keep="last")
        if "account_id" in accounts.columns:
            accounts = accounts.drop_duplicates(subset=["account_id"], keep="last")
        if "transaction_id" in transactions.columns:
            transactions = transactions.drop_duplicates(subset=["transaction_id"], keep="last")

        results = []
        for df, entity in [(customers, "customers"), (accounts, "accounts"), (transactions, "transactions")]:
            valid, rejected, report = self.validator.validate(df, entity)
            self._stats[f"rejected_{entity}"] = len(rejected)
            logger.info("Validation [%s]: valid=%d rejected=%d pass_rate=%.2f%%",
                        entity, len(valid), len(rejected), report.pass_rate * 100)
            if not rejected.empty:
                self._store_rejected(rejected, entity)
            
            # Map valid records for raw_data insert
            if not valid.empty:
                valid = valid.copy()
                valid["is_valid"] = True
                valid["validation_errors"] = "[]"
                
            results.append(valid)
        return tuple(results)

    def _clean(self, customers, accounts, transactions):
        c = clean_customers(customers, self.cfg)
        a = clean_accounts(accounts, self.cfg)
        t = clean_transactions(transactions, self.cfg)
        dup_cfg = self.cfg.get("duplicates", {})
        c, _ = handle_duplicates(c, dup_cfg.get("customers", {}).get("business_keys", ["customer_id"]))
        a, _ = handle_duplicates(a, dup_cfg.get("accounts", {}).get("business_keys", ["account_id"]))
        t, _ = handle_duplicates(t, dup_cfg.get("transactions", {}).get("business_keys", ["transaction_id"]))
        self._stats["rows_after_cleaning"] = {
            "customers": len(c), "accounts": len(a), "transactions": len(t)
        }
        return c, a, t

    def _handle_outliers(self, transactions):
        if transactions.empty:
            return transactions
        out_cfg = self.cfg.get("outliers", {})
        cols = out_cfg.get("columns", {}).get("transactions", ["amount"])
        clean, removed, report = handle_outliers(
            transactions, cols,
            method=out_cfg.get("method", "iqr"),
            action=out_cfg.get("action", "winsorize"),
            iqr_multiplier=float(out_cfg.get("iqr_multiplier", 3.0)),
        )
        self._stats["outliers_report"] = report
        logger.info("Outlier handling: %d rows affected", len(removed))
        return clean

    def _transform(self, customers, accounts, transactions):
        t_cfg = self.cfg.get("transformations", {})
        scale_cfg = t_cfg.get("scaling", {})
        scale_method = scale_cfg.get("method", "robust")
        scale_cols = scale_cfg.get("columns", [])

        # Scale numeric columns
        if not customers.empty and "risk_score" in customers.columns:
            customers = scale_columns(customers, ["risk_score"], method=scale_method)
        if not accounts.empty and "balance" in accounts.columns:
            accounts = scale_columns(accounts, ["balance"], method=scale_method)
        if not transactions.empty and scale_cols and "amount" in transactions.columns:
            transactions = scale_columns(transactions, ["amount"], method=scale_method)

        # Ordinal encode risk_level
        if not customers.empty and "risk_level" in customers.columns:
            customers = ordinal_encode(customers, "risk_level", ["LOW", "MEDIUM", "HIGH"])

        # Date features
        if not transactions.empty and "transaction_date" in transactions.columns:
            transactions = extract_date_features(
                transactions, "transaction_date",
                ["year", "month", "day", "dayofweek", "quarter", "is_weekend"]
            )

        return customers, accounts, transactions

    def _quality_check(self, customers, accounts, transactions):
        for df, entity in [(customers, "customers"), (accounts, "accounts"), (transactions, "transactions")]:
            reference_df = df.sample(min(100, len(df))) if not df.empty else None
            report = self.quality_checker.check(df, entity, reference_df=reference_df)
            report_dict = report.to_dict()
            self._stats[f"quality_{entity}"] = report_dict
            self.alert_manager.check_and_alert(entity, report.overall_score, report_dict)
            if not report.passed:
                logger.warning("Quality check FAILED [%s]: score=%.4f", entity, report.overall_score)
            else:
                logger.info("Quality check PASSED [%s]: score=%.4f", entity, report.overall_score)

    def _persist_execution_stats(self):
        """Save pipeline stats to metadata.pipeline_executions."""
        from sqlalchemy import text
        import json
        from pipeline.core.database import get_engine
        try:
            engine = get_engine()
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO metadata.pipeline_executions 
                    (execution_id, pipeline_name, pipeline_version, status, started_at, finished_at, 
                     rows_ingested, rows_valid, rows_rejected, duration_seconds, peak_memory_mb, avg_cpu_percent, config_snapshot)
                    VALUES (:id, :name, :ver, :status, :start, :end, :ing, :valid, :rej, :dur, :mem, :cpu, :config)
                """), {
                    "id": self.execution_id,
                    "name": self.cfg.get("pipeline", {}).get("name", "aml_pipeline"),
                    "ver": self.cfg.get("pipeline", {}).get("version", "1.0.0"),
                    "status": self._stats.get("status", "UNKNOWN"),
                    "start": self._stats.get("started_at"),
                    "end": self._stats.get("finished_at"),
                    "ing": self._stats.get("rows_ingested_transactions", 0),
                    "valid": self._stats.get("rows_after_cleaning", {}).get("transactions", 0),
                    "rej": self._stats.get("rejected_transactions", 0),
                    "dur": self._stats.get("duration_seconds", 0.0),
                    "mem": self._stats.get("peak_memory_mb", 0.0),
                    "cpu": self._stats.get("avg_cpu_percent", 0.0),
                    "config": json.dumps(self._stats, default=str)
                })
            logger.info("✔ Execution metadata persisted")
        except Exception as exc:
            logger.error("Failed to persist execution stats: %s", exc)

    def _load_to_db(self, customers, accounts, transactions, cust_features, txn_features):
        """
        Load all datasets to PostgreSQL using upsert strategy.

        Target schema mapping:
          - customers   → raw_data.customers   (simple string columns, no UUID FKs)
          - accounts    → raw_data.accounts    (same)
          - transactions→ raw_data.transactions (partitioned by created_at)
          - cust_features → feature_store.customer_features
          - txn_features  → feature_store.transaction_features (partitioned by transaction_date)

        The warehouse.* tables require a full normalization ETL (UUID FK resolution
        for countries, kyc_statuses, risk_levels) which is done in a separate step.
        """
        load_stats = {}

        def _safe_load(df, schema, table, conflict_cols, label):
            """Load a DataFrame into the DB; log and continue on error (non-blocking)."""
            if df is None or df.empty:
                logger.info("Skipping empty DataFrame for %s.%s", schema, table)
                return 0
            try:
                ins, upd = upsert_dataframe(df, schema, table, conflict_cols, config=self.cfg)
                load_stats[label] = {"inserted": ins, "updated": upd}
                logger.info("✔ Loaded [%s.%s]: inserted=%d updated=%d", schema, table, ins, upd)
                return ins
            except Exception as exc:
                logger.error("✖ Load failed [%s.%s]: %s", schema, table, exc)
                return 0

        def _safe_load_nothing(df, schema, table, label):
            """Load using ON CONFLICT DO NOTHING — for tables whose UNIQUE constraint
            includes auto-generated columns (e.g. created_at DEFAULT NOW())."""
            if df is None or df.empty:
                logger.info("Skipping empty DataFrame for %s.%s", schema, table)
                return 0
            try:
                ins, upd = upsert_dataframe(
                    df, schema, table,
                    conflict_columns=[],   # no explicit conflict target needed for DO NOTHING
                    config=self.cfg,
                    on_conflict="nothing",
                )
                load_stats[label] = {"inserted": ins, "updated": upd}
                logger.info("✔ Loaded [%s.%s]: inserted=%d (DO NOTHING)", schema, table, ins)
                return ins
            except Exception as exc:
                logger.error("✖ Load failed [%s.%s]: %s", schema, table, exc)
                return 0

        # ── 1. Strip computed / transformed columns before raw_data load ──────
        # raw_data tables only want the original source columns.
        customers_raw = customers.drop(columns=[c for c in self._RAW_CUSTOMER_DROP if c in customers.columns], errors="ignore")
        accounts_raw  = accounts.drop(columns=[c for c in self._RAW_ACCOUNT_DROP  if c in accounts.columns],  errors="ignore")
        transactions_raw = transactions.drop(columns=[c for c in self._RAW_TXN_DROP if c in transactions.columns], errors="ignore")

        # ── 2. Ensure date columns are strings for raw_data tables ──
        # raw_data tables expect VARCHAR for dates, but cleaner.py converted them to Timestamp.
        for col in ["date_of_birth", "kyc_last_review"]:
            if col in customers_raw.columns:
                customers_raw[col] = customers_raw[col].dt.strftime("%Y-%m-%d") if pd.api.types.is_datetime64_any_dtype(customers_raw[col]) else customers_raw[col].astype(str)

        if "opened_date" in accounts_raw.columns:
            accounts_raw["opened_date"] = accounts_raw["opened_date"].dt.strftime("%Y-%m-%d") if pd.api.types.is_datetime64_any_dtype(accounts_raw["opened_date"]) else accounts_raw["opened_date"].astype(str)

        if "transaction_date" in transactions_raw.columns:
            transactions_raw["transaction_date"] = transactions_raw["transaction_date"].astype(str)


        import uuid
        batch_id = str(uuid.uuid4())
        
        # ── 3. Load to raw_data.* ─────────────────────────────────────────────
        customers_raw["batch_id"] = batch_id
        customers_raw["source_file"] = "generator_api"
        
        accounts_raw["batch_id"] = batch_id
        accounts_raw["source_file"] = "generator_api"
        
        _safe_load(customers_raw,    "raw_data",  "customers",    ["customer_id"],    "raw_customers")
        _safe_load(accounts_raw,     "raw_data",  "accounts",     ["account_id"],     "raw_accounts")
        
        # raw_data.transactions is partitioned by created_at.
        # We must add created_at to the DataFrame to match the partition key and use DO NOTHING.
        transactions_raw["created_at"] = pd.Timestamp.now(tz="UTC")
        transactions_raw["batch_id"] = batch_id
        transactions_raw["source_file"] = "generator_api"
        _safe_load_nothing(transactions_raw, "raw_data", "transactions", "raw_transactions")

        def _normalize_and_load_warehouse():
            """Populates warehouse lookup tables and core tables from raw_data."""
            from sqlalchemy import text
            from pipeline.core.database import get_engine
            logger.info("Executing warehouse normalization layer...")
            try:
                engine = get_engine()
                with engine.begin() as conn:
                    # 1. Lookups
                    conn.execute(text("""
                        INSERT INTO warehouse.countries (id, code)
                        SELECT gen_random_uuid(), COALESCE(country, 'UNK') FROM raw_data.customers GROUP BY COALESCE(country, 'UNK')
                        ON CONFLICT (code) DO NOTHING;
                    """))
                    conn.execute(text("""
                        INSERT INTO warehouse.countries (id, code)
                        SELECT gen_random_uuid(), COALESCE(residency_country, 'UNK') FROM raw_data.customers GROUP BY COALESCE(residency_country, 'UNK')
                        ON CONFLICT (code) DO NOTHING;
                    """))
                    conn.execute(text("""
                        INSERT INTO warehouse.countries (id, code)
                        SELECT gen_random_uuid(), COALESCE(meta_country_code, 'UNK') FROM raw_data.transactions GROUP BY COALESCE(meta_country_code, 'UNK')
                        ON CONFLICT (code) DO NOTHING;
                    """))
                    conn.execute(text("""
                        INSERT INTO warehouse.countries (id, code)
                        SELECT gen_random_uuid(), COALESCE(meta_destination_country, 'UNK') FROM raw_data.transactions GROUP BY COALESCE(meta_destination_country, 'UNK')
                        ON CONFLICT (code) DO NOTHING;
                    """))
                    conn.execute(text("""
                        INSERT INTO warehouse.countries (id, code)
                        SELECT gen_random_uuid(), COALESCE(meta_origin_country, 'UNK') FROM raw_data.transactions GROUP BY COALESCE(meta_origin_country, 'UNK')
                        ON CONFLICT (code) DO NOTHING;
                    """))
                    conn.execute(text("""
                        INSERT INTO warehouse.currencies (id, code)
                        SELECT gen_random_uuid(), COALESCE(currency, 'UNK') FROM raw_data.accounts GROUP BY COALESCE(currency, 'UNK')
                        ON CONFLICT (code) DO NOTHING;
                    """))
                    conn.execute(text("""
                        INSERT INTO warehouse.currencies (id, code)
                        SELECT gen_random_uuid(), COALESCE(currency, 'UNK') FROM raw_data.transactions GROUP BY COALESCE(currency, 'UNK')
                        ON CONFLICT (code) DO NOTHING;
                    """))
                    conn.execute(text("""
                        INSERT INTO warehouse.kyc_statuses (id, status_code)
                        SELECT gen_random_uuid(), kyc_status FROM raw_data.customers WHERE kyc_status IS NOT NULL GROUP BY kyc_status
                        ON CONFLICT (status_code) DO NOTHING;
                    """))
                    conn.execute(text("""
                        INSERT INTO warehouse.risk_levels (id, level_code, ordinal_rank, min_score, max_score)
                        VALUES 
                            (gen_random_uuid(), 'LOW', 1, 0, 33),
                            (gen_random_uuid(), 'MEDIUM', 2, 33, 66),
                            (gen_random_uuid(), 'HIGH', 3, 66, 100)
                        ON CONFLICT (level_code) DO NOTHING;
                    """))
                    
                    # 2. Customers
                    conn.execute(text("""
                        INSERT INTO warehouse.customers (id, customer_id, full_name, email, phone, date_of_birth, country_id, residency_country_id, kyc_status_id, kyc_last_review, pep_flag, sanctions_flag, adverse_media_flag, risk_level_id, risk_score, customer_type, raw_customer_id)
                        SELECT 
                            gen_random_uuid(), c.customer_id, c.full_name, c.email, c.phone, c.date_of_birth::date,
                            co.id, co_res.id, kyc.id, c.kyc_last_review::date, c.pep_flag::boolean, c.sanctions_flag::boolean, c.adverse_media_flag::boolean,
                            rl.id, c.risk_score::numeric, c.customer_type, c.id
                        FROM raw_data.customers c
                        LEFT JOIN warehouse.countries co ON c.country = co.code
                        LEFT JOIN warehouse.countries co_res ON c.residency_country = co_res.code
                        LEFT JOIN warehouse.kyc_statuses kyc ON c.kyc_status = kyc.status_code
                        LEFT JOIN warehouse.risk_levels rl ON c.risk_level = rl.level_code
                        WHERE NOT EXISTS (
                            SELECT 1 FROM warehouse.customers existing 
                            WHERE existing.customer_id = c.customer_id AND existing.wh_is_current = TRUE
                        );
                    """))
                    
                    # 3. Accounts
                    conn.execute(text("""
                        INSERT INTO warehouse.accounts (id, account_id, customer_id, account_type, account_status, currency_id, balance, opened_date, raw_account_id)
                        SELECT
                            gen_random_uuid(), a.account_id, wc.id, a.account_type, a.account_status, curr.id, a.balance::numeric, a.opened_date::date, a.id
                        FROM raw_data.accounts a
                        JOIN warehouse.customers wc ON a.customer_id = wc.customer_id
                        LEFT JOIN warehouse.currencies curr ON a.currency = curr.code
                        ON CONFLICT (account_id) DO NOTHING;
                    """))

                    # 4. Transactions
                    conn.execute(text("SET LOCAL enable_nestloop = off;"))
                    conn.execute(text("""
                        INSERT INTO warehouse.transactions (
                            id, transaction_id, customer_id, account_id, transaction_date, 
                            transaction_type, amount, currency_id, risk_flags, source_system, 
                            meta_counterparty, meta_counterparty_type, meta_country_id, 
                            meta_destination_country_id, meta_origin_country_id, raw_transaction_id
                        )
                        SELECT
                            gen_random_uuid(), t.transaction_id, wc.id, wa.id, t.transaction_date::timestamptz, 
                            t.transaction_type, t.amount::numeric, curr.id, t.risk_flags::jsonb, t.source_system, 
                            COALESCE(t.meta_counterparty, 'UNKNOWN'), COALESCE(t.meta_counterparty_type, 'UNKNOWN'), co_meta.id, 
                            co_dest.id, co_orig.id, t.id
                        FROM raw_data.transactions t
                        JOIN warehouse.customers wc ON t.customer_id = wc.customer_id AND wc.wh_is_current = TRUE
                        JOIN warehouse.accounts wa ON t.account_id = wa.account_id
                        LEFT JOIN warehouse.currencies curr ON COALESCE(t.currency, 'UNK') = curr.code
                        LEFT JOIN warehouse.countries co_meta ON COALESCE(t.meta_country_code, 'UNK') = co_meta.code
                        LEFT JOIN warehouse.countries co_dest ON COALESCE(t.meta_destination_country, 'UNK') = co_dest.code
                        LEFT JOIN warehouse.countries co_orig ON COALESCE(t.meta_origin_country, 'UNK') = co_orig.code
                        ON CONFLICT (transaction_id, transaction_date) DO NOTHING;
                    """))
                logger.info("✔ Warehouse normalization complete")
            except Exception as e:
                logger.error("✖ Warehouse normalization failed: %s", e)

        _normalize_and_load_warehouse()

        # ── 4. Load feature_store.customer_features ───────────────────────────
        if cust_features is not None and not cust_features.empty:
            # Map transformed column names to feature_store column names
            cf = cust_features.copy()

            # Map risk_score_scaled → risk_score_scaled (keep), flags (already int)
            col_map = {
                "flag_high_risk_country": "is_high_risk_country",
                "txn_high_value_count":   "high_value_txn_count",
                "unique_currencies":      "unique_countries_count",
                "txn_count":              "txn_count_30d",
                "txn_amount_total":       "txn_amount_sum_30d",
                "txn_amount_mean":        "txn_amount_avg_30d",
                "total_balance":          "total_balance_scaled",
            }
            cf = cf.rename(columns={k: v for k, v in col_map.items() if k in cf.columns})

            # Keep only columns that exist in the feature_store table
            cust_feat_keep = [
                "customer_id", "feature_set_version",
                "risk_score_scaled", "risk_level_encoded", "kyc_status_encoded", "customer_type_encoded",
                "account_count", "total_balance_scaled",
                "pep_flag", "sanctions_flag", "adverse_media_flag", "is_high_risk_country",
                "txn_count_30d", "txn_amount_sum_30d", "txn_amount_avg_30d",
                "high_value_txn_count", "unique_countries_count",
                "feature_vector", "label_aml_risk",
            ]
            cf = cf[[c for c in cust_feat_keep if c in cf.columns]]
            
            for col in ["pep_flag", "sanctions_flag", "adverse_media_flag", "is_high_risk_country", "label_aml_risk"]:
                if col in cf.columns:
                    cf[col] = cf[col].fillna(0).astype(bool).astype(int)

            _safe_load(cf, "feature_store", "customer_features",
                       ["customer_id", "feature_set_version"], "customer_features")

        # ── 5. Load feature_store.transaction_features ────────────────────────
        if txn_features is not None and not txn_features.empty:
            tf = txn_features.copy()

            # Map column names to match feature_store schema
            tf_col_map = {
                "amount_scaled":            "amount_scaled",
                "flag_high_value":          "is_high_value",
                "flag_high_risk_country":   "is_high_risk_country",
                "txn_year":                 "txn_year",
                "txn_month":                "txn_month",
                "txn_day":                  "txn_day",
                "txn_dayofweek":            "txn_dayofweek",
                "txn_quarter":              "txn_quarter",
                "txn_is_weekend":           "txn_is_weekend",
                "amount_rolling_7_mean":    "amount_rolling_7_mean",
                "amount_rolling_30_mean":   "amount_rolling_30_mean",
                "amount_rolling_30_std":    "amount_rolling_30_std",
            }
            tf = tf.rename(columns={k: v for k, v in tf_col_map.items() if k in tf.columns})

            # Ensure transaction_date is TIMESTAMPTZ (not string or naive)
            if "transaction_date" in tf.columns:
                tf["transaction_date"] = pd.to_datetime(tf["transaction_date"], errors="coerce", utc=True)
                # Drop rows where transaction_date is NULL — partition key must not be NULL
                before = len(tf)
                tf = tf.dropna(subset=["transaction_date"])
                dropped = before - len(tf)
                if dropped:
                    logger.warning("Dropped %d txn_features rows with NULL transaction_date", dropped)

            txn_feat_keep = [
                "transaction_id", "customer_id", "account_id", "feature_set_version",
                "transaction_date",
                "txn_year", "txn_month", "txn_day", "txn_dayofweek", "txn_quarter", "txn_is_weekend",
                "amount_scaled", "amount_lag_1", "amount_lag_3", "amount_lag_7",
                "amount_rolling_7_mean", "amount_rolling_30_mean", "amount_rolling_30_std",
                "is_high_value", "is_high_risk_country",
                "feature_vector", "label_suspicious",
            ]
            tf = tf[[c for c in txn_feat_keep if c in tf.columns]]

            for col in ["txn_is_weekend", "is_high_value", "is_high_risk_country", "label_suspicious"]:
                if col in tf.columns:
                    tf[col] = tf[col].fillna(0).astype(bool).astype(int)

            if not tf.empty:
                _safe_load(tf, "feature_store", "transaction_features",
                           ["transaction_id", "feature_set_version", "transaction_date"],
                           "transaction_features")

        self._stats["load_stats"] = load_stats

    @with_retry(max_retries=3, backoff=2.0)
    def _store_rejected(self, rejected_df, entity_type):
        """Store rejected records in raw_data.rejected_records table."""
        try:
            engine = get_engine(self.cfg)
            records = []
            for _, row in rejected_df.iterrows():
                errors = row.get("_validation_errors", [])
                payload = row.drop(labels=["_validation_errors"], errors="ignore").to_dict()
                records.append({
                    "entity_type": entity_type,
                    "source_id": str(payload.get(f"{entity_type.rstrip('s')}_id", "")),
                    "ingestion_id": self.execution_id,
                    "batch_id": self.execution_id,
                    "raw_payload": json.dumps(payload, default=str),
                    "validation_errors": json.dumps(errors, default=str),
                    "rejection_reason": "Validation failed",
                    "reprocessed": False,
                })
            if records:
                pd.DataFrame(records).to_sql(
                    "rejected_records", engine,
                    schema="raw_data", if_exists="append", index=False, method="multi",
                )
                logger.info("Stored %d rejected [%s] to raw_data.rejected_records", len(records), entity_type)
        except Exception as exc:
            logger.warning("Failed to store rejected records for %s: %s", entity_type, exc)


# ── CLI entry point ───────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Pull data from the existing generator
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from generator.data_generator import generate_dataset

    num = int(os.environ.get("NUM_CUSTOMERS", "200"))
    logger.info("Generating %d customers via generator...", num)
    dataset = generate_dataset(num_customers=num)

    pipeline = AMLPipeline()
    stats = pipeline.run(dataset=dataset)
    print("\n" + "=" * 60)
    print("Pipeline Execution Stats:")
    import json
    print(json.dumps(stats, indent=2, default=str))
