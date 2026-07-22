"""
main.py — FastAPI application entry point for the KYRO Risk Assessment API.
Run with: uvicorn app.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import accounts, alerts, auth, customers, dashboard, kyc, ml, transactions, kyrochat, tts

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0", debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(customers.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(alerts.router)
app.include_router(kyc.router)
app.include_router(ml.router)
app.include_router(kyrochat.router)
app.include_router(tts.router)


@app.get("/api/v1/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
