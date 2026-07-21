import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.models.user import User
from app.utils.security import hash_password

def create_users():
    db = SessionLocal()
    try:
        users = [
            {
                "username": "analyst",
                "email": "analyst@kyro.com",
                "full_name": "Compliance Analyst",
                "password": "kyro123",
                "role": "ANALYST"
            },
            {
                "username": "test_compliance",
                "email": "test_compliance@kyro.com",
                "full_name": "Test Compliance Officer",
                "password": "strongpassword123",
                "role": "COMPLIANCE_OFFICER"
            }
        ]
        
        for u in users:
            existing = db.query(User).filter(User.username == u["username"]).first()
            if existing:
                print(f"User {u['username']} already exists. Updating password...")
                existing.hashed_password = hash_password(u["password"])
                existing.role = u["role"]
            else:
                print(f"Creating user {u['username']}...")
                user = User(
                    username=u["username"],
                    email=u["email"],
                    full_name=u["full_name"],
                    hashed_password=hash_password(u["password"]),
                    role=u["role"],
                    is_active=True
                )
                db.add(user)
        db.commit()
        print("Successfully created/updated users.")
    except Exception as e:
        print("Error creating users:", e)
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_users()
