#!/usr/bin/env python3
"""
Quick script to check customer count in database
"""
import os
import sys

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.models.customer import Customer

def main():
    db = SessionLocal()
    try:
        count = db.query(Customer).count()
        print(f"📊 Total Customers in app.customers: {count:,}")
        
        # Get a few samples
        samples = db.query(Customer.id, Customer.full_name, Customer.email).limit(5).all()
        print(f"\n📝 Sample customers:")
        for customer in samples:
            print(f"  - {customer.full_name} ({customer.email})")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
