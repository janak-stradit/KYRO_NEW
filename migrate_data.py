#!/usr/bin/env python3
"""
Data Migration Script: raw_data -> app schema
Migrate generated data from pipeline to API-compatible format
"""

import uuid
from datetime import datetime, timezone
import psycopg
from pathlib import Path

DATABASE_URL = "postgresql://kyro_user:kyro_pass@localhost:5434/kyro_aml"

def generate_uuid():
    """Generate UUID v4"""
    return str(uuid.uuid4())

def migrate_customers():
    """Migrate customers from raw_data.customers to app.customers"""
    print("🔄 Migrating customers...")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM raw_data.customers")
            raw_count = cur.fetchone()[0]
            print(f"📊 Raw data: {raw_count} customers")
            
            cur.execute("TRUNCATE TABLE app.customers CASCADE")
            
            migrate_query = """
            INSERT INTO app.customers (
                id, full_name, email, phone, date_of_birth, 
                country, residency_country, kyc_status, pep_flag, 
                sanctions_flag, adverse_media_flag, risk_level, 
                risk_score, customer_type, created_at, updated_at
            )
            SELECT 
                id,
                full_name,
                email,
                phone,
                date_of_birth::date,
                country,
                residency_country,
                CASE 
                    WHEN kyc_status IS NULL         THEN 'PENDING'
                    WHEN UPPER(kyc_status) = 'VERIFIED'    THEN 'VERIFIED'
                    WHEN UPPER(kyc_status) = 'REJECTED'    THEN 'REJECTED'
                    WHEN UPPER(kyc_status) = 'UNDER_REVIEW' THEN 'UNDER_REVIEW'
                    WHEN UPPER(kyc_status) = 'COMPLETE'    THEN 'VERIFIED'
                    WHEN UPPER(kyc_status) = 'PARTIAL'     THEN 'UNDER_REVIEW'
                    WHEN UPPER(kyc_status) = 'EXPIRED'     THEN 'REJECTED'
                    ELSE 'PENDING'
                END as kyc_status,
                COALESCE(pep_flag, false) as pep_flag,
                COALESCE(sanctions_flag, false) as sanctions_flag,
                COALESCE(adverse_media_flag, false) as adverse_media_flag,
                CASE 
                    WHEN COALESCE(risk_score::numeric, 0) >= 70 THEN 'HIGH'
                    WHEN COALESCE(risk_score::numeric, 0) >= 40 THEN 'MEDIUM'
                    ELSE 'LOW'
                END as risk_level,
                LEAST(100, GREATEST(0, COALESCE(risk_score::integer, 0))) as risk_score,
                CASE 
                    WHEN customer_type IS NULL THEN 'INDIVIDUAL'
                    WHEN UPPER(customer_type) = 'TRUST' THEN 'FUND'
                    WHEN UPPER(customer_type) = 'BUSINESS' THEN 'CORPORATE'
                    WHEN UPPER(customer_type) NOT IN ('INDIVIDUAL', 'CORPORATE', 'FUND') THEN 'INDIVIDUAL'
                    ELSE UPPER(customer_type)
                END as customer_type,
                COALESCE(created_at, NOW()) as created_at,
                COALESCE(updated_at, NOW()) as updated_at
            FROM raw_data.customers
            """
            
            cur.execute(migrate_query)
            migrated_count = cur.rowcount
            print(f"✅ Migrated {migrated_count} customers")
            
            return migrated_count

def migrate_accounts():
    """Migrate accounts from raw_data.accounts to app.accounts"""
    print("🔄 Migrating accounts...")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM raw_data.accounts")
            raw_count = cur.fetchone()[0]
            print(f"📊 Raw data: {raw_count} accounts")
            
            cur.execute("TRUNCATE TABLE app.accounts CASCADE")
            
            migrate_query = """
            INSERT INTO app.accounts (
                id, customer_id, account_type, 
                currency, balance, account_status, opened_date, 
                account_metadata,
                created_at, updated_at
            )
            SELECT 
                a.id,
                c.id as customer_id,
                CASE 
                    WHEN UPPER(a.account_type) IN ('CHECKING', 'SAVINGS', 'INVESTMENT', 'TRADING') THEN UPPER(a.account_type)
                    WHEN UPPER(a.account_type) = 'CREDIT' THEN 'CHECKING'
                    WHEN UPPER(a.account_type) = 'LOAN' THEN 'SAVINGS'
                    ELSE 'CHECKING'
                END as account_type,
                UPPER(a.currency) as currency,
                a.balance,
                CASE 
                    WHEN a.account_status IS NULL THEN 'ACTIVE'
                    ELSE UPPER(a.account_status)
                END as account_status,
                a.opened_date::date,
                jsonb_build_object('raw_account_id', a.account_id) as account_metadata,
                COALESCE(a.created_at, NOW()) as created_at,
                COALESCE(a.updated_at, NOW()) as updated_at
            FROM raw_data.accounts a
            JOIN raw_data.customers rc ON rc.customer_id = a.customer_id
            JOIN app.customers c ON c.id = rc.id
            """
            
            cur.execute(migrate_query)
            migrated_count = cur.rowcount
            print(f"✅ Migrated {migrated_count} accounts")
            
            return migrated_count

def migrate_transactions():
    """Migrate transactions from raw_data.transactions to app.transactions"""
    print("🔄 Migrating transactions...")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM raw_data.transactions")
            raw_count = cur.fetchone()[0]
            print(f"📊 Raw data: {raw_count} transactions")
            
            cur.execute("TRUNCATE TABLE app.transactions CASCADE")
            
            migrate_query = f"""
            INSERT INTO app.transactions (
                id, customer_id, account_id, transaction_date, transaction_type, amount, currency,
                meta_counterparty, meta_counterparty_type, meta_country_code, 
                meta_destination_country, meta_origin_country, risk_flags, risk_score, source_system,
                created_at
            )
            SELECT 
                t.id,
                c.id as customer_id,
                acc.id as account_id,
                t.transaction_date::timestamp with time zone,
                CASE UPPER(t.transaction_type)
                    WHEN 'BUY' THEN 'TRADE'
                    WHEN 'SELL' THEN 'TRADE'
                    WHEN 'FEE' THEN 'WITHDRAWAL'
                    WHEN 'PAYMENT' THEN 'TRANSFER'
                    WHEN 'REFUND' THEN 'DEPOSIT'
                    WHEN 'TRANSFER_IN' THEN 'TRANSFER'
                    WHEN 'TRANSFER_OUT' THEN 'TRANSFER'
                    WHEN 'DEPOSIT' THEN 'DEPOSIT'
                    WHEN 'WITHDRAWAL' THEN 'WITHDRAWAL'
                    WHEN 'FX' THEN 'FX'
                    ELSE 'TRANSFER'
                END as transaction_type,
                t.amount,
                UPPER(t.currency) as currency,
                t.meta_counterparty,
                t.meta_counterparty_type,
                t.meta_country_code,
                t.meta_destination_country,
                t.meta_origin_country,
                t.risk_flags,
                COALESCE((t.risk_flags->>'risk_score')::int, 0) as risk_score,
                t.source_system,
                COALESCE(t.created_at, NOW()) as created_at
            FROM raw_data.transactions t
            JOIN raw_data.accounts ra ON ra.account_id = t.account_id
            JOIN raw_data.customers rc ON rc.customer_id = ra.customer_id
            JOIN app.customers c ON c.id = rc.id
            JOIN app.accounts acc ON acc.id = ra.id
            """
            
            cur.execute(migrate_query)
            total_migrated = cur.rowcount
            
            print(f"✅ Migrated {total_migrated} transactions")
            return total_migrated

def create_sample_users():
    """Create sample users for login"""
    print("🔄 Creating sample users...")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM app.users WHERE username = 'analyst'")
            if cur.fetchone()[0] > 0:
                print("👤 Sample users already exist")
                return
            
            users_query = """
            INSERT INTO app.users (id, username, email, full_name, hashed_password, role, is_active, created_at, updated_at)
            VALUES 
            (gen_random_uuid(), 'analyst', 'analyst@kyro.com', 'Test Analyst', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewEyKdyFFK/4V2r6', 'ANALYST', true, NOW(), NOW()),
            (gen_random_uuid(), 'admin', 'admin@kyro.com', 'System Admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewEyKdyFFK/4V2r6', 'ADMIN', true, NOW(), NOW()),
            (gen_random_uuid(), 'compliance', 'compliance@kyro.com', 'Compliance Officer', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewEyKdyFFK/4V2r6', 'COMPLIANCE_OFFICER', true, NOW(), NOW())
            """
            
            cur.execute(users_query)
            print("✅ Created sample users (password: kyro123)")

def generate_sample_alerts():
    """Generate some sample alerts for dashboard"""
    print("🔄 Generating sample alerts...")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE app.alerts CASCADE")
            
            alerts_query = """
            WITH high_risk_txns AS (
                SELECT 
                    t.id as transaction_id,
                    c.id as customer_id,
                    t.amount,
                    t.transaction_date,
                    c.full_name,
                    CASE 
                        WHEN t.amount > 50000 THEN 'LARGE_AMOUNT'
                        WHEN t.transaction_type = 'WIRE_TRANSFER' THEN 'WIRE_TRANSFER'
                        WHEN c.risk_score > 70 THEN 'HIGH_RISK_CUSTOMER'
                        ELSE 'BEHAVIORAL_ANOMALY'
                    END as alert_type,
                    CASE 
                        WHEN t.amount > 100000 OR c.risk_score > 80 THEN 85 + (RANDOM() * 15)::int
                        WHEN t.amount > 50000 OR c.risk_score > 60 THEN 60 + (RANDOM() * 25)::int
                        ELSE 40 + (RANDOM() * 30)::int
                    END as risk_score
                FROM app.transactions t
                JOIN app.accounts acc ON acc.id = t.account_id
                JOIN app.customers c ON c.id = acc.customer_id
                WHERE t.amount > 25000 OR c.risk_score > 50
                ORDER BY t.transaction_date DESC
                LIMIT 50
            )
            INSERT INTO app.alerts (
                id, customer_id, alert_type, 
                risk_score, confidence, status,
                ml_explanation, created_at
            )
            SELECT 
                gen_random_uuid(),
                customer_id,
                alert_type,
                risk_score::int,
                (0.7 + RANDOM() * 0.3)::numeric(3,2),
                CASE (RANDOM() * 4)::int
                    WHEN 0 THEN 'OPEN'
                    WHEN 1 THEN 'ASSIGNED' 
                    WHEN 2 THEN 'IN_REVIEW'
                    ELSE 'RESOLVED'
                END,
                CASE alert_type
                    WHEN 'LARGE_AMOUNT' THEN 'Large transaction amount detected'
                    WHEN 'WIRE_TRANSFER' THEN 'Wire transfer requires review'
                    WHEN 'HIGH_RISK_CUSTOMER' THEN 'Transaction from high-risk customer'
                    ELSE 'Unusual transaction pattern detected'
                END,
                transaction_date - (RANDOM() * INTERVAL '24 hours')
            FROM high_risk_txns
            """
            
            cur.execute(alerts_query)
            alert_count = cur.rowcount
            print(f"✅ Generated {alert_count} sample alerts")

def main():
    """Run the complete data migration"""
    print("🚀 Starting KYRO Data Migration")
    print("=" * 50)
    
    try:
        customers = migrate_customers()
        accounts = migrate_accounts() 
        transactions = migrate_transactions()
        
        create_sample_users()
        generate_sample_alerts()
        
        print("\n" + "=" * 50)
        print("✅ Migration Complete!")
        print(f"📊 Summary:")
        print(f"   - Customers: {customers}")
        print(f"   - Accounts: {accounts}")
        print(f"   - Transactions: {transactions}")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    main()