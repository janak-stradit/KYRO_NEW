"""
ai/redaction.py — Replaces personal data with placeholders before text leaves
KYRO, and restores it in the model's reply.

Two layers:
  * known values the caller passes in (customer names, customer IDs, ...)
    are replaced exactly, longest first;
  * patterns catch what callers don't know about: emails, phone numbers,
    IBANs, long account/card numbers, dates, record IDs, street addresses,
    postcodes, payment references and labelled account or ID numbers.

identifying_values() collects the known values from a record's JSON metadata
(addresses, ID and account numbers, references) for the first layer.

Placeholders look like [PERSON_1] / [EMAIL_2] so the model can still refer
to "the customer" consistently, and restore() maps them back afterwards.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Order matters: more specific patterns run first so e.g. an IBAN isn't
# half-consumed by the generic number pattern.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ID", re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")),
    # "account no. 1234567", "passport: X1234567": the label says what the value is. A value has a digit, so a
    # word after the label ("Passport number", "passport\nFields") is never taken for one, even on a second pass
    ("ACCOUNT", re.compile(r"(?i)\b(?:account|acct|a/c)(?:\s+(?:number|no\.?)|\s*#)?[:\s]\s*((?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,})\b")),
    ("ID", re.compile(r"(?i)\b(?:passport|national id|id number|ssn|tax id|tin|nino|registration|company no\.?)(?:\s+(?:number|no\.?))?[:\s#]\s*((?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{4,})\b")),
    ("ADDRESS", re.compile(
        r"(?i)\b\d{1,5}[A-Z]?(?:\s+[A-Z][A-Za-z.'-]*){1,4}\s+"
        r"(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd|way|court|ct|place|pl|square|sq|close|terrace|highway|hwy)\b\.?"
    )),
    ("POSTCODE", re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}\b")),  # UK
    ("POSTCODE", re.compile(r"\b\d{5}-\d{4}\b")),  # US ZIP+4
    # Payment and transaction references: at least six characters mixing two or more letters and digits, e.g. TXN-2026-00412
    ("REFERENCE", re.compile(r"\b(?=(?:[A-Z0-9-]*\d){2})(?=(?:[A-Z0-9-]*[A-Z]){2})[A-Z0-9]+(?:-[A-Z0-9]+)*\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b")),
    ("DATE", re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b")),
    ("PHONE", re.compile(r"(?<![\w])\+?\d[\d ()-]{7,}\d\b")),
    ("ACCOUNT", re.compile(r"\b\d{8,19}\b")),
]


_IDENTIFYING_KEY = re.compile(
    r"(?i)(address|street|line_?[12]|post_?code|zip|passport|national_?id|id_?number|tax|ssn|tin|nino|registration|"
    r"account_?(?:number|no)|iban|swift|bic|sort_?code|routing|reference|\bref\b|phone|mobile|email)"
)
_ADDRESS_KEY = re.compile(r"(?i)address|street|line_?[12]|post_?code|zip")


def identifying_values(metadata: Any) -> dict[str, str]:
    """Values under identifying keys anywhere in a JSON metadata object, as {value: category} for Redactor.known."""
    found: dict[str, str] = {}

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{key} {k}")
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif node is not None and not isinstance(node, bool) and _IDENTIFYING_KEY.search(key):
            value = str(node).strip()
            if len(value) >= 4:
                found[value] = "ADDRESS" if _ADDRESS_KEY.search(key) else "ID"

    walk(metadata)
    return found


@dataclass
class Redactor:
    """Holds the placeholder mapping for one request so replies can be restored."""

    known: dict[str, str] = field(default_factory=dict)  # value -> category, e.g. {"John James": "PERSON"}
    _forward: dict[str, str] = field(default_factory=dict, init=False)  # original -> placeholder
    _counters: dict[str, int] = field(default_factory=dict, init=False)

    @property
    def count(self) -> int:
        return len(self._forward)

    def _placeholder(self, category: str, original: str) -> str:
        if original not in self._forward:
            n = self._counters.get(category, 0) + 1
            self._counters[category] = n
            self._forward[original] = f"[{category}_{n}]"
        return self._forward[original]

    def _replace(self, category: str, match: re.Match[str]) -> str:
        """Replace the whole match, or only its value when the pattern keeps a label ("account no. ") in front."""
        if match.re.groups and match.group(1):
            start = match.start(1) - match.start(0)
            return match.group(0)[:start] + self._placeholder(category, match.group(1))
        return self._placeholder(category, match.group(0))

    def redact(self, text: str) -> str:
        if not text:
            return text
        # Known values first, longest first so "John James Smith" beats "John James"
        for value, category in sorted(self.known.items(), key=lambda kv: -len(kv[0])):
            if value and len(value) >= 3:
                pattern = re.compile(re.escape(value), re.IGNORECASE)
                text = pattern.sub(lambda m, c=category: self._placeholder(c, m.group(0)), text)
        for category, pattern in _PATTERNS:
            text = pattern.sub(lambda m, c=category: self._replace(c, m), text)
        return text

    def restore(self, text: str) -> str:
        if not text:
            return text
        for original, placeholder in self._forward.items():
            text = text.replace(placeholder, original)
        return text
