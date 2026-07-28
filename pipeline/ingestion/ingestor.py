"""
ingestion/ingestor.py — Multi-format data ingestion layer.
Supports: CSV, Excel, JSON, dict/list, API responses.
Handles: malformed records, encoding issues, schema evolution, batch chunking.
"""
from __future__ import annotations

import io
import json
import logging
import math
from pathlib import Path
from typing import Any, Generator, Iterator

import pandas as pd

from pipeline.core.exceptions import IngestionError, EncodingError, SchemaEvolutionError

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {"csv", "excel", "xlsx", "xls", "json", "dict", "list", "api"}
ENCODINGS_TO_TRY = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]


def _detect_encoding(path: str) -> str:
    """Try encodings in order; return the first that succeeds."""
    for enc in ENCODINGS_TO_TRY:
        try:
            with open(path, "r", encoding=enc) as f:
                f.read(4096)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    raise EncodingError(f"Cannot determine encoding for: {path}")


def _reconcile_schema(
    df: pd.DataFrame,
    expected_cols: list[str],
    on_mismatch: str = "warn",
) -> pd.DataFrame:
    """
    Align DataFrame columns to expected schema.

    Args:
        on_mismatch: 'warn'=log missing cols, 'error'=raise, 'drop_extra'=remove extras,
                     'add_missing'=add NaN cols for missing.
    """
    actual = set(df.columns)
    expected = set(expected_cols)
    missing = expected - actual
    extra = actual - expected

    if missing:
        msg = f"Missing columns: {missing}"
        if on_mismatch == "error":
            raise SchemaEvolutionError(msg)
        elif on_mismatch in ("warn", "drop_extra"):
            logger.warning("Schema evolution — %s", msg)
            for col in missing:
                df[col] = None
        elif on_mismatch == "add_missing":
            for col in missing:
                df[col] = None

    if extra and on_mismatch == "drop_extra":
        logger.info("Dropping extra columns: %s", extra)
        df = df.drop(columns=list(extra))

    return df


def read_csv(
    path: str,
    expected_cols: list[str] | None = None,
    on_mismatch: str = "warn",
    **kwargs,
) -> pd.DataFrame:
    """Read a CSV file with auto-encoding detection."""
    encoding = _detect_encoding(path)
    try:
        df = pd.read_csv(path, encoding=encoding, **kwargs)
    except Exception as exc:
        raise IngestionError(f"CSV read failed [{path}]: {exc}") from exc
    if expected_cols:
        df = _reconcile_schema(df, expected_cols, on_mismatch)
    logger.info("CSV ingested: %s — %d rows, %d cols", Path(path).name, len(df), len(df.columns))
    return df


def read_excel(
    path: str,
    sheet_name: str | int = 0,
    expected_cols: list[str] | None = None,
    on_mismatch: str = "warn",
    **kwargs,
) -> pd.DataFrame:
    """Read an Excel sheet into a DataFrame."""
    try:
        df = pd.read_excel(path, sheet_name=sheet_name, **kwargs)
    except Exception as exc:
        raise IngestionError(f"Excel read failed [{path}, sheet={sheet_name}]: {exc}") from exc
    if expected_cols:
        df = _reconcile_schema(df, expected_cols, on_mismatch)
    logger.info("Excel ingested: %s[%s] — %d rows", Path(path).name, sheet_name, len(df))
    return df


def read_json(
    path_or_str: str,
    expected_cols: list[str] | None = None,
    on_mismatch: str = "warn",
    **kwargs,
) -> pd.DataFrame:
    """Read JSON file or JSON string into a DataFrame."""
    try:
        path = Path(path_or_str)
        if path.exists():
            df = pd.read_json(path, **kwargs)
        else:
            df = pd.read_json(io.StringIO(path_or_str), **kwargs)
    except Exception as exc:
        raise IngestionError(f"JSON read failed: {exc}") from exc
    if expected_cols:
        df = _reconcile_schema(df, expected_cols, on_mismatch)
    logger.info("JSON ingested: %d rows", len(df))
    return df


def from_dict_list(
    records: list[dict],
    expected_cols: list[str] | None = None,
    on_mismatch: str = "warn",
) -> pd.DataFrame:
    """Convert a list of dicts (from Python generator or API response) to DataFrame."""
    if not records:
        logger.warning("from_dict_list: received empty list")
        return pd.DataFrame(columns=expected_cols or [])
    try:
        df = pd.DataFrame(records)
    except Exception as exc:
        raise IngestionError(f"Dict-list conversion failed: {exc}") from exc
    if expected_cols:
        df = _reconcile_schema(df, expected_cols, on_mismatch)
    logger.info("Dict ingested: %d rows, %d cols", len(df), len(df.columns))
    return df


def from_api_response(
    response_data: Any,
    data_key: str | None = None,
    expected_cols: list[str] | None = None,
    on_mismatch: str = "warn",
) -> pd.DataFrame:
    """Normalise an API JSON response (nested or flat) to a DataFrame."""
    if isinstance(response_data, (str, bytes)):
        response_data = json.loads(response_data)
    if data_key and isinstance(response_data, dict):
        response_data = response_data.get(data_key, response_data)
    if isinstance(response_data, dict):
        response_data = [response_data]
    return from_dict_list(response_data, expected_cols, on_mismatch)


def chunked_reader(
    df: pd.DataFrame,
    batch_size: int = 5000,
) -> Generator[pd.DataFrame, None, None]:
    """Yield DataFrame in fixed-size chunks for memory-efficient batch processing."""
    total = len(df)
    num_batches = math.ceil(total / batch_size)
    logger.info("Chunking %d rows into %d batches of %d", total, num_batches, batch_size)
    for i in range(num_batches):
        chunk = df.iloc[i * batch_size : (i + 1) * batch_size].copy()
        logger.debug("Yielding batch %d/%d (%d rows)", i + 1, num_batches, len(chunk))
        yield chunk


def ingest(
    source: Any,
    source_format: str,
    sheet_name: str | int = 0,
    data_key: str | None = None,
    expected_cols: list[str] | None = None,
    on_mismatch: str = "warn",
    batch_size: int | None = None,
    **kwargs,
) -> pd.DataFrame | Generator[pd.DataFrame, None, None]:
    """
    Unified ingestion entry point.

    Args:
        source: File path, JSON string, list[dict], or API response dict.
        source_format: One of 'csv','excel','json','dict','list','api'.
        batch_size: If provided, returns a generator of chunks instead of full DataFrame.

    Returns:
        DataFrame or generator of DataFrames.
    """
    fmt = source_format.lower().strip(".")
    if fmt not in SUPPORTED_FORMATS:
        raise IngestionError(f"Unsupported format '{fmt}'. Supported: {SUPPORTED_FORMATS}")

    if fmt == "csv":
        df = read_csv(source, expected_cols, on_mismatch, **kwargs)
    elif fmt in ("excel", "xlsx", "xls"):
        df = read_excel(source, sheet_name, expected_cols, on_mismatch, **kwargs)
    elif fmt == "json":
        df = read_json(source, expected_cols, on_mismatch, **kwargs)
    elif fmt in ("dict", "list"):
        df = from_dict_list(source, expected_cols, on_mismatch)
    elif fmt == "api":
        df = from_api_response(source, data_key, expected_cols, on_mismatch)
    else:
        raise IngestionError(f"Unhandled format: {fmt}")

    if batch_size:
        return chunked_reader(df, batch_size)
    return df
