"""
ai/retrieval.py — Index and search the knowledge store (Phase 11.0.5).

    index_text(db, source_type="REGULATION", source_ref="31 CFR 1023.320",
               version="2026-01-01", title="Reports by brokers or dealers ...", text=body)
    hits = search(db, "when must a broker-dealer file a SAR?")

Search is keyword-based (PostgreSQL full-text). A question matches a chunk if
they share any meaningful term; chunks sharing more terms, or matching in the
source reference or title, rank higher. Vector similarity is merged in here
once embeddings are available (docs/plans/COMPLIANCE_AI_PLAN.md §9.2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text as sql
from sqlalchemy.orm import Session

from app.models.knowledge_chunk import KnowledgeChunk


@dataclass
class SearchHit:
    chunk: KnowledgeChunk
    score: float
    coverage: float  # share of the question's terms found in the chunk, 0–1


def chunk_text(text: str, *, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Split on paragraph boundaries into chunks of at most `max_chars`."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        # A single oversized paragraph is cut into overlapping windows
        while len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars - overlap:]
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks


def index_text(
    db: Session,
    *,
    source_type: str,
    source_ref: str,
    version: str,
    text: str,
    title: str | None = None,
    citation: str | None = None,
    meta: dict[str, Any] | None = None,
) -> int:
    """
    Store `text` as chunks for one version of a source. Re-indexing the same
    version replaces its chunks; other versions of the source stay for
    point-in-time lookups but stop being current. The caller commits.
    """
    same_source = db.query(KnowledgeChunk).filter(
        KnowledgeChunk.source_type == source_type, KnowledgeChunk.source_ref == source_ref
    )
    same_source.filter(KnowledgeChunk.version == version).delete(synchronize_session=False)
    same_source.update({KnowledgeChunk.is_current: False}, synchronize_session=False)

    chunks = chunk_text(text)
    db.add_all(
        KnowledgeChunk(
            source_type=source_type,
            source_ref=source_ref,
            version=version,
            title=title,
            citation=citation,
            chunk_index=i,
            content=chunk,
            meta=meta,
        )
        for i, chunk in enumerate(chunks)
    )
    db.flush()
    return len(chunks)


def search(
    db: Session,
    query: str,
    *,
    limit: int = 5,
    source_type: str | None = None,
    current_only: bool = True,
    min_coverage: float = 0.4,
) -> list[SearchHit]:
    if not query or not query.strip():
        return []
    # plainto_tsquery ANDs the terms; a question rarely appears word for word
    # in one chunk, so OR them and let the ranking favour fuller matches.
    # `coverage` is the share of the question's terms found in the chunk; below
    # `min_coverage` a hit is a chance word overlap, and returning nothing lets
    # the caller say "not found in sources" instead of guessing.
    rows = db.execute(
        sql(
            """
            WITH q AS (
                SELECT NULLIF(replace(plainto_tsquery('english', :query)::text, '&', '|'), '')::tsquery AS tsq,
                       tsvector_to_array(to_tsvector('english', :query)) AS terms
            ), matched AS (
                SELECT c.id, c.source_ref, c.chunk_index,
                       ts_rank_cd(c.content_tsv, q.tsq) AS score,
                       cardinality(ARRAY(
                           SELECT unnest(q.terms) INTERSECT SELECT unnest(tsvector_to_array(c.content_tsv))
                       ))::float / GREATEST(cardinality(q.terms), 1) AS coverage
                FROM app.knowledge_chunks c, q
                WHERE c.content_tsv @@ q.tsq
                  AND (CAST(:source_type AS text) IS NULL OR c.source_type = :source_type)
                  AND (NOT :current_only OR c.is_current)
            )
            SELECT id, score, coverage FROM matched
            WHERE coverage >= :min_coverage
            ORDER BY score DESC, source_ref, chunk_index
            LIMIT :limit
            """
        ),
        {
            "query": query,
            "source_type": source_type,
            "current_only": current_only,
            "min_coverage": min_coverage,
            "limit": limit,
        },
    ).all()
    if not rows:
        return []
    chunks = {c.id: c for c in db.query(KnowledgeChunk).filter(KnowledgeChunk.id.in_([r.id for r in rows]))}
    return [SearchHit(chunk=chunks[r.id], score=float(r.score), coverage=float(r.coverage)) for r in rows]
