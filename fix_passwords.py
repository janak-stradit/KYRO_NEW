#!/usr/bin/env python3
"""
Fix user passwords in the database
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import get_settings
from app.models.user import User
from app.utils.security import hash_password

def fix_passwords():
    """Update user passwords"""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        print("🔐 Updating user passwords...")
        
        # Update admin password
        admin = db.query(User).filter(User.username == "admin").first()
        if admin:
            admin.hashed_password = hash_password("admin123")
            print("✅ Updated admin password to: admin123")
        else:
            print("⚠️  Admin user not found, creating...")
            from datetime import datetime, timezone
            import uuid
            admin = User(
                id=str(uuid.uuid4()),
                username="admin",
                email="admin@kyro.com",
                full_name="System Administrator",
                hashed_password=hash_password("admin123"),
                role="ADMIN",
                is_active=True,
                created_at=datetime.now(timezone.utc)
            )
            db.add(admin)
            print("✅ Created admin user: admin/admin123")
        
        # Update analyst password
        analyst = db.query(User).filter(User.username == "analyst").first()
        if analyst:
            analyst.hashed_password = hash_password("kyro123")
            print("✅ Updated analyst password to: kyro123")
        else:
            print("⚠️  Analyst user not found, creating...")
            from datetime import datetime, timezone
            import uuid
            analyst = User(
                id=str(uuid.uuid4()),
                username="analyst",
                email="analyst@kyro.com",
                full_name="Compliance Analyst",
                hashed_password=hash_password("kyro123"),
                role="ANALYST",
                is_active=True,
                created_at=datetime.now(timezone.utc)
            )
            db.add(analyst)
            print("✅ Created analyst user: analyst/kyro123")
        
        db.commit()
        print("\n✅ Passwords fixed successfully!")
        print("🔐 Login credentials:")
        print("   - admin/admin123 (Administrator)")
        print("   - analyst/kyro123 (Analyst)")
        
    except Exception as e:
        print(f"❌ Error fixing passwords: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    fix_passwords()
