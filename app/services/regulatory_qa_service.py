"""
services/regulatory_qa_service.py — Answers regulatory questions from the
knowledge store only (Phase 11.3 step 3).

Three outcomes, reported in `mode`:
  * NOT_FOUND  — nothing relevant in the sources; no answer is attempted.
  * GENERATED  — the AI summarised the retrieved passages. Any citation it
                 gives that is not one of those passages is dropped, and an
                 answer left with no valid citation is marked unverified.
  * EXTRACTIVE — AI is off or in mock mode; the passages themselves are
                 returned so the analyst can read the source text.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.ai import AIGateway, AIProviderError
from app.ai.retrieval import SearchHit, search
from app.config import get_settings

NOT_FOUND_MESSAGE = "Not found in the regulatory sources KYRO has loaded."


def _source(hit: SearchHit) -> dict[str, Any]:
    chunk = hit.chunk
    return {
        "source_ref": chunk.source_ref,
        "source_type": chunk.source_type,
        "title": chunk.title,
        "version": chunk.version,
        "url": (chunk.meta or {}).get("url"),
        "excerpt": chunk.content,
        "coverage": round(hit.coverage, 2),
    }


def ask(db: Session, question: str, *, requested_by: uuid.UUID | None = None, limit: int = 5) -> dict[str, Any]:
    hits = search(db, question, limit=limit)
    result: dict[str, Any] = {
        "question": question,
        "mode": "NOT_FOUND",
        "answer": None,
        "citations": [],
        "verified": False,
        "sources": [_source(h) for h in hits],
        "interaction_id": None,
        "warnings": [],
    }
    if not hits:
        result["answer"] = NOT_FOUND_MESSAGE
        return result

    settings = get_settings()
    if not settings.kyro_ai_enabled or settings.kyro_llm_mock:
        result["mode"] = "EXTRACTIVE"
        result["citations"] = list(dict.fromkeys(s["source_ref"] for s in result["sources"]))
        result["verified"] = True  # the passages are the source text itself
        result["warnings"].append("AI summarisation is off; showing the most relevant source passages.")
        return result

    excerpts = "\n\n".join(
        f"[{i}] {s['source_ref']} — {s['title'] or ''} (version {s['version']})\n{s['excerpt']}"
        for i, s in enumerate(result["sources"], start=1)
    )
    try:
        ai = AIGateway(db).run(
            "regulatory.answer", {"question": question, "excerpts": excerpts}, requested_by=requested_by
        )
    except AIProviderError as exc:
        result["mode"] = "EXTRACTIVE"
        result["citations"] = list(dict.fromkeys(s["source_ref"] for s in result["sources"]))
        result["verified"] = True
        result["warnings"].append(f"AI summarisation failed ({exc}); showing the source passages instead.")
        return result

    result["interaction_id"] = str(ai.interaction_id)
    result["warnings"] += ai.warnings
    data = ai.data or {}
    answer = str(data.get("answer") or "").strip()
    if not data.get("found") or not answer:
        result["answer"] = NOT_FOUND_MESSAGE
        return result

    retrieved = {s["source_ref"] for s in result["sources"]}
    cited = [str(c) for c in data.get("citations") or []]
    valid = [c for c in dict.fromkeys(cited) if c in retrieved]
    if len(valid) < len(set(cited)):
        result["warnings"].append("Dropped citations that were not among the retrieved sources.")

    result.update(mode="GENERATED", answer=answer, citations=valid, verified=bool(valid))
    if not valid:
        result["warnings"].append("Unverified: the answer cites none of the retrieved sources.")
    return result
