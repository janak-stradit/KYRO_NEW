"""
services/watchlist_adapters/uk_ofsi.py — parser for the UK OFSI Consolidated
List of Financial Sanctions Targets CSV export.

OFSI has changed this export's column names before, and a "Group ID" can
span multiple rows (one primary-name row plus one row per alias). Column
matching is therefore done defensively against normalized header aliases,
and rows sharing a Group ID are merged into a single record with every
other name variant folded into aka_names. The full raw row is always kept
in raw_data so a header we don't recognize isn't silently dropped.
"""
from __future__ import annotations

import csv
import io
from collections import OrderedDict
from datetime import date, datetime
from typing import Iterator

from app.services.watchlist_adapters.base import WatchlistRecord, identifier

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "group_id": ("groupid", "groupidnumber", "id"),
    "group_type": ("grouptype",),
    "name1": ("name1", "title"),
    "name2": ("name2", "firstname"),
    "name3": ("name3", "middlename"),
    "name4": ("name4",),
    "name5": ("name5",),
    "name6": ("name6", "lastname", "surname"),
    "dob": ("dob", "dateofbirth"),
    "town_of_birth": ("townofbirth", "placeofbirth"),
    "country_of_birth": ("countryofbirth",),
    "nationality": ("nationality",),
    "address": ("address", "fulladdress", "address1"),
    "town": ("town", "city"),
    "country": ("country",),
    "regime": ("regime",),
    "programme": ("programme", "program"),
    "other_information": ("otherinformation", "comments", "remarks"),
    "passport": ("passportnumber", "passportno", "passportdetails", "passport"),
    "national_id": ("nationalidentificationnumber", "nationalidentitynumber", "nationalidnumber", "nationalidentificationdetails", "ninumber"),
    "company_number": ("companynumber", "businessregistrationnumber", "registrationnumber", "companyregistrationnumber"),
    "imo": ("imonumber", "imo", "currentbelievedflagofshipimonumber"),
}

_IDENTIFIER_FIELDS = (("passport", "Passport"), ("national_id", "National ID"), ("company_number", "Registration"), ("imo", "IMO"))


def row_identifiers(rows: list[dict], header_map: dict[str, str]) -> list[dict]:
    """Passport, national ID, company and IMO numbers from every row of one group, without repeats."""
    found: dict[tuple[str, str], dict] = {}
    for row in rows:
        for field, label in _IDENTIFIER_FIELDS:
            entry = identifier(label, _get(row, header_map, field))
            if entry:
                found.setdefault((entry["type"], entry["normalized"]), entry)
    return list(found.values())


def _normalize_header(header: str) -> str:
    return "".join(ch for ch in header.lower() if ch.isalnum())


def _build_header_map(fieldnames: list[str]) -> dict[str, str]:
    normalized = {_normalize_header(h): h for h in fieldnames}
    resolved: dict[str, str] = {}
    for field, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                resolved[field] = normalized[alias]
                break
    return resolved


def _get(row: dict, header_map: dict[str, str], field: str) -> str | None:
    header = header_map.get(field)
    if not header:
        return None
    value = row.get(header)
    return value.strip() if value and value.strip() else None


def _row_name(row: dict, header_map: dict[str, str]) -> str:
    parts = [_get(row, header_map, f"name{i}") for i in range(1, 7)]
    return " ".join(p for p in parts if p).strip()


def _parse_dob(raw: str | None) -> date | None:
    if not raw:
        return None
    for fmt, has_day in (("%d/%m/%Y", True), ("%Y-%m-%d", True), ("%d %b %Y", True), ("%Y", False)):
        try:
            parsed = datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
        return parsed.date() if has_day else date(parsed.year, 1, 1)
    return None


def parse_uk_ofsi_csv(raw_bytes: bytes) -> Iterator[WatchlistRecord]:
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return
    header_map = _build_header_map(reader.fieldnames)

    groups: OrderedDict[str, list[dict]] = OrderedDict()
    for row in reader:
        group_id = _get(row, header_map, "group_id")
        if not group_id:
            continue
        groups.setdefault(group_id, []).append(row)

    for group_id, rows in groups.items():
        primary_row = rows[0]
        primary_name = _row_name(primary_row, header_map)
        if not primary_name:
            continue

        aka_names = []
        for row in rows[1:]:
            variant = _row_name(row, header_map)
            if variant and variant != primary_name and variant not in aka_names:
                aka_names.append(variant)

        group_type = (_get(primary_row, header_map, "group_type") or "").lower()
        entity_type = "ENTITY" if "entity" in group_type else "INDIVIDUAL"

        addresses = []
        addr = {
            "address": _get(primary_row, header_map, "address"),
            "city": _get(primary_row, header_map, "town"),
            "country": _get(primary_row, header_map, "country"),
        }
        if any(addr.values()):
            addresses.append(addr)

        nationality = _get(primary_row, header_map, "nationality")
        regime = _get(primary_row, header_map, "regime")
        programme = _get(primary_row, header_map, "programme")

        yield WatchlistRecord(
            external_id=group_id,
            primary_name=primary_name,
            entity_type=entity_type,
            aka_names=aka_names,
            date_of_birth=_parse_dob(_get(primary_row, header_map, "dob")),
            place_of_birth=_get(primary_row, header_map, "town_of_birth")
            or _get(primary_row, header_map, "country_of_birth"),
            nationalities=[nationality] if nationality else [],
            addresses=addresses,
            programs=[p for p in (regime, programme) if p],
            remarks=_get(primary_row, header_map, "other_information"),
            identifiers=row_identifiers(rows, header_map),
            raw_data={"rows": rows},
        )
