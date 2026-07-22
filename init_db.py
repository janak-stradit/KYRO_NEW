#!/usr/bin/env python3
"""
Initialize KYRO database and create sample data
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine
from app.models.base import Base
from app.config import get_settings
from app.models.customer import Customer
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.alert import Alert
from app.models.user import User
from app.models.ml_score import MLScore
from app.models.audit import AuditLog
from app.utils.security import hash_password
from datetime import datetime, timezone
import uuid

def init_database():
    """Initialize database with tables and sample data"""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    
    print("🗄️ Creating database tables...")
    Base.metadata.create_all(engine)
    
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Check if we already have data
        if db.query(Customer).count() > 0:
            print("✅ Database already initialized with data")
            return
        
        print("📊 Creating sample data...")
        
        # Create sample users
        admin_user = User(
            id=str(uuid.uuid4()),
            username="admin",
            email="admin@kyro.com",
            full_name="System Administrator",
            hashed_password=hash_password("admin123"),
            role="ADMIN",
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )
        
        analyst_user = User(
            id=str(uuid.uuid4()),
            username="analyst",
            email="analyst@kyro.com", 
            full_name="Compliance Analyst",
            hashed_password=hash_password("kyro123"),
            role="ANALYST",
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )
        
        db.add_all([admin_user, analyst_user])
        
        # Create sample customers
        customers = [
            Customer(
                id=str(uuid.uuid4()),
                full_name="John Doe",
                email="john.doe@email.com",
                phone="+1234567890",
                address="123 Main St, City, State 12345",
                date_of_birth=datetime(1985, 3, 15).date(),
                risk_level="MEDIUM",
                risk_score=65.5,
                customer_type="INDIVIDUAL",
                onboarding_date=datetime.now(timezone.utc),
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ),
            Customer(
                id=str(uuid.uuid4()),
                full_name="Jane Smith Corp",
                email="contact@janesmith.com",
                phone="+1987654321",
                address="456 Business Ave, City, State 54321",
                risk_level="HIGH",
                risk_score=85.2,
                customer_type="BUSINESS", 
                onboarding_date=datetime.now(timezone.utc),
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ),
            Customer(
                id=str(uuid.uuid4()),
                full_name="Apex Global Corp",
                email="info@apexglobal.com",
                phone="+1555123456",
                address="789 Corporate Blvd, City, State 67890", 
                risk_level="HIGH",
                risk_score=87.5,
                customer_type="BUSINESS",
                onboarding_date=datetime.now(timezone.utc),
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
        ]
        
        db.add_all(customers)
        db.commit()
        
        # Create sample accounts
        accounts = []
        for customer in customers:
            account = Account(
                id=str(uuid.uuid4()),
                customer_id=customer.id,
                account_number=f"ACC{len(accounts)+1:06d}",
                account_type="CHECKING",
                balance=50000.00 + (len(accounts) * 25000),
                currency="USD",
                status="ACTIVE",
                opened_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            accounts.append(account)
        
        db.add_all(accounts)
        db.commit()
        
        # Create sample alerts
        alerts = [
            Alert(
                id=str(uuid.uuid4()),
                customer_id=customers[1].id,  # Jane Smith Corp
                alert_type="VELOCITY_SPIKE",
                severity="HIGH",
                risk_score=85.2,
                confidence=0.92,
                description="Unusual transaction velocity detected - 15 large transfers in 2 hours",
                status="OPEN",
                recommended_action="ESCALATE",
                is_false_positive=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ),
            Alert(
                id=str(uuid.uuid4()),
                customer_id=customers[2].id,  # Apex Global Corp
                alert_type="GEOGRAPHIC_SHIFT",
                severity="HIGH", 
                risk_score=87.5,
                confidence=0.88,
                description="Cross-border wire transfers to high-risk jurisdictions",
                status="OPEN",
                recommended_action="INVESTIGATE",
                is_false_positive=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ),
            Alert(
                id=str(uuid.uuid4()),
                customer_id=customers[0].id,  # John Doe
                alert_type="THRESHOLD_BREACH",
                severity="MEDIUM",
                risk_score=65.5,
                confidence=0.75,
                description="Single large transaction exceeds customer profile",
                status="ASSIGNED",
                assigned_to=analyst_user.id,
                recommended_action="REVIEW",
                is_false_positive=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
        ]
        
        db.add_all(alerts)
        
        # Create sample transactions
        transactions = [
            Transaction(
                id=str(uuid.uuid4()),
                account_id=accounts[0].id,
                transaction_type="WIRE_TRANSFER",
                amount=25000.00,
                currency="USD",
                description="Wire transfer to business partner",
                counterparty="Business Partner LLC",
                transaction_date=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ),
            Transaction(
                id=str(uuid.uuid4()),
                account_id=accounts[1].id,
                transaction_type="WIRE_TRANSFER", 
                amount=75000.00,
                currency="USD",
                description="International wire transfer",
                counterparty="Offshore Entity",
                transaction_date=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
        ]
        
        db.add_all(transactions)
        db.commit()
        
        print("✅ Database initialized successfully!")
        print(f"📊 Created {len(customers)} customers, {len(accounts)} accounts, {len(alerts)} alerts")
        print("🔐 Default users:")
        print("   - admin/admin123 (Administrator)")
        print("   - analyst/kyro123 (Analyst)")
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    init_database()