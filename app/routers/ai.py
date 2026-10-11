"""
routers/ai.py — Admin endpoints for the Compliance AI foundation (Phase 11.0).
"""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai import AIDisabledError, AIGateway, AIProviderError
from app.ai.retrieval import search
from app.database import get_db
from app.deps import get_current_user, require_permission
from app.models.ai_interaction import AIInteraction
from app.models.user import User

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.get("/status")
def ai_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ai.status")),
) -> dict[str, Any]:
    """Current AI configuration. Never returns the API key."""
    return AIGateway(db).status()


@router.get("/search")
def knowledge_search(
    q: str = Query(min_length=2, max_length=500),
    source_type: str | None = Query(None, pattern="^(REGULATION|POLICY|DOCUMENT)$"),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Keyword search over the knowledge store. An empty list means "not found in sources"."""
    hits = search(db, q, limit=limit, source_type=source_type)
    return {
        "query": q,
        "results": [
            {
                "source_type": h.chunk.source_type,
                "source_ref": h.chunk.source_ref,
                "version": h.chunk.version,
                "title": h.chunk.title,
                "citation": h.chunk.citation,
                "content": h.chunk.content,
                "score": round(h.score, 4),
                "coverage": round(h.coverage, 2),
            }
            for h in hits
        ],
    }


@router.get("/oversight")
def oversight(db: Session = Depends(get_db), _: User = Depends(require_permission("ai.status"))) -> list[dict[str, Any]]:
    """
    For each prompt version: how many outputs were produced, and how many investigators accepted,
    corrected or rejected, or have not yet reviewed. A rising correction or rejection rate is a
    model-risk signal.
    """
    rows = (
        db.query(AIInteraction.feature, AIInteraction.prompt_id, AIInteraction.prompt_version, AIInteraction.human_decision,
                 func.count(AIInteraction.id))
        .filter(AIInteraction.status == "SUCCESS")
        .group_by(AIInteraction.feature, AIInteraction.prompt_id, AIInteraction.prompt_version, AIInteraction.human_decision)
        .all()
    )
    out: dict[tuple, dict[str, Any]] = {}
    for feature, prompt_id, version, decision, n in rows:
        entry = out.setdefault((prompt_id, version), {
            "feature": feature, "prompt_id": prompt_id, "prompt_version": version,
            "outputs": 0, "accepted": 0, "edited": 0, "rejected": 0, "not_reviewed": 0,
        })
        entry["outputs"] += n
        entry[{"ACCEPTED": "accepted", "EDITED": "edited", "REJECTED": "rejected"}.get(decision, "not_reviewed")] += n
    return sorted(out.values(), key=lambda e: (e["prompt_id"], -e["prompt_version"]))


@router.post("/check")
def ai_check(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("ai.admin")),
) -> dict[str, Any]:
    """Round-trips a no-PII test prompt through the gateway and reports the result."""
    nonce = secrets.token_hex(4)
    gateway = AIGateway(db)
    try:
        result = gateway.run("system.connectivity_check", {"nonce": nonce}, requested_by=user.id)
    except AIDisabledError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except AIProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None

    echoed = bool(result.data and result.data.get("echo") == nonce)
    return {
        "ok": echoed,
        "provider": result.provider,
        "model": result.model,
        "latency_ms": result.latency_ms,
        "interaction_id": str(result.interaction_id),
        "warnings": result.warnings + ([] if echoed else ["Model reply did not echo the check value"]),
    }
