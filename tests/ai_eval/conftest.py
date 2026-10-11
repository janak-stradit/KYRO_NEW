"""
tests/ai_eval/conftest.py — Evaluation harness for the Compliance AI (Phase 11.0.6).

Golden datasets live in golden/*.json. Each eval scores a component against
its dataset and fails if the score drops below the threshold in the test, so
a prompt, model or retrieval change that makes things worse is caught before
it ships. No eval calls a real AI provider.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Reuse the API suite's live-database fixtures (SAVEPOINT per test)
from api.conftest import _require_live_db, db_session  # noqa: F401

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture(scope="session")
def golden():
    def load(name: str) -> dict:
        return json.loads((GOLDEN_DIR / f"{name}.json").read_text(encoding="utf-8"))

    return load
