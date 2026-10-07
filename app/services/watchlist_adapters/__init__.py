"""
services/watchlist_adapters — one parser per source list format.

Each adapter turns a raw downloaded payload (XML/CSV bytes) into an iterator
of WatchlistRecord, the common shape the ingestion service upserts into
WatchlistEntity rows.
"""
from __future__ import annotations

from app.services.watchlist_adapters.base import WatchlistRecord
from app.services.watchlist_adapters.ofac import parse_ofac_xml
from app.services.watchlist_adapters.uk_ofsi import parse_uk_ofsi_csv
from app.services.watchlist_adapters.un import parse_un_xml

ADAPTERS = {
    "OFAC_SDN": parse_ofac_xml,
    "OFAC_CONSOLIDATED": parse_ofac_xml,
    "UN_CONSOLIDATED": parse_un_xml,
    "UK_OFSI": parse_uk_ofsi_csv,
}

__all__ = ["WatchlistRecord", "ADAPTERS", "parse_ofac_xml", "parse_un_xml", "parse_uk_ofsi_csv"]
