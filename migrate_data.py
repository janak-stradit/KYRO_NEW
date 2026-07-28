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
            # First, count existing data
            cur.execute("SELECT COUNT(*) FROM raw_data.customers")
            raw_count = cur.fetchone()[0]
            print(f"📊 Raw data: {raw_count} customers")
            
            # Clear existing app data
            cur.execute("TRUNCATE TABLE app.customers CASCADE")
            
            # Migrate customers with proper UUID and schema mapping
            migrate_query = """
            INSERT INTO app.customers (
                id, full_name, email, phone, date_of_birth, 
                country, residency_country, kyc_status, pep_flag, 
                sanctions_flag, adverse_media_flag, risk_level, 
                risk_score, customer_type, created_at, updated_at
            )
            SELECT 
                gen_random_uuid() as id,
                full_name,
                email,
                phone_number as phone,
                date_of_birth::date,
                country,
                residency_country,
                CASE 
                    WHEN kyc_status IS NULL THEN 'PENDING'
                    ELSE UPPER(kyc_status)
                END as kyc_status,
                COALESCE(pep_flag, false) as pep_flag,
                COALESCE(sanctions_flag, false) as sanctions_flag,
                COALESCE(adverse_media_flag, false) as adverse_media_flag,
                CASE 
                    WHEN risk_score >= 70 THEN 'HIGH'
                    WHEN risk_score >= 40 THEN 'MEDIUM'
                    ELSE 'LOW'
                END as risk_level,
                COALESCE(risk_score, 0) as risk_score,
                CASE 
                    WHEN customer_type IS NULL THEN 'INDIVIDUAL'
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
            # Count raw accounts
            cur.execute("SELECT COUNT(*) FROM raw_data.accounts")
            raw_count = cur.fetchone()[0]
            print(f"📊 Raw data: {raw_count} accounts")
            
            # Clear existing app accounts
            cur.execute("TRUNCATE TABLE app.accounts CASCADE")
            
            # Migrate accounts
            migrate_query = """
            INSERT INTO app.accounts (
                id, customer_id, account_number, account_type, 
                currency, balance, status, opened_date, 
                created_at, updated_at
            )
            SELECT 
                gen_random_uuid() as id,
                c.id as customer_id,
                a.account_number,
                UPPER(a.account_type) as account_type,
                UPPER(a.currency) as currency,
                a.current_balance as balance,
                CASE 
                    WHEN a.status IS NULL THEN 'ACTIVE'
                    ELSE UPPER(a.status)
                END as status,
                a.opened_date::date,
                COALESCE(a.created_at, NOW()) as created_at,
                COALESCE(a.updated_at, NOW()) as updated_at
            FROM raw_data.accounts a
            JOIN raw_data.customers rc ON rc.customer_id = a.customer_id
            JOIN app.customers c ON c.email = rc.email
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
            # Count raw transactions
            cur.execute("SELECT COUNT(*) FROM raw_data.transactions")
            raw_count = cur.fetchone()[0]
            print(f"📊 Raw data: {raw_count} transactions")
            
            # Clear existing app transactions
            cur.execute("TRUNCATE TABLE app.transactions CASCADE")
            
            # Migrate transactions (batch by batch to avoid memory issues)
            batch_size = 10000
            offset = 0
            total_migrated = 0
            
            while True:
                migrate_query = f"""
                INSERT INTO app.transactions (
                    id, account_id, transaction_date, amount, currency,
                    transaction_type, description, counterparty_name,
                    counterparty_account, reference_number, 
                    created_at, updated_at
                )
                SELECT 
                    gen_random_uuid() as id,
                    acc.id as account_id,
                    t.transaction_date::timestamp with time zone,
                    t.amount,
                    UPPER(t.currency) as currency,
                    UPPER(t.transaction_type) as transaction_type,
                    t.description,
                    t.counterparty_name,
                    t.counterparty_account,
                    t.reference_number,
                    COALESCE(t.created_at, NOW()) as created_at,
                    COALESCE(t.updated_at, NOW()) as updated_at
                FROM raw_data.transactions t
                JOIN raw_data.accounts ra ON ra.account_id = t.account_id
                JOIN raw_data.customers rc ON rc.customer_id = ra.customer_id
                JOIN app.customers c ON c.email = rc.email
                JOIN app.accounts acc ON acc.customer_id = c.id AND acc.account_number = ra.account_number
                ORDER BY t.transaction_date
                LIMIT {batch_size} OFFSET {offset}
                """
                
                cur.execute(migrate_query)
                batch_count = cur.rowcount
                
                if batch_count == 0:
                    break
                    
                total_migrated += batch_count
                offset += batch_size
                
                print(f"📦 Migrated batch: {total_migrated}/{raw_count} transactions")
            
            print(f"✅ Migrated {total_migrated} transactions")
            return total_migrated

def create_sample_users():
    """Create sample users for login"""
    print("🔄 Creating sample users...")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Check if users exist
            cur.execute("SELECT COUNT(*) FROM app.users WHERE username = 'analyst'")
            if cur.fetchone()[0] > 0:
                print("👤 Sample users already exist")
                return
            
            # Create sample users
            users_query = """
            INSERT INTO app.users (id, username, email, full_name, hashed_password, role, is_active, created_at, updated_at)
            VALUES 
            (gen_random_uuid(), 'analyst', 'analyst@kyro.com', 'Test Analyst', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewEyKdyFFK/4V2r6', 'ANALYST', true, NOW(), NOW()),
            (gen_random_uuid(), 'admin', 'admin@kyro.com', 'System Admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewEyKdyFFK/4V2r6', 'ADMIN', true, NOW(), NOW()),
            (gen_random_uuid(), 'compliance', 'compliance@kyro.com', 'Compliance Officer', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewEyKdyFFK/4V2r6', 'COMPLIANCE_OFFICER', true, NOW(), NOW())
            """
            
            cur.execute(users_query)
            print("✅ Created sample users (password: kyro123)")
            print("   - analyst@kyro.com (ANALYST)")
            print("   - admin@kyro.com (ADMIN)")
            print("   - compliance@kyro.com (COMPLIANCE_OFFICER)")

def generate_sample_alerts():
    """Generate some sample alerts for dashboard"""
    print("🔄 Generating sample alerts...")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Clear existing alerts
            cur.execute("TRUNCATE TABLE app.alerts CASCADE")
            
            # Generate alerts for high-risk transactions
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
                id, customer_id, transaction_id, alert_type, 
                risk_score, confidence, status, priority,
                description, created_at, updated_at
            )
            SELECT 
                gen_random_uuid(),
                customer_id,
                transaction_id,
                alert_type,
                risk_score::int,
                (0.7 + RANDOM() * 0.3)::numeric(3,2),
                CASE (RANDOM() * 4)::int
                    WHEN 0 THEN 'OPEN'
                    WHEN 1 THEN 'ASSIGNED' 
                    WHEN 2 THEN 'IN_REVIEW'
                    ELSE 'RESOLVED'
                END,
                CASE 
                    WHEN risk_score > 80 THEN 'HIGH'
                    WHEN risk_score > 60 THEN 'MEDIUM'
                    ELSE 'LOW'
                END,
                CASE alert_type
                    WHEN 'LARGE_AMOUNT' THEN 'Large transaction amount detected'
                    WHEN 'WIRE_TRANSFER' THEN 'Wire transfer requires review'
                    WHEN 'HIGH_RISK_CUSTOMER' THEN 'Transaction from high-risk customer'
                    ELSE 'Unusual transaction pattern detected'
                END,
                transaction_date - (RANDOM() * INTERVAL '24 hours'),
                transaction_date - (RANDOM() * INTERVAL '12 hours')
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
        # Migrate core data
        customers = migrate_customers()
        accounts = migrate_accounts() 
        transactions = migrate_transactions()
        
        # Create users and sample data
        create_sample_users()
        generate_sample_alerts()
        
        print("\n" + "=" * 50)
        print("✅ Migration Complete!")
        print(f"📊 Summary:")
        print(f"   - Customers: {customers}")
        print(f"   - Accounts: {accounts}")
        print(f"   - Transactions: {transactions}")
        print(f"   - Users: 3 created")
        print(f"   - Sample alerts generated")
        print("\n🔐 Login credentials:")
        print("   Username: analyst")
        print("   Password: kyro123")
        print(f"\n🌐 Frontend: http://localhost:3001/phase3/login.html")
        print(f"🔧 API: http://localhost:8000/docs")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    main()