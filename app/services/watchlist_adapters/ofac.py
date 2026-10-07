"""
services/watchlist_adapters/ofac.py — parser for the OFAC SDN and Consolidated
Non-SDN XML feeds (same schema, different content). Streams via iterparse so
a ~17k-entry SDN list doesn't need to be held fully in memory as a DOM tree.
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Iterator
from xml.etree import ElementTree as ET

from app.services.watchlist_adapters.base import WatchlistRecord

_ENTITY_TYPE_MAP = {
    "individual": "INDIVIDUAL",
    "vessel": "VESSEL",
    "aircraft": "OTHER",
    "entity": "ENTITY",
}

_DOB_FORMATS = ("%d %b %Y", "%b %Y", "%Y")


def _local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _text(elem: ET.Element, path: str) -> str | None:
    node = elem.find(path)
    return node.text.strip() if node is not None and node.text else None


def _parse_dob(raw: str | None) -> date | None:
    if not raw:
        return None
    candidate = raw.split(" to ")[0].replace("circa ", "").replace("est. ", "").strip()
    for fmt in _DOB_FORMATS:
        try:
            parsed = datetime.strptime(candidate, fmt)
        except ValueError:
            continue
        if fmt == "%b %Y":
            return date(parsed.year, parsed.month, 1)
        if fmt == "%Y":
            return date(parsed.year, 1, 1)
        return parsed.date()
    return None


def _combine_name(first: str | None, last: str | None) -> str | None:
    if first and last:
        return f"{first} {last}"
    return first or last


def parse_ofac_xml(raw_bytes: bytes) -> Iterator[WatchlistRecord]:
    for _, elem in ET.iterparse(io.BytesIO(raw_bytes), events=("end",)):
        if _local_name(elem.tag) != "sdnEntry":
            continue

        try:
            uid = _text(elem, "{*}uid")
            first_name = _text(elem, "{*}firstName")
            last_name = _text(elem, "{*}lastName")
            primary_name = _combine_name(first_name, last_name)
            if not uid or not primary_name:
                continue

            sdn_type = (_text(elem, "{*}sdnType") or "").lower()
            entity_type = _ENTITY_TYPE_MAP.get(sdn_type, "ENTITY")

            aka_names = []
            for aka in elem.findall("{*}akaList/{*}aka"):
                aka_name = _combine_name(_text(aka, "{*}firstName"), _text(aka, "{*}lastName"))
                if aka_name:
                    aka_names.append(aka_name)

            addresses = []
            for addr in elem.findall("{*}addressList/{*}address"):
                entry = {
                    "address": _text(addr, "{*}address1"),
                    "city": _text(addr, "{*}city"),
                    "country": _text(addr, "{*}country"),
                }
                if any(entry.values()):
                    addresses.append(entry)

            programs = [p.text.strip() for p in elem.findall("{*}programList/{*}program") if p.text]
            nationalities = [
                n.text.strip() for n in elem.findall("{*}nationalityList/{*}nationality/{*}country") if n.text
            ]

            dob_raw = _text(elem, "{*}dateOfBirthList/{*}dateOfBirthItem/{*}dateOfBirth")
            place_of_birth = _text(elem, "{*}placeOfBirthList/{*}placeOfBirthItem/{*}placeOfBirth")
            remarks = _text(elem, "{*}remarks")

            yield WatchlistRecord(
                external_id=uid,
                primary_name=primary_name,
                entity_type=entity_type,
                aka_names=aka_names,
                date_of_birth=_parse_dob(dob_raw),
                place_of_birth=place_of_birth,
                nationalities=nationalities,
                addresses=addresses,
                programs=programs,
                remarks=remarks,
                raw_data={"uid": uid, "sdn_type": sdn_type, "dob_raw": dob_raw},
            )
        finally:
            elem.clear()
