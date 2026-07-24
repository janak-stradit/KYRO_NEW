#!/usr/bin/env python3
import sys
sys.path.insert(0, "/app")

from generator.data_generator import generate_dataset
import psycopg

DATABASE_URL = "postgresql://kyro_user:kyro_pass@postgres:5432/kyro_aml"

def main():
    conn = psycopg.connect(DATABASE_URL)
    cur = conn.cursor()
    
    for start_id in range(1, 10001, 1000):
        print(f"📊 Generating customers {start_id} to {start_id+999}...")
        dataset = generate_dataset(1000, start_id)
        
        customers = [
            (c["customer_id"], c["full_name"], c["email"], c["phone"], 
             c["date_of_birth"], c["country"], c["residency_country"], 
             c["kyc_status"], c["pep_flag"], c["sanctions_flag"], 
             c["adverse_media_flag"], c["risk_level"], c["risk_score"], 
             c["customer_type"]) 
            for c in dataset["customers"]
        ]
        
        cur.executemany(
            "INSERT INTO raw_data.customers (customer_id, full_name, email, phone, date_of_birth, country, residency_country, kyc_status, pep_flag, sanctions_flag, adverse_media_flag, risk_level, risk_score, customer_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            customers
        )
        
        conn.commit()
        print(f"✅ Batch {start_id//1000 + 1}/10 completed")
    
    cur.close()
    conn.close()
    print("=" * 70)
    print("✅ ALL 10,000 CUSTOMERS LOADED INTO raw_data.customers!")
    print("=" * 70)

if __name__ == "__main__":
    main()
