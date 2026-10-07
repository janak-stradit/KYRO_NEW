"""
main.py — FastAPI application entry point for the KYRO Risk Assessment API.
Run with: uvicorn app.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.rate_limit import limiter
from app.routers import (
    accounts,
    alerts,
    auth,
    beneficial_owners,
    customers,
    dashboard,
    kyc,
    kyrochat,
    ml,
    rule_configs,
    transactions,
    tts,
    watchlists,
)

settings = get_settings()


def _seed_default_users() -> None:
    """Create default demo users if they don't already exist."""
    from app.database import SessionLocal
    from app.models.user import User
    from app.utils.security import hash_password

    default_users = [
        {
            "username": "admin",
            "email": "admin@kyro.local",
            "full_name": "KYRO Admin",
            "hashed_password": hash_password("admin123"),
            "role": "ADMIN",
        },
        {
            "username": "analyst",
            "email": "analyst@kyro.local",
            "full_name": "KYRO Analyst",
            "hashed_password": hash_password("kyro123"),
            "role": "ANALYST",
        },
        {
            "username": "compliance",
            "email": "compliance@kyro.local",
            "full_name": "KYRO Compliance Officer",
            "hashed_password": hash_password("kyro123"),
            "role": "COMPLIANCE_OFFICER",
        },
    ]

    db = SessionLocal()
    try:
        for u in default_users:
            exists = db.query(User).filter(User.username == u["username"]).first()
            if not exists:
                db.add(User(**u, is_active=True))
        db.commit()
    except Exception as exc:
        db.rollback()
        import logging
        logging.getLogger("kyro.main").warning("User seed failed: %s", exc)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _seed_default_users()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", debug=settings.debug, lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(customers.router)
app.include_router(beneficial_owners.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(alerts.router)
app.include_router(kyc.router)
app.include_router(watchlists.router)
app.include_router(rule_configs.router)
app.include_router(ml.router)
app.include_router(kyrochat.router)
app.include_router(tts.router)


@app.get("/api/v1/health", tags=["health"])
@limiter.exempt
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
