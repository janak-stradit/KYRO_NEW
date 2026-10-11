"""
tests/ai_eval/test_retrieval_eval.py — Does search return the right source?
Thresholds: correct source ranked first for >= 85% of questions and within the
top 3 for all of them; questions outside the corpus return nothing.
"""
from __future__ import annotations

import pytest

from app.ai.retrieval import chunk_text, index_text, search
from app.models.knowledge_chunk import KnowledgeChunk

pytestmark = pytest.mark.db

TOP1_THRESHOLD = 0.85
TOP3_THRESHOLD = 1.0


@pytest.fixture
def corpus(db_session, golden):
    data = golden("retrieval")
    # Only the golden corpus should be searchable for the duration of the test
    db_session.query(KnowledgeChunk).update({KnowledgeChunk.is_current: False}, synchronize_session=False)
    for doc in data["corpus"]:
        index_text(db_session, version=data["version"], **doc)
    db_session.commit()
    return data


def test_retrieval_golden_set_meets_thresholds(db_session, corpus):
    top1 = top3 = 0
    misses = []
    for item in corpus["questions"]:
        refs = [hit.chunk.source_ref for hit in search(db_session, item["q"], limit=3)]
        top1 += refs[:1] == [item["expected"]]
        top3 += item["expected"] in refs
        if refs[:1] != [item["expected"]]:
            misses.append((item["q"], refs))

    total = len(corpus["questions"])
    assert top3 / total >= TOP3_THRESHOLD, f"top-3 {top3}/{total}; misses: {misses}"
    assert top1 / total >= TOP1_THRESHOLD, f"top-1 {top1}/{total}; misses: {misses}"


def test_out_of_corpus_questions_return_nothing(db_session, corpus):
    for question in corpus["out_of_corpus"]:
        assert search(db_session, question) == [], question


def test_reindexing_a_new_version_supersedes_the_old_one(db_session, corpus):
    index_text(
        db_session, source_type="POLICY", source_ref="Internal Policy AML-07", version="eval-2",
        title="Periodic KYC review cycles", text="High-risk customers are re-reviewed every 6 months.",
    )
    db_session.commit()

    current = search(db_session, "high-risk customers re-reviewed", limit=10)
    assert [h.chunk.version for h in current if h.chunk.source_ref == "Internal Policy AML-07"] == ["eval-2"]
    history = search(db_session, "high-risk customers re-reviewed", limit=10, current_only=False)
    assert {h.chunk.version for h in history if h.chunk.source_ref == "Internal Policy AML-07"} == {"eval-1", "eval-2"}


def test_chunk_text_respects_size_and_keeps_all_content():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(8)) + "\n\n" + "x" * 3000
    chunks = chunk_text(text, max_chars=500, overlap=50)
    assert all(len(c) <= 500 for c in chunks)
    assert all(f"Paragraph {i} " in "".join(chunks) for i in range(8))
