#!/usr/bin/env python3
"""
Show actual customer count from PostgreSQL database
"""
import psycopg2

def main():
    try:
        # Connect to database
        conn = psycopg2.connect(
            host="localhost",
            port=5434,
            database="kyro_aml",
            user="kyro_user",
            password="kyro_pass"
        )
        
        cursor = conn.cursor()
        
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM app.customers")
        total = cursor.fetchone()[0]
        print(f"\n📊 Total Customers in app.customers: {total:,}\n")
        
        # Get sample records
        cursor.execute("""
            SELECT id, full_name, email, risk_level, created_at 
            FROM app.customers 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        
        print("📝 Sample customers (latest 5):")
        print("-" * 80)
        for row in cursor.fetchall():
            print(f"  {row[1][:30]:30} | {row[2][:35]:35} | {row[3]}")
        print("-" * 80)
        
        # Get risk level distribution
        cursor.execute("""
            SELECT risk_level, COUNT(*) as count 
            FROM app.customers 
            GROUP BY risk_level 
            ORDER BY count DESC
        """)
        
        print("\n📈 Risk Level Distribution:")
        for row in cursor.fetchall():
            print(f"  {row[0]:10} : {row[1]:,}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        print("\n💡 Make sure:")
        print("  1. PostgreSQL is running")
        print("  2. Database 'kyro_aml' exists")
        print("  3. Port 5434 is accessible")

if __name__ == "__main__":
    main()
