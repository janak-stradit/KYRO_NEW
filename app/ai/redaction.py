"""
ai/redaction.py — Replaces personal data with placeholders before text leaves
KYRO, and restores it in the model's reply.

Two layers:
  * known values the caller passes in (customer names, customer IDs, ...)
    are replaced exactly, longest first;
  * patterns catch what callers don't know about: emails, phone numbers,
    IBANs, long account/card numbers and dates.

Placeholders look like [PERSON_1] / [EMAIL_2] so the model can still refer
to "the customer" consistently, and restore() maps them back afterwards.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Order matters: more specific patterns run first so e.g. an IBAN isn't
# half-consumed by the generic number pattern.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b")),
    ("DATE", re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b")),
    ("PHONE", re.compile(r"(?<![\w])\+?\d[\d ()-]{7,}\d\b")),
    ("ACCOUNT", re.compile(r"\b\d{8,19}\b")),
]


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

    def redact(self, text: str) -> str:
        if not text:
            return text
        # Known values first, longest first so "John James Smith" beats "John James"
        for value, category in sorted(self.known.items(), key=lambda kv: -len(kv[0])):
            if value and len(value) >= 3:
                pattern = re.compile(re.escape(value), re.IGNORECASE)
                text = pattern.sub(lambda m, c=category: self._placeholder(c, m.group(0)), text)
        for category, pattern in _PATTERNS:
            text = pattern.sub(lambda m, c=category: self._placeholder(c, m.group(0)), text)
        return text

    def restore(self, text: str) -> str:
        if not text:
            return text
        for original, placeholder in self._forward.items():
            text = text.replace(placeholder, original)
        return text
