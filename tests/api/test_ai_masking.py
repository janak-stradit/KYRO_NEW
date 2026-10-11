"""
tests/api/test_ai_masking.py — What is replaced before text leaves KYRO for the
model, and that every replacement is restored in the reply.
"""
import pytest

from app.ai.redaction import Redactor, identifying_values


@pytest.mark.parametrize("text, category", [
    ("lives at 22 Fleet Road", "ADDRESS"),
    ("post code SW1A 1AA", "POSTCODE"),
    ("ZIP 10001-1234", "POSTCODE"),
    ("payment reference TXN-2026-00412", "REFERENCE"),
    ("SWIFT ref FT24A9QX81", "REFERENCE"),
    ("record 1bb00fc6-1234-4abc-9def-001122334455", "ID"),
    ("passport: X9876543", "ID"),
    ("account no. 7731842", "ACCOUNT"),
])
def test_identifying_details_are_replaced(text, category):
    redactor = Redactor()
    out = redactor.redact(text)
    assert f"[{category}_1]" in out
    assert redactor.restore(out) == text


def test_labels_stay_and_only_the_value_is_replaced():
    redactor = Redactor()
    assert redactor.redact("account no. 7731842") == "account no. [ACCOUNT_1]"
    assert redactor.redact("passport: X9876543") == "passport: [ID_1]"


def test_case_facts_that_are_not_identifying_pass_through():
    text = "Rule R006 fired; risk score 87; 3 transfers totalling 25,000.00 USD; country IR"
    assert Redactor().redact(text) == text


def test_known_values_come_from_metadata():
    known = identifying_values({
        "address": {"line1": "14 Baker Street", "postcode": "NW1 6XE"},
        "documents": [{"passport_number": "P1234567"}],
        "risk": "HIGH", "is_pep": True,
    })
    assert known == {"14 Baker Street": "ADDRESS", "NW1 6XE": "ADDRESS", "P1234567": "ID"}
    redactor = Redactor(known=known)
    out = redactor.redact("Moved from 14 Baker Street; passport P1234567")
    assert "Baker" not in out and "P1234567" not in out


def test_masking_twice_changes_nothing_more():
    """The gateway masks each variable and then the whole prompt; labels must survive both passes."""
    redactor = Redactor()
    text = "Document type: passport\nFields to extract: id_number\nPassport number: X1234567\nRegistration number: 88213377"
    once = redactor.redact(text)
    assert redactor.redact(once) == once
    assert "Passport number: [ID_" in once and "Fields to extract" in once
    assert redactor.restore(once) == text
