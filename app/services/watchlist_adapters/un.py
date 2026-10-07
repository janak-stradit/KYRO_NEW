"""
services/watchlist_adapters/un.py — parser for the UN Security Council
Consolidated Sanctions List XML feed.
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Iterator
from xml.etree import ElementTree as ET

from app.services.watchlist_adapters.base import WatchlistRecord

_NAME_FIELDS = ("{*}FIRST_NAME", "{*}SECOND_NAME", "{*}THIRD_NAME", "{*}FOURTH_NAME")


def _local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _text(elem: ET.Element, path: str) -> str | None:
    node = elem.find(path)
    return node.text.strip() if node is not None and node.text else None


def _parse_dob(elem: ET.Element, container: str) -> date | None:
    dob_node = elem.find(f"{{*}}{container}")
    if dob_node is None:
        return None
    exact = _text(dob_node, "{*}DATE")
    if exact:
        try:
            return datetime.strptime(exact, "%Y-%m-%d").date()
        except ValueError:
            pass
    year = _text(dob_node, "{*}YEAR")
    if year and year.isdigit():
        return date(int(year), 1, 1)
    return None


def _extract(elem: ET.Element, *, alias_tag: str, address_tag: str, dob_container: str) -> WatchlistRecord | None:
    external_id = _text(elem, "{*}REFERENCE_NUMBER") or _text(elem, "{*}DATAID")
    name = " ".join(t for t in (_text(elem, f) for f in _NAME_FIELDS) if t)
    if not external_id or not name:
        return None

    aka_names = [t.strip() for t in (n.text for n in elem.findall(f"{{*}}{alias_tag}/{{*}}ALIAS_NAME")) if t and t.strip()]
    nationalities = [t.strip() for t in (n.text for n in elem.findall("{*}NATIONALITY/{*}VALUE")) if t and t.strip()]

    addresses = []
    for addr in elem.findall(f"{{*}}{address_tag}"):
        entry = {"city": _text(addr, "{*}CITY"), "country": _text(addr, "{*}COUNTRY")}
        if any(entry.values()):
            addresses.append(entry)

    pob_node = elem.find("{*}INDIVIDUAL_PLACE_OF_BIRTH")
    place_of_birth = None
    if pob_node is not None:
        place_of_birth = " ".join(
            p for p in (_text(pob_node, "{*}CITY"), _text(pob_node, "{*}COUNTRY")) if p
        ) or None

    list_type = _text(elem, "{*}UN_LIST_TYPE")
    reference_number = _text(elem, "{*}REFERENCE_NUMBER")

    return WatchlistRecord(
        external_id=external_id,
        primary_name=name,
        aka_names=aka_names,
        date_of_birth=_parse_dob(elem, dob_container),
        place_of_birth=place_of_birth,
        nationalities=nationalities,
        addresses=addresses,
        programs=[list_type] if list_type else [],
        remarks=_text(elem, "{*}COMMENTS1"),
        raw_data={"reference_number": reference_number, "un_list_type": list_type},
    )


def parse_un_xml(raw_bytes: bytes) -> Iterator[WatchlistRecord]:
    for _, elem in ET.iterparse(io.BytesIO(raw_bytes), events=("end",)):
        tag = _local_name(elem.tag)
        if tag not in ("INDIVIDUAL", "ENTITY"):
            # Skip *before* entering the try/finally below: clearing every
            # descendant as its own end-event fires (DATAID, FIRST_NAME, ...)
            # would wipe their .text before the parent INDIVIDUAL/ENTITY
            # element gets a chance to read it via elem.find(...).
            continue
        try:
            if tag == "INDIVIDUAL":
                record = _extract(
                    elem,
                    alias_tag="INDIVIDUAL_ALIAS",
                    address_tag="INDIVIDUAL_ADDRESS",
                    dob_container="INDIVIDUAL_DATE_OF_BIRTH",
                )
                if record:
                    yield WatchlistRecord(**{**record.__dict__, "entity_type": "INDIVIDUAL"})
            else:
                record = _extract(
                    elem,
                    alias_tag="ENTITY_ALIAS",
                    address_tag="ENTITY_ADDRESS",
                    dob_container="__NONE__",
                )
                if record:
                    yield WatchlistRecord(**{**record.__dict__, "entity_type": "ENTITY"})
        finally:
            elem.clear()
