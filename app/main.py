"""
main.py — FastAPI application entry point for the KYRO Risk Assessment API.
Run with: uvicorn app.main:app --reload
"""
from __future__ import annotations

import importlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.rate_limit import limiter
from app.routers import (
    accounts,
    ai,
    alerts,
    auth,
    beneficial_owners,
    change_management,
    customers,
    dashboard,
    documents,
    feeds,
    kyc,
    kyrochat,
    regulatory,
    rule_configs,
    transactions,
    tts,
    watchlists,
)

settings = get_settings()
logger = logging.getLogger("kyro.main")


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
        logger.warning("User seed failed: %s", exc)
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
app.include_router(ai.router)
app.include_router(dashboard.router)
app.include_router(customers.router)
app.include_router(beneficial_owners.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(alerts.router)
app.include_router(kyc.router)
app.include_router(watchlists.router)
app.include_router(rule_configs.router)
app.include_router(regulatory.router)
app.include_router(change_management.router)
app.include_router(documents.router)
app.include_router(feeds.router)
try:
    app.include_router(importlib.import_module("app.routers.ml").router)
except ImportError as exc:
    # Lets the API run on machines where the ML stack can't load (e.g. Windows
    # Smart App Control blocking scikit-learn/pandas DLLs). Off by default so a
    # broken ML install fails loudly in production.
    if not settings.ml_optional:
        raise
    logger.error("ML endpoints disabled — ML dependencies failed to import: %s", exc)
app.include_router(kyrochat.router)
app.include_router(tts.router)


@app.get("/api/v1/health", tags=["health"])
@limiter.exempt
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


# Local (non-Docker) runs: serve the static frontend from the API so the
# frontend's relative /api/v1 calls stay same-origin, as nginx does in Docker.
# Mounted last so every API route above takes precedence.
class _FrontendStaticFiles(StaticFiles):
    """Static files with nginx's `try_files $uri $uri.html $uri/ /index.html`
    behaviour, so clean URLs like /dashboard resolve as they do in Docker."""

    async def get_response(self, path: str, scope):
        response = await self._resolve(path, scope)
        # Revalidate on every load (cheap 304s via ETag) so frontend edits
        # show up without a hard refresh.
        response.headers["Cache-Control"] = "no-cache"
        return response

    async def _resolve(self, path: str, scope):
        for candidate in (path, f"{path}.html"):
            try:
                return await super().get_response(candidate, scope)
            except StarletteHTTPException as exc:
                if exc.status_code != 404:
                    raise
        if path.replace("\\", "/").startswith("api/"):
            raise StarletteHTTPException(status_code=404)
        return await super().get_response("index.html", scope)


if settings.serve_frontend_dir:
    _frontend_dir = Path(settings.serve_frontend_dir)
    if _frontend_dir.is_dir():
        app.mount("/", _FrontendStaticFiles(directory=_frontend_dir, html=True), name="frontend")
    else:
        logger.warning("SERVE_FRONTEND_DIR %s does not exist; frontend not served", _frontend_dir)
