#!/usr/bin/env python3
"""
sync_to_app.py — Sync raw_data.* → app.* schema for the KYRO dashboard.

The ETL pipeline writes generated data into raw_data.* and warehouse.*.
The FastAPI backend and frontend dashboard exclusively read from app.*.
This script bridges that gap safely, handling all PostgreSQL constraint
mappings discovered in the generator (TRUST→FUND, EXPIRED→UNDER_REVIEW, etc.)
"""

import psycopg
import sys

DATABASE_URL = "postgresql://kyro_user:kyro_pass@localhost:5434/kyro_aml"

# ── KYC statuses accepted by app.customers ──────────────────────────────────
# Generator produces: COMPLETE, PENDING, EXPIRED, PARTIAL
# app CHECK constraint allows: PENDING, VERIFIED, REJECTED, UNDER_REVIEW
KYC_MAP = """
    CASE
        WHEN kyc_status IS NULL                                          THEN 'PENDING'
        WHEN UPPER(kyc_status) = 'COMPLETE'                             THEN 'VERIFIED'
        WHEN UPPER(kyc_status) IN ('EXPIRED', 'PARTIAL')                THEN 'UNDER_REVIEW'
        WHEN UPPER(kyc_status) NOT IN
             ('PENDING','VERIFIED','REJECTED','UNDER_REVIEW')            THEN 'PENDING'
        ELSE UPPER(kyc_status)
    END
"""

# ── Customer types accepted by app.customers ─────────────────────────────────
# Generator produces: INDIVIDUAL, CORPORATE, PARTNERSHIP, TRUST, NGO
# app CHECK constraint allows: INDIVIDUAL, CORPORATE, FUND
CUST_TYPE_MAP = """
    CASE
        WHEN customer_type IS NULL                                        THEN 'INDIVIDUAL'
        WHEN UPPER(customer_type) = 'TRUST'                              THEN 'FUND'
        WHEN UPPER(customer_type) NOT IN ('INDIVIDUAL','CORPORATE','FUND') THEN 'INDIVIDUAL'
        ELSE UPPER(customer_type)
    END
"""

# ── Account types accepted by app.accounts ───────────────────────────────────
# Generator produces: SAVINGS, CHECKING, CREDIT, INVESTMENT, CRYPTO, FX
# app CHECK constraint allows: CHECKING, SAVINGS, INVESTMENT, TRADING
ACCT_TYPE_MAP = """
    CASE
        WHEN UPPER(account_type) IN ('CHECKING','SAVINGS','INVESTMENT','TRADING')
             THEN UPPER(account_type)
        WHEN UPPER(account_type) = 'CREDIT'  THEN 'CHECKING'
        WHEN UPPER(account_type) = 'CRYPTO'  THEN 'INVESTMENT'
        WHEN UPPER(account_type) = 'FX'      THEN 'TRADING'
        ELSE 'CHECKING'
    END
"""

# ── Transaction types accepted by app.transactions ───────────────────────────
# Generator produces: DEPOSIT, WITHDRAWAL, TRANSFER_IN, TRANSFER_OUT,
#                     BUY, SELL, PAYMENT, FEE, REFUND
# app CHECK constraint allows: DEPOSIT, WITHDRAWAL, TRANSFER, FX, TRADE
TXN_TYPE_MAP = """
    CASE
        WHEN UPPER(transaction_type) IN ('DEPOSIT','WITHDRAWAL','FX')
             THEN UPPER(transaction_type)
        WHEN UPPER(transaction_type) IN ('TRANSFER_IN','TRANSFER_OUT') THEN 'TRANSFER'
        WHEN UPPER(transaction_type) IN ('BUY','SELL')                 THEN 'TRADE'
        ELSE 'TRANSFER'
    END
"""


def run(sql: str, conn, label: str):
    print(f"  ⟳  {label}...")
    with conn.cursor() as cur:
        cur.execute(sql)
        count = cur.rowcount
    print(f"  ✔  {label} — {count} row(s)")
    return count


def main():
    print("=" * 60)
    print("KYRO  raw_data → app  sync")
    print("=" * 60)

    with psycopg.connect(DATABASE_URL, autocommit=False) as conn:

        # ── 1. Seed admin users (idempotent) ─────────────────────────────
        print("\n[1/4] Users")
        run("""
            INSERT INTO app.users
                (id, username, email, full_name, hashed_password, role, is_active)
            VALUES
                (gen_random_uuid(), 'admin',      'admin@kyro.com',      'System Admin',
                 '$2b$12$mxwW9jU70LW1XXs41UhXJ.E.yU10QpoVKqJ6iRwFytQqEsKyCG2NK', 'ADMIN',              true),
                (gen_random_uuid(), 'analyst',    'analyst@kyro.com',    'AML Analyst',
                 '$2b$12$mxwW9jU70LW1XXs41UhXJ.E.yU10QpoVKqJ6iRwFytQqEsKyCG2NK', 'ANALYST',            true),
                (gen_random_uuid(), 'compliance', 'compliance@kyro.com', 'Compliance Officer',
                 '$2b$12$mxwW9jU70LW1XXs41UhXJ.E.yU10QpoVKqJ6iRwFytQqEsKyCG2NK', 'COMPLIANCE_OFFICER', true)
            ON CONFLICT (email) DO NOTHING;
        """, conn, "Seed users (admin/analyst/compliance) — password: admin123")

        # ── 2. Customers ──────────────────────────────────────────────────
        print("\n[2/4] Customers")
        run("TRUNCATE TABLE app.customers CASCADE;", conn, "Truncate app.customers (cascades)")
        run(f"""
            INSERT INTO app.customers
                (id, full_name, email, phone, date_of_birth,
                 country, residency_country, kyc_status,
                 pep_flag, sanctions_flag, adverse_media_flag,
                 risk_level, risk_score, customer_type,
                 created_at, updated_at)
            SELECT
                gen_random_uuid(),
                full_name,
                email,
                phone,
                NULLIF(date_of_birth, '')::date,
                country,
                residency_country,
                {KYC_MAP} AS kyc_status,
                COALESCE(pep_flag,           false),
                COALESCE(sanctions_flag,     false),
                COALESCE(adverse_media_flag, false),
                CASE
                    WHEN risk_score >= 70 THEN 'HIGH'
                    WHEN risk_score >= 40 THEN 'MEDIUM'
                    ELSE 'LOW'
                END AS risk_level,
                CAST(COALESCE(risk_score, 0) AS INTEGER),
                {CUST_TYPE_MAP} AS customer_type,
                COALESCE(created_at, NOW()),
                NOW()
            FROM raw_data.customers;
        """, conn, "Insert customers from raw_data")

        # ── 3. Accounts ───────────────────────────────────────────────────
        print("\n[3/4] Accounts")
        run(f"""
            INSERT INTO app.accounts
                (id, customer_id, account_type, currency,
                 balance, account_status, opened_date,
                 created_at, updated_at)
            SELECT
                a.id,
                c.id            AS customer_id,
                {ACCT_TYPE_MAP} AS account_type,
                UPPER(COALESCE(a.currency, 'USD')),
                COALESCE(a.balance, 0),
                CASE
                    WHEN UPPER(a.account_status) IN ('ACTIVE','SUSPENDED','CLOSED','FROZEN')
                         THEN UPPER(a.account_status)
                    ELSE 'ACTIVE'
                END             AS account_status,
                NULLIF(a.opened_date, '')::date,
                COALESCE(a.created_at, NOW()),
                NOW()
            FROM raw_data.accounts a
            JOIN raw_data.customers rc ON rc.customer_id = a.customer_id
            JOIN app.customers       c  ON c.email       = rc.email;
        """, conn, "Insert accounts from raw_data")

        # ── 4. Transactions (batch — no LIMIT so all data is loaded) ─────
        print("\n[4/4] Transactions + Alerts")
        run(f"""
            INSERT INTO app.transactions
                (id, customer_id, account_id, transaction_date,
                 amount, currency, transaction_type,
                 meta_counterparty, meta_counterparty_type,
                 meta_location, meta_country, meta_country_code,
                 meta_destination_country, meta_origin_country, meta_source,
                 risk_score, created_at)
            SELECT
                gen_random_uuid(),
                c.id                AS customer_id,
                acc.id              AS account_id,
                t.transaction_date::timestamptz,
                CASE WHEN ABS(t.amount) = 0 THEN 0.01
                     ELSE ABS(t.amount) END,
                UPPER(COALESCE(t.currency, 'USD')),
                {TXN_TYPE_MAP}      AS transaction_type,
                t.meta_counterparty,
                t.meta_counterparty_type,
                t.meta_location,
                t.meta_country,
                LEFT(COALESCE(t.meta_country_code, 'UNK'), 3),
                t.meta_destination_country,
                t.meta_origin_country,
                t.meta_source,
                0                   AS risk_score,
                COALESCE(t.created_at, NOW())
            FROM raw_data.transactions t
            JOIN raw_data.accounts   ra  ON ra.account_id  = t.account_id
            JOIN app.accounts        acc ON acc.id          = ra.id
            JOIN app.customers       c   ON c.id            = acc.customer_id;
        """, conn, "Insert all transactions from raw_data")

        # ── 5. Alerts — derived from high-risk transactions ───────────────
        run("""
            WITH scored AS (
                SELECT
                    c.id                                                         AS customer_id,
                    t.transaction_date,
                    CASE
                        WHEN t.amount > 50000                    THEN 'LARGE_AMOUNT'
                        WHEN t.transaction_type = 'TRANSFER'
                             AND c.risk_score > 60               THEN 'SUSPICIOUS_TRANSFER'
                        WHEN c.risk_score > 70                   THEN 'HIGH_RISK_CUSTOMER'
                        WHEN c.pep_flag                          THEN 'PEP_ACTIVITY'
                        WHEN c.sanctions_flag                    THEN 'SANCTIONS_HIT'
                        ELSE 'BEHAVIORAL_ANOMALY'
                    END                                                          AS alert_type,
                    LEAST(99,
                        CASE
                            WHEN t.amount > 100000 OR c.risk_score > 80
                                THEN 85 + (RANDOM() * 14)::int
                            WHEN t.amount > 50000  OR c.risk_score > 60
                                THEN 60 + (RANDOM() * 25)::int
                            ELSE   40 + (RANDOM() * 20)::int
                        END
                    )                                                            AS risk_score
                FROM app.transactions t
                JOIN app.accounts     acc ON acc.id = t.account_id
                JOIN app.customers    c   ON c.id   = acc.customer_id
                WHERE t.amount > 25000 OR c.risk_score > 50
                ORDER BY t.transaction_date DESC
                LIMIT 2000
            )
            INSERT INTO app.alerts
                (id, customer_id, alert_type, risk_score, confidence, status, created_at)
            SELECT
                gen_random_uuid(),
                customer_id,
                alert_type,
                risk_score::int,
                (0.70 + RANDOM() * 0.29)::numeric(3,2),
                (ARRAY['OPEN','OPEN','OPEN','ASSIGNED','IN_REVIEW','RESOLVED'])
                    [1 + (RANDOM() * 5)::int],
                transaction_date - (RANDOM() * INTERVAL '48 hours')
            FROM scored;
        """, conn, "Generate alerts from high-risk transactions")

        conn.commit()

    print("\n" + "=" * 60)
    print("✅  Sync complete! Refresh your dashboard.")
    print("=" * 60)

    # ── Final count report ────────────────────────────────────────────────
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for table, label in [
                ("app.customers",    "Customers"),
                ("app.accounts",     "Accounts"),
                ("app.transactions", "Transactions"),
                ("app.alerts",       "Alerts"),
                ("app.users",        "Users"),
            ]:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                print(f"  {label:15s}: {cur.fetchone()[0]:,}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Sync failed: {e}")
        sys.exit(1)
