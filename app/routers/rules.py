"""
routers/rules.py — Rules engine operations: replay before a change, and the
exchange rates the engine converts amounts with (rules engine R1).
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_permission
from app.models.user import User
from app.services import fx_service, rules_replay
from app.services.rules_engine import RuleOptions

router = APIRouter(prefix="/api/v1/rules", tags=["rules"], dependencies=[Depends(get_current_user)])


class ReplayRequest(BaseModel):
    start: datetime
    end: datetime
    base_currency: bool = True
    noise_reduction: bool = True
    limit: int = Field(default=rules_replay.MAX_TRANSACTIONS, ge=1, le=rules_replay.MAX_TRANSACTIONS)

    @model_validator(mode="after")
    def _ordered(self) -> "ReplayRequest":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


@router.get("/options")
def current_options(_: User = Depends(require_permission("cases.view"))) -> dict:
    """Which R1 switches are on (set in the environment, see .env.example)."""
    options = RuleOptions.from_settings()
    return {**asdict(options), "signature": options.signature()}


@router.post("/replay")
def replay(data: ReplayRequest, db: Session = Depends(get_db), _: User = Depends(require_permission("rules.propose"))) -> dict:
    """Re-run the rules over a past period with the current and the proposed switches. Writes nothing."""
    proposed = RuleOptions(base_currency=data.base_currency, noise_reduction=data.noise_reduction)
    start = data.start if data.start.tzinfo else data.start.replace(tzinfo=timezone.utc)
    end = data.end if data.end.tzinfo else data.end.replace(tzinfo=timezone.utc)
    return rules_replay.replay(db, start, end, proposed, limit=data.limit)


@router.get("/fx")
def fx_status(db: Session = Depends(get_db), _: User = Depends(require_permission("cases.view"))) -> dict:
    return fx_service.status(db)


@router.post("/fx/refresh")
def fx_refresh(db: Session = Depends(get_db), _: User = Depends(require_permission("feeds.load"))) -> dict:
    """Load today's ECB reference rates and convert transactions that had no base amount yet."""
    try:
        result = fx_service.refresh_from_ecb(db)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not load exchange rates: {exc}") from None
    return {"stored": result["stored"], "rate_date": result["rate_date"].isoformat() if result["rate_date"] else None,
            "backfilled": fx_service.backfill_amount_base(db)}
