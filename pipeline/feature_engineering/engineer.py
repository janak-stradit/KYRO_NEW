"""
feature_engineering/engineer.py — AML-specific ML feature engineering.
Generates: date features, lag/rolling features, ratios, flags, KPIs,
           hash features, frequency counts, rankings.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

HIGH_RISK_COUNTRIES = {"KP", "IR", "SY", "CU", "VE", "MM", "BY", "RU", "SO", "YE"}


# ── Flag Features ─────────────────────────────────────────────

def add_aml_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Add binary AML signal flags derived from domain knowledge."""
    df = df.copy()
    if "amount" in df.columns:
        df["flag_high_value"] = (pd.to_numeric(df["amount"], errors="coerce") > 10000).astype(int)
        df["flag_structuring"] = (
            (pd.to_numeric(df["amount"], errors="coerce") >= 9000) &
            (pd.to_numeric(df["amount"], errors="coerce") < 10000)
        ).astype(int)
    if "meta_country_code" in df.columns:
        df["flag_high_risk_country"] = df["meta_country_code"].isin(HIGH_RISK_COUNTRIES).astype(int)
    if "pep_flag" in df.columns:
        df["flag_pep"] = df["pep_flag"].astype(int)
    if "sanctions_flag" in df.columns:
        df["flag_sanctioned"] = df["sanctions_flag"].astype(int)
    if "adverse_media_flag" in df.columns:
        df["flag_adverse_media"] = df["adverse_media_flag"].astype(int)
    if all(c in df.columns for c in ("pep_flag", "sanctions_flag", "adverse_media_flag")):
        df["flag_any_compliance_alert"] = (
            df["pep_flag"].astype(int) |
            df["sanctions_flag"].astype(int) |
            df["adverse_media_flag"].astype(int)
        )
    return df


# ── Lag Features ──────────────────────────────────────────────

def add_lag_features(
    df: pd.DataFrame,
    col: str,
    group_by: str,
    sort_by: str,
    lags: list[int] = (1, 3, 7),
) -> pd.DataFrame:
    """
    Add lag features for a column within groups, sorted by time.
    e.g., amount_lag_1, amount_lag_3 for each account_id.
    """
    if col not in df.columns or group_by not in df.columns or sort_by not in df.columns:
        logger.warning("Lag feature skipped — missing columns")
        return df
    df = df.copy().sort_values([group_by, sort_by])
    for lag in lags:
        df[f"{col}_lag_{lag}"] = df.groupby(group_by)[col].shift(lag)
        logger.debug("Added lag feature: %s_lag_%d", col, lag)
    return df


# ── Rolling / Window Features ─────────────────────────────────

def add_rolling_features(
    df: pd.DataFrame,
    col: str,
    group_by: str,
    sort_by: str,
    windows: list[int] = (7, 30, 90),
    agg_funcs: list[str] = ("mean", "std", "max", "min", "sum"),
) -> pd.DataFrame:
    """
    Add rolling window aggregation features per group.
    Windows are in rows (not calendar days) unless sort_by is a DatetimIndex.
    """
    if col not in df.columns or group_by not in df.columns:
        return df
    df = df.copy().sort_values([group_by, sort_by])
    for w in windows:
        for agg in agg_funcs:
            new_col = f"{col}_rolling_{w}_{agg}"
            df[new_col] = (
                df.groupby(group_by)[col]
                .transform(lambda x: x.rolling(window=w, min_periods=1).agg(agg))
            )
            logger.debug("Added rolling feature: %s", new_col)
    return df


# ── Ratio / Interaction Features ──────────────────────────────

def add_ratio_feature(
    df: pd.DataFrame, numerator: str, denominator: str, name: str | None = None
) -> pd.DataFrame:
    """Add ratio column; handles division by zero with NaN."""
    n = name or f"{numerator}_to_{denominator}_ratio"
    if numerator not in df.columns or denominator not in df.columns:
        return df
    df = df.copy()
    denom = pd.to_numeric(df[denominator], errors="coerce").replace(0, np.nan)
    df[n] = pd.to_numeric(df[numerator], errors="coerce") / denom
    return df


def add_percentage_feature(
    df: pd.DataFrame, part_col: str, total_col: str, name: str | None = None
) -> pd.DataFrame:
    """Add percentage feature: (part / total) * 100."""
    n = name or f"{part_col}_pct_of_{total_col}"
    if part_col not in df.columns or total_col not in df.columns:
        return df
    df = df.copy()
    total = pd.to_numeric(df[total_col], errors="coerce").replace(0, np.nan)
    df[n] = (pd.to_numeric(df[part_col], errors="coerce") / total) * 100
    return df


# ── Aggregation / KPI Features ────────────────────────────────

def compute_customer_kpis(
    customers: pd.DataFrame,
    accounts: pd.DataFrame,
    transactions: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute customer-level business KPIs by joining across entities.

    Returns customers DataFrame enriched with KPI columns.
    """
    kpis = customers[["customer_id"]].copy()

    # Account KPIs
    if "customer_id" in accounts.columns:
        acc_kpi = accounts.groupby("customer_id").agg(
            account_count=("account_id", "count"),
            total_balance=("balance", "sum"),
            avg_balance=("balance", "mean"),
            max_balance=("balance", "max"),
            active_accounts=("account_status", lambda x: (x == "ACTIVE").sum()),
        ).reset_index()
        kpis = kpis.merge(acc_kpi, on="customer_id", how="left")

    # Transaction KPIs
    if "customer_id" in transactions.columns:
        txn_kpi = transactions.groupby("customer_id").agg(
            txn_count=("transaction_id", "count"),
            txn_amount_total=("amount", "sum"),
            txn_amount_mean=("amount", "mean"),
            txn_amount_max=("amount", "max"),
            txn_high_value_count=("amount", lambda x: (pd.to_numeric(x, errors="coerce") > 10000).sum()),
            unique_currencies=("currency", "nunique"),
        ).reset_index()
        kpis = kpis.merge(txn_kpi, on="customer_id", how="left")

    # Merge back to customers
    if len(kpis.columns) > 1:
        customers = customers.merge(kpis, on="customer_id", how="left")
    return customers


# ── Hash / Frequency Features ─────────────────────────────────

def add_hash_feature(df: pd.DataFrame, columns: list[str], name: str = "row_hash") -> pd.DataFrame:
    """Add an MD5-based hash feature from multiple columns (for similarity grouping)."""
    df = df.copy()
    def _hash_row(row):
        raw = "|".join(str(row[c]) for c in columns if c in row.index)
        return hashlib.md5(raw.encode()).hexdigest()[:16]
    df[name] = df.apply(_hash_row, axis=1)
    return df


def add_frequency_count(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Add column with the count of each value's occurrence in the dataset."""
    if col not in df.columns:
        return df
    df = df.copy()
    freq = df[col].value_counts()
    df[f"{col}_frequency"] = df[col].map(freq).fillna(0).astype(int)
    return df


def add_rank_feature(
    df: pd.DataFrame, col: str, group_by: str | None = None, ascending: bool = False
) -> pd.DataFrame:
    """Add percentile rank feature (0–1) for a numeric column."""
    if col not in df.columns:
        return df
    df = df.copy()
    if group_by and group_by in df.columns:
        df[f"{col}_rank"] = df.groupby(group_by)[col].rank(pct=True, ascending=ascending)
    else:
        df[f"{col}_rank"] = pd.to_numeric(df[col], errors="coerce").rank(pct=True, ascending=ascending)
    return df


# ── Master Feature Builder ────────────────────────────────────

def build_customer_features(
    customers: pd.DataFrame,
    accounts: pd.DataFrame,
    transactions: pd.DataFrame,
    feature_set_version: str = "1.0.0",
) -> pd.DataFrame:
    """
    Full customer ML feature vector pipeline.
    Returns a DataFrame ready for the feature_store.customer_features table.
    """
    if customers.empty:
        return customers.copy()
    df = customers.copy()
    # Flags
    df = add_aml_flags(df)
    # KPIs (joins)
    df = compute_customer_kpis(df, accounts, transactions)
    # Rankings
    df = add_rank_feature(df, "risk_score", ascending=False)
    # Frequency
    df = add_frequency_count(df, "country")
    df["feature_set_version"] = feature_set_version
    logger.info("Built customer features: %d rows, %d cols", len(df), len(df.columns))
    return df


def build_transaction_features(
    transactions: pd.DataFrame,
    feature_set_version: str = "1.0.0",
) -> pd.DataFrame:
    """
    Full transaction ML feature vector pipeline.
    Returns DataFrame ready for feature_store.transaction_features.
    """
    if transactions.empty:
        return transactions.copy()
    df = transactions.copy()
    df = add_aml_flags(df)
    if "transaction_date" in df.columns and pd.api.types.is_datetime64_any_dtype(df["transaction_date"]):
        from pipeline.transformation.transformer import extract_date_features
        df = extract_date_features(df, "transaction_date",
                                   ["year", "month", "day", "dayofweek", "quarter", "is_weekend"])
    df = add_lag_features(df, "amount", "account_id", "transaction_date", lags=[1, 3, 7])
    df = add_rolling_features(df, "amount", "account_id", "transaction_date",
                               windows=[7, 30], agg_funcs=["mean", "std"])
    df = add_rank_feature(df, "amount", group_by="account_id", ascending=False)
    df = add_frequency_count(df, "transaction_type")
    df["feature_set_version"] = feature_set_version
    logger.info("Built transaction features: %d rows, %d cols", len(df), len(df.columns))
    return df
