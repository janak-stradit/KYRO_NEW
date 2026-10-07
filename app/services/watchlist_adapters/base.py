"""
services/watchlist_adapters/base.py — common record shape every adapter
parses its source format into.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


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
    raw_data: dict | None = None
