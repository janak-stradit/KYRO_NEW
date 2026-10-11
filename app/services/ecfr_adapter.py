"""
services/ecfr_adapter.py — Reads regulation text from the eCFR Versioner API
(https://www.ecfr.gov/developers/documentation/api/v1). Free, no key; the text
is a US Government work in the public domain.

    fetch(config) -> (as_of_date, [SectionRecord, ...])

`config` is a RegulatorySource.config, e.g. {"title": 31, "part": "1023"},
optionally narrowed with "section": "240.17a-8".
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from app.config import get_settings

BASE_URL = "https://www.ecfr.gov/api/versioner/v1"


@dataclass
class SectionRecord:
    section_ref: str  # "31 CFR 1023.320"
    heading: str
    content: str
    version: str  # date this section was last amended (falls back to the as-of date)
    url: str
    source_note: str | None = None


def _get(client: httpx.Client, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
    # The API rejects uncompressed requests; httpx sends Accept-Encoding by default
    response = client.get(f"{BASE_URL}{path}", params=params)
    response.raise_for_status()
    return response


def _text(element: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def parse_sections(xml_bytes: bytes, *, title: int, as_of: str, amended: dict[str, str] | None = None) -> list[SectionRecord]:
    """Extract every section (<DIV8 TYPE="SECTION">) from an eCFR XML document."""
    amended = amended or {}
    root = ET.fromstring(xml_bytes)
    records: list[SectionRecord] = []
    for div in root.iter("DIV8"):
        number = div.get("N")
        if div.get("TYPE") != "SECTION" or not number:
            continue

        head = div.find("HEAD")
        heading = _text(head) if head is not None else ""
        heading = re.sub(rf"^§\s*{re.escape(number)}\s*", "", heading).strip()

        paragraphs, notes = [], []
        for child in div:
            if child.tag == "HEAD":
                continue
            text = _text(child)
            if text:
                (notes if child.tag == "CITA" else paragraphs).append(text)
        if not paragraphs:
            continue  # reserved sections have a heading only

        try:
            citation = json.loads(div.get("hierarchy_metadata") or "{}").get("citation")
        except ValueError:
            citation = None

        records.append(
            SectionRecord(
                section_ref=citation or f"{title} CFR {number}",
                heading=heading,
                content="\n\n".join(paragraphs),
                version=amended.get(number, as_of),
                url=f"https://www.ecfr.gov/current/title-{title}/section-{number}",
                source_note=" ".join(notes) or None,
            )
        )
    return records


def fetch(config: dict[str, Any]) -> tuple[str, list[SectionRecord]]:
    title = int(config["title"])
    scope = {k: config[k] for k in ("part", "section") if config.get(k)}
    timeout = get_settings().watchlist_http_timeout_seconds

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        titles = _get(client, "/titles.json").json()["titles"]
        as_of = next(t["up_to_date_as_of"] for t in titles if t["number"] == title)

        # Latest amendment date per section, so citations carry the real version date
        versions = _get(client, f"/versions/title-{title}.json", scope).json().get("content_versions", [])
        amended: dict[str, str] = {}
        for v in versions:
            if v.get("type") == "section" and not v.get("removed") and v["date"] <= as_of:
                amended[v["identifier"]] = max(v["date"], amended.get(v["identifier"], ""))

        xml_bytes = _get(client, f"/full/{as_of}/title-{title}.xml", scope).content

    return as_of, parse_sections(xml_bytes, title=title, as_of=as_of, amended=amended)
