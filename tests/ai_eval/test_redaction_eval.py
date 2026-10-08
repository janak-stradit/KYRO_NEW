"""
tests/ai_eval/test_redaction_eval.py — Personal data must never survive redaction.
Threshold: zero leaks, exact restoration, on every golden case.
"""
from __future__ import annotations

from app.ai.redaction import Redactor


def test_redaction_golden_set_has_no_leaks(golden):
    cases = golden("redaction")["cases"]
    leaks, bad_restores = [], []
    for case in cases:
        redactor = Redactor(known=dict(case["known"]))
        redacted = redactor.redact(case["text"])
        leaks += [(case["id"], secret) for secret in case["must_not_leak"] if secret.lower() in redacted.lower()]
        if redactor.restore(redacted) != case["text"]:
            bad_restores.append(case["id"])

    assert not leaks, f"Personal data left in redacted text: {leaks}"
    assert not bad_restores, f"restore() did not return the original text for: {bad_restores}"
