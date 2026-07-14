# KYRO AML Data Pipeline — System Architecture & Design Document

## 1. Executive Summary
The KYRO AML Data Pipeline is an enterprise-grade ETL/ELT platform designed to ingest synthetic global banking data (Customers, Accounts, Transactions), rigorously validate and clean it, and structure it into a high-performance PostgreSQL warehouse. The system simultaneously generates a Machine Learning (ML) Feature Store containing engineered signals and aggregations to train downstream fraud and money laundering detection models.

---

## 2. Pipeline Architecture Flow

The pipeline operates in a sequential, highly-observable DAG (Directed Acyclic Graph) flow, orchestrated via `pipeline.run_pipeline`:

1.  **Ingestion (`pipeline/ingestion`)**
    *   Accepts data via Python memory dictionaries, JSON payloads, CSV, or multi-sheet Excel files.
    *   Applies schema reconciliation and safely handles character encodings.
    *   Supports fixed-size chunking for memory-efficient batch processing.

2.  **Validation (`pipeline/validation`)**
    *   Validates data against configured rules: required fields, types, numeric boundaries, regular expressions (e.g., CUST-xxxx), UUID structures, and allowed enum values.
    *   Isolates malformed records and logs them into `raw_data.rejected_records` without failing the entire batch (Quarantine Pattern).

3.  **Cleaning (`pipeline/cleaning`)**
    *   **String Normalization:** Removes HTML tags, strips invisible control characters, normalizes Unicode to NFC, collapses double spaces.
    *   **Imputation:** Employs configurable strategies including `KNNImputer`, `IterativeImputer` (MICE), median, mode, or forward-fill.
    *   **Duplicate Resolution:** Two-pass duplicate removal (exact row hashing followed by configurable Business Key deduplication: `keep_first`, `keep_last`).
    *   **Outlier Handling:** Implements robust outlier detection using Interquartile Range (IQR), Z-Score, Modified Z-Score, Isolation Forests, and DBSCAN. Values can be winsorized, removed, or flagged.

4.  **Transformation & Feature Engineering (`pipeline/transformation`, `pipeline/feature_engineering`)**
    *   **Scalers & Encoders:** Uses scikit-learn for Robust Scaling, Label Encoding, One-Hot Encoding, and Target Encoding. Scalers are persisted as joblib artifacts.
    *   **Time-Series Features:** Generates lag features (amount_lag_1), rolling windows (amount_rolling_7d_mean), and temporal properties (is_weekend, quarter).
    *   **AML Domain Signals:** Flags Structuring ($9k-$10k transactions), High-Risk Country interactions, and compliance alerts (PEP/Sanctions).
    *   **Aggregations:** Computes customer lifetime value, transaction velocities, and cross-entity ratios.

5.  **Quality Assurance (`pipeline/quality`)**
    *   Calculates an automated Quality Score based on 7 dimensions: Completeness, Uniqueness, Validity, Consistency, Timeliness, Distribution Drift (Kolmogorov-Smirnov test), and Anomaly volume.

6.  **Load & Storage (`pipeline/loaders`)**
    *   Leverages PostgreSQL `COPY` for bulk throughput on initial loads.
    *   Uses `INSERT ... ON CONFLICT DO UPDATE` (Upsert) for incremental batches.
    *   Applies Slowly Changing Dimension (SCD) Type 2 logic for Customer tracking over time.

---

## 3. Database Schema Design (PostgreSQL 16)

The database strictly adheres to **3NF/BCNF** normalization to eliminate redundancy and prevent insert/update/delete anomalies.

### Schemas
*   `raw_data`: 1NF staging area. Lands data exactly as received. Partitioned.
*   `warehouse`: Core 3NF/BCNF business tables.
*   `metadata`: Pipeline execution logs, transformation history, and state checkpoints.
*   `audit`: Immutable, append-only trigger-based audit logs for every DML operation.
*   `logs`: Application and pipeline structured logging.
*   `feature_store`: Materialized ML feature vectors with version control.
*   `ml`: Model registry and inference results.
*   `analytics`: Read-optimized Materialized Views.

### Key Normalizations & Lookup Tables
*   `warehouse.countries`: Resolves 200+ distinct country codes into a single lookup table to eliminate string redundancy and centralize `is_high_risk` logic.
*   `warehouse.currencies`: Normalizes ISO 4217 currencies and their precision metadata.
*   `warehouse.risk_levels`: Normalizes risk bounds (LOW, MEDIUM, HIGH, CRITICAL).

### Indexing Strategy
*   **Primary/Foreign Keys:** Standard B-Tree indexes.
*   **BRIN (Block Range Index):** Used on append-only timestamps (e.g., `transaction_date`, `created_at`) to allow massive time-range scans with ~20KB memory footprint compared to multi-gigabyte B-Trees.
*   **GIN (Generalized Inverted Index):** Used for JSONB columns (`risk_flags`) to support lightning-fast containment queries.
*   **GIN + pg_trgm:** Fuzzy string matching on counterparty names.
*   **Partial Indexes:** Scoped to active data (e.g., `WHERE is_deleted = FALSE`, `WHERE is_outlier = TRUE`) for efficient dashboard retrieval.

### Constraints & Integrity
*   Database-level enums and `CHECK` constraints (e.g., `amount > 0`, `risk_score BETWEEN 0 AND 100`) ensure invalid data never reaches disk.
*   Trigger functions enforce logical consistency (e.g., ensuring `risk_level_id` correctly aligns with the numerical `risk_score`).

---

## 4. Audit & Security

*   **Immutable Audit Trail:** PostgreSQL Trigger functions automatically capture `OLD` and `NEW` JSONB states on every `INSERT`, `UPDATE`, and `DELETE` operation across the warehouse, tracking the `db_user` and `event_timestamp`.
*   **Row-Level Security (RLS):** Enabled on `customers` to hide soft-deleted or historically expired (SCD2) records from analysts, while preserving them for ML training.
*   **Role-Based Access Control (RBAC):** Distinct roles mapped via DDL (`kyro_pipeline_writer`, `kyro_analyst_ro`, `kyro_ml_user`, `kyro_audit_reader`).
*   **Secrets Management:** Handled dynamically via environment variables with fallback to Docker Swarm secret mounts.

---

## 5. Technology Stack

*   **Language:** Python 3.12 (Strict typing).
*   **Data Processing:** Pandas, NumPy, Scikit-Learn, SciPy.
*   **Database:** PostgreSQL 16 (via Psycopg3 + SQLAlchemy 2.0).
*   **Migrations:** Alembic.
*   **Testing:** Pytest, pytest-cov.
*   **Infrastructure:** Docker, Docker Compose.
