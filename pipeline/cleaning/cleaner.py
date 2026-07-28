"""
cleaning/cleaner.py — Comprehensive data cleaning layer.
Handles: whitespace, unicode, HTML, illegal chars, case normalization,
         empty→NULL, negative values, impossible dates, encoding artefacts.
Also implements configurable missing-value strategies and duplicate resolution.
"""
from __future__ import annotations

import html
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.experimental import enable_iterative_imputer  # noqa
from sklearn.impute import KNNImputer, IterativeImputer

from pipeline.core.exceptions import CleaningError

logger = logging.getLogger(__name__)

_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_ILLEGAL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML_TAG_RE = re.compile(r"<[^>]+>")

HIGH_RISK_COUNTRIES = {"KP", "IR", "SY", "CU", "VE", "MM", "BY", "RU", "SO", "YE"}
VALID_CURRENCIES = {"USD", "EUR", "GBP", "CHF", "AUD", "CAD", "JPY", "INR", "SGD"}


# ── String Cleaning ───────────────────────────────────────────

def clean_string(value: Any, case: str = "strip") -> str | None:
    """
    Normalise a string value:
    - strip HTML tags
    - decode HTML entities
    - normalise unicode (NFC)
    - remove illegal control characters
    - collapse duplicate spaces
    - strip leading/trailing whitespace
    - apply case normalisation

    Args:
        case: 'strip' | 'upper' | 'lower' | 'title'
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value)
    s = _HTML_TAG_RE.sub("", s)                      # strip HTML
    s = html.unescape(s)                              # &amp; → &
    s = unicodedata.normalize("NFC", s)               # unicode normalise
    s = _ILLEGAL_CHARS_RE.sub("", s)                  # remove control chars
    s = _MULTI_SPACE_RE.sub(" ", s)                   # collapse spaces
    s = s.strip()
    if not s:
        return None
    if case == "upper":
        s = s.upper()
    elif case == "lower":
        s = s.lower()
    elif case == "title":
        s = s.title()
    return s


def clean_string_series(series: pd.Series, case: str = "strip") -> pd.Series:
    return series.map(lambda v: clean_string(v, case))


# ── Currency / Numeric Cleaning ───────────────────────────────

def clean_currency_series(series: pd.Series) -> pd.Series:
    """Convert string currency values to float; coerce invalid to NaN."""
    def _parse(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return np.nan
        s = re.sub(r"[^\d.\-]", "", str(v))
        try:
            return float(s)
        except ValueError:
            return np.nan
    return series.map(_parse)


def clip_negative_amounts(series: pd.Series, fill: float = 0.0) -> pd.Series:
    """Replace negative numeric values with fill (default 0)."""
    return series.clip(lower=fill)


# ── Date Cleaning ─────────────────────────────────────────────

_DATE_FORMATS = [
    "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
    "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d",
]
_MIN_DATE = pd.Timestamp("1900-01-01")
_MAX_DATE = pd.Timestamp("2100-12-31")


def parse_date_series(series: pd.Series, default: pd.Timestamp | None = None) -> pd.Series:
    """Parse mixed-format date strings to Timestamps; invalid → default."""
    def _parse(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return default
        for fmt in _DATE_FORMATS:
            try:
                return pd.Timestamp(datetime.strptime(str(v).strip(), fmt))
            except ValueError:
                pass
        try:
            ts = pd.Timestamp(str(v))
            if _MIN_DATE <= ts <= _MAX_DATE:
                return ts
        except Exception:
            pass
        logger.debug("Unparseable date: %s", v)
        return default
    return series.map(_parse)


def reject_impossible_dates(df: pd.DataFrame, col: str, min_year: int = 1900, max_year: int = 2100) -> pd.DataFrame:
    """Flag rows with dates outside acceptable year range."""
    if col not in df.columns:
        return df
    mask = df[col].notna() & (
        (df[col].dt.year < min_year) | (df[col].dt.year > max_year)
    )
    if mask.any():
        logger.warning("Removing %d rows with impossible dates in column '%s'", mask.sum(), col)
        df.loc[mask, col] = pd.NaT
    return df


# ── Missing Value Imputation ───────────────────────────────────

def impute_missing(
    df: pd.DataFrame,
    strategies: dict[str, dict],
) -> pd.DataFrame:
    """
    Apply per-column missing value strategies.

    Strategy dict format (from config)::
        {
          "column_name": {"strategy": "median"},
          "other_col":   {"strategy": "constant", "fill_value": "UNKNOWN"},
          "num_col":     {"strategy": "knn", "n_neighbors": 5},
        }

    Strategies:
        categorical: mode, constant, unknown, ffill, bfill
        numerical:   mean, median, zero, constant, knn, iterative
        datetime:    ffill, bfill, constant (timestamp string)
    """
    df = df.copy()
    knn_cols, iter_cols = [], []

    for col, cfg in strategies.items():
        if col not in df.columns:
            continue
        strat = cfg.get("strategy", "mode")
        fill = cfg.get("fill_value")
        missing_count = df[col].isna().sum()
        if missing_count == 0:
            continue

        logger.debug("Imputing '%s' (%d nulls) with strategy='%s'", col, missing_count, strat)

        if strat == "mean":
            df[col] = df[col].fillna(df[col].mean())
        elif strat == "median":
            df[col] = df[col].fillna(df[col].median())
        elif strat == "zero":
            df[col] = df[col].fillna(0)
        elif strat == "constant":
            df[col] = df[col].fillna(fill if fill is not None else 0)
        elif strat in ("mode", "most_frequent"):
            mode_val = df[col].mode()
            df[col] = df[col].fillna(mode_val.iloc[0] if not mode_val.empty else (fill or "UNKNOWN"))
        elif strat in ("unknown", "UNKNOWN"):
            df[col] = df[col].fillna("UNKNOWN")
        elif strat == "ffill":
            df[col] = df[col].ffill()
        elif strat == "bfill":
            df[col] = df[col].bfill()
        elif strat == "knn":
            knn_cols.append((col, cfg.get("n_neighbors", 5)))
        elif strat == "iterative":
            iter_cols.append(col)

    # KNN imputation (requires numeric context)
    if knn_cols:
        for col, k in knn_cols:
            try:
                imputer = KNNImputer(n_neighbors=k)
                df[[col]] = imputer.fit_transform(df[[col]])
                logger.info("KNN imputed: %s (k=%d)", col, k)
            except Exception as exc:
                logger.warning("KNN impute failed for '%s': %s", col, exc)

    if iter_cols:
        try:
            imputer = IterativeImputer(max_iter=10, random_state=42)
            df[iter_cols] = imputer.fit_transform(df[iter_cols])
            logger.info("Iterative imputed: %s", iter_cols)
        except Exception as exc:
            logger.warning("Iterative impute failed: %s", exc)

    return df


# ── Duplicate Handling ────────────────────────────────────────

def handle_duplicates(
    df: pd.DataFrame,
    business_keys: list[str],
    strategy: str = "keep_first",
    hash_check: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Detect and resolve duplicates at multiple levels.

    Returns:
        (clean_df, duplicates_df)
    """
    if not business_keys:
        return df, pd.DataFrame()

    available_keys = [k for k in business_keys if k in df.columns]
    if not available_keys:
        logger.warning("Business keys not found in df: %s", business_keys)
        return df, pd.DataFrame()

    all_dupes = []

    # 1. Exact row hash duplicates
    if hash_check:
        df = df.copy()
        df["_row_hash"] = pd.util.hash_pandas_object(df, index=False)
        exact_dupes = df.duplicated(subset=["_row_hash"], keep="first")
        if exact_dupes.any():
            logger.info("Removing %d exact-row duplicates (hash check)", exact_dupes.sum())
            all_dupes.append(df[exact_dupes].drop(columns=["_row_hash"]))
        df = df[~exact_dupes].drop(columns=["_row_hash"])

    # 2. Business key duplicates
    keep = "first" if strategy == "keep_first" else ("last" if strategy == "keep_last" else False)
    dupes_mask = df.duplicated(subset=available_keys, keep=keep)
    duplicates_df = df[dupes_mask].copy()
    clean_df = df[~dupes_mask].copy()

    if not duplicates_df.empty:
        all_dupes.append(duplicates_df)

    final_dupes = pd.concat(all_dupes, ignore_index=True) if all_dupes else pd.DataFrame(columns=df.columns)

    if len(final_dupes) > 0:
        logger.warning(
            "Removed %d duplicate records (keys=%s, strategy=%s)",
            len(final_dupes), available_keys, strategy,
        )
    return clean_df, final_dupes


# ── Master Cleaning Pipeline ──────────────────────────────────

def clean_customers(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Apply all cleaning steps to customer DataFrame."""
    df = df.copy()
    # String normalisation
    for col in ("full_name", "meta_source"):
        if col in df.columns:
            df[col] = clean_string_series(df[col], case="title")
    for col in ("email",):
        if col in df.columns:
            df[col] = clean_string_series(df[col], case="lower")
    for col in ("country", "residency_country", "kyc_status", "risk_level", "customer_type"):
        if col in df.columns:
            df[col] = clean_string_series(df[col], case="upper")
    # Date parsing
    for col in ("date_of_birth", "kyc_last_review"):
        if col in df.columns:
            df[col] = parse_date_series(df[col])
    # Boolean coercion
    for col in ("pep_flag", "sanctions_flag", "adverse_media_flag"):
        if col in df.columns:
            df[col] = df[col].map(lambda v: bool(v) if v is not None else None)
    # Missing value imputation
    missing_strats = cfg.get("missing_values", {}).get("customers", {})
    if missing_strats:
        df = impute_missing(df, missing_strats)
    return df


def clean_accounts(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Apply all cleaning steps to accounts DataFrame."""
    df = df.copy()
    for col in ("account_type", "account_status", "currency"):
        if col in df.columns:
            df[col] = clean_string_series(df[col], case="upper")
    if "balance" in df.columns:
        df["balance"] = pd.to_numeric(df["balance"], errors="coerce")
    if "opened_date" in df.columns:
        df["opened_date"] = parse_date_series(df["opened_date"])
    missing_strats = cfg.get("missing_values", {}).get("accounts", {})
    if missing_strats:
        df = impute_missing(df, missing_strats)
    return df


def clean_transactions(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Apply all cleaning steps to transactions DataFrame."""
    df = df.copy()
    for col in ("currency", "transaction_type", "source_system"):
        if col in df.columns:
            df[col] = clean_string_series(df[col], case="upper")
    for col in ("meta_counterparty", "meta_location", "meta_country"):
        if col in df.columns:
            df[col] = clean_string_series(df[col], case="title")
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        df["amount"] = clip_negative_amounts(df["amount"], fill=0.01)
    if "transaction_date" in df.columns:
        df["transaction_date"] = parse_date_series(df["transaction_date"])
        df = reject_impossible_dates(df, "transaction_date", 1990, 2030)
    missing_strats = cfg.get("missing_values", {}).get("transactions", {})
    if missing_strats:
        df = impute_missing(df, missing_strats)
    return df
