"""
services/watchlist_adapters/base.py — common record shape every adapter
parses its source format into.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

# Identifier types KYRO compares; anything else is kept as OTHER
IDENTIFIER_TYPES = ("PASSPORT", "NATIONAL_ID", "TAX_ID", "REGISTRATION", "IMO", "OTHER")
# First match wins; short codes match only as whole words
_TYPE_WORDS = (
    ("IMO", r"\bimo\b"),
    ("PASSPORT", r"passport"),
    ("OTHER", r"driv(er|ing)"),
    ("TAX_ID", r"tax|\btin\b|\bvat\b|\bssn\b|social security"),
    ("REGISTRATION", r"registration|company|business|commercial|incorporation|licen[cs]e|swift|\bbic\b"),
    ("NATIONAL_ID", r"national|identity|identification|\bid no|\bid card|cedula|\bdni\b|\bnin\b|personal id"),
)


def identifier_type(label: str | None) -> str:
    """The KYRO identifier type for a list's own label, e.g. "Passport", "National ID No.", "Registration Number"."""
    text = (label or "").lower()
    for kind, pattern in _TYPE_WORDS:
        if re.search(pattern, text):
            return kind
    return "OTHER"


def normalize_identifier(value: str | None) -> str:
    """Upper case, letters and digits only, so "AB 123-456" and "ab123456" compare equal."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def identifier(label: str | None, value: str | None, country: str | None = None) -> dict | None:
    normalized = normalize_identifier(value)
    if len(normalized) < 4:
        return None
    return {"type": identifier_type(label), "value": value.strip(), "normalized": normalized, "country": country or None}


@dataclass
class WatchlistRecord:
    external_id: str
    primary_name: str
    entity_type: str = "INDIVIDUAL"  # INDIVIDUAL | ENTITY | VESSEL | OTHER
    aka_names: list[str] = field(default_factory=list)
    date_of_birth: date | None = None
    place_of_birth: str | None = None
    nationalities: list[str] = field(default_factory=list)
    addresses: list[dict] = field(default_factory=list)
    programs: list[str] = field(default_factory=list)
    remarks: str | None = None
    identifiers: list[dict] = field(default_factory=list)  # {type, value, normalized, country}; see identifier()
    raw_data: dict | None = None
