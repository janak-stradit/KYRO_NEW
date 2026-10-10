"""
routers/feeds.py — Data-feed field mapping (Phase 11.4 step 4): preview a
client CSV, save the column mapping, check the file and load it. Also starts
and stops the live synthetic feed.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_permission
from app.models.feed import FeedMapping, FeedRun
from app.models.user import User
from app.services import feed_service, live_feed_service
from app.services.feed_service import FeedError
from app.services.live_feed_service import LiveFeedError

router = APIRouter(prefix="/api/v1/feeds", tags=["feeds"], dependencies=[Depends(get_current_user)])

Target = Literal["CUSTOMERS", "ACCOUNTS", "TRANSACTIONS"]


class MappingIn(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    target: Target
    mapping: dict[str, str]
    date_day_first: bool = True


class MappingOut(MappingIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mapping_id: uuid.UUID | None = None
    target: str
    filename: str
    dry_run: bool
    rows_total: int
    rows_valid: int
    rows_loaded: int
    rows_skipped_existing: int
    rows_invalid: int
    errors: list[dict[str, Any]] | None = None
    run_at: datetime


class LiveStartIn(BaseModel):
    per_minute: int = Field(default=live_feed_service.DEFAULT_PER_MINUTE, ge=1, le=live_feed_service.MAX_PER_MINUTE)


class LiveOut(BaseModel):
    enabled: bool
    running: bool
    per_minute: int
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    started_by: str | None = None
    transactions: int
    flagged: int
    alerts: int
    anomalies: int
    ai_unavailable: str | None = None  # why transactions are not being ML-scored
    last_error: str | None = None
    recent: list[dict[str, Any]]


def _fail(exc: FeedError | LiveFeedError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


@router.post("/preview")
async def preview(
    target: Target = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_permission("feeds.load")),
) -> dict[str, Any]:
    """Read a CSV's header and first rows and suggest which column is which KYRO field."""
    try:
        return feed_service.preview(target, await file.read(feed_service.MAX_BYTES + 1))
    except FeedError as exc:
        raise _fail(exc) from None


@router.get("/mappings", response_model=list[MappingOut])
def list_mappings(db: Session = Depends(get_db)) -> list[FeedMapping]:
    return db.query(FeedMapping).order_by(FeedMapping.name).all()


@router.post("/mappings", response_model=MappingOut, status_code=status.HTTP_201_CREATED)
def save_mapping(
    data: MappingIn, db: Session = Depends(get_db), user: User = Depends(require_permission("feeds.load"))
) -> FeedMapping:
    """Save a mapping under a name so the next file from the same source needs no setup."""
    fields = {f.name for f in feed_service.TARGETS[data.target]}
    unknown = sorted(set(data.mapping) - fields)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Not a field for {data.target.lower()}: {', '.join(unknown)}")
    mapping = db.query(FeedMapping).filter(FeedMapping.name == data.name.strip()).first()
    if mapping is None:
        mapping = FeedMapping(name=data.name.strip(), created_by=user.id)
        db.add(mapping)
    mapping.target = data.target
    mapping.mapping = {k: v for k, v in data.mapping.items() if v}
    mapping.date_day_first = data.date_day_first
    db.commit()
    db.refresh(mapping)
    return mapping


@router.post("/run", response_model=RunOut)
async def run_feed(
    target: Target = Form(...),
    mapping: str = Form(..., description="JSON object: KYRO field -> column in the file"),
    dry_run: bool = Form(True),
    skip_invalid: bool = Form(False),
    date_day_first: bool = Form(True),
    mapping_id: uuid.UUID | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("feeds.load")),
) -> FeedRun:
    """
    Check every row of the file against the mapping. With dry_run=false the
    valid rows are loaded; nothing is loaded if any row is invalid unless
    skip_invalid=true.
    """
    try:
        parsed = json.loads(mapping)
        if not isinstance(parsed, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()):
            raise ValueError
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "mapping must be a JSON object of field -> column") from None
    try:
        return feed_service.run(
            db, target=target, mapping=parsed, data=await file.read(feed_service.MAX_BYTES + 1),
            filename=file.filename or "feed.csv", day_first=date_day_first, dry_run=dry_run,
            skip_invalid=skip_invalid, mapping_id=mapping_id, user_id=user.id,
        )
    except FeedError as exc:
        db.rollback()
        raise _fail(exc) from None


@router.get("/runs", response_model=list[RunOut])
def list_runs(db: Session = Depends(get_db)) -> list[FeedRun]:
    return db.query(FeedRun).order_by(FeedRun.run_at.desc()).limit(50).all()


@router.get("/live", response_model=LiveOut)
def live_status() -> dict[str, Any]:
    return live_feed_service.status()


@router.post("/live/start", response_model=LiveOut)
def live_start(
    data: LiveStartIn, db: Session = Depends(get_db), user: User = Depends(require_permission("feeds.load"))
) -> dict[str, Any]:
    """Start sending synthetic transactions through the rules engine until stopped."""
    try:
        return live_feed_service.start(db, per_minute=data.per_minute, user_id=user.id, username=user.username)
    except LiveFeedError as exc:
        raise _fail(exc) from None


@router.post("/live/stop", response_model=LiveOut)
def live_stop(user: User = Depends(require_permission("feeds.load"))) -> dict[str, Any]:
    return live_feed_service.stop()
