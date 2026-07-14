"""
cleaning/outlier_detector.py — Outlier detection and handling.
Implements: IQR, Z-score, Modified Z-score, Isolation Forest, DBSCAN,
            Percentile clipping, Winsorization.
"""
from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import mstats
from sklearn.ensemble import IsolationForest
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

OutlierAction = Literal["winsorize", "remove", "flag", "store_separate"]


def detect_outliers_iqr(series: pd.Series, multiplier: float = 3.0) -> pd.Series:
    """Return boolean mask: True where value is an IQR outlier."""
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - multiplier * iqr, q3 + multiplier * iqr
    return (series < lower) | (series > upper)


def detect_outliers_zscore(series: pd.Series, threshold: float = 3.5) -> pd.Series:
    """Return boolean mask: True where |z-score| > threshold."""
    mean, std = series.mean(), series.std()
    if std == 0:
        return pd.Series(False, index=series.index)
    return ((series - mean) / std).abs() > threshold


def detect_outliers_modified_zscore(series: pd.Series, threshold: float = 3.5) -> pd.Series:
    """Modified Z-score using Median Absolute Deviation — robust to existing outliers."""
    median = series.median()
    mad = (series - median).abs().median()
    if mad == 0:
        return pd.Series(False, index=series.index)
    modified_z = 0.6745 * (series - median) / mad
    return modified_z.abs() > threshold


def detect_outliers_isolation_forest(
    df: pd.DataFrame, columns: list[str], contamination: float = 0.05
) -> pd.Series:
    """Isolation Forest multivariate outlier detection. Returns boolean mask."""
    data = df[columns].dropna()
    if data.empty:
        return pd.Series(False, index=df.index)
    model = IsolationForest(contamination=contamination, random_state=42, n_jobs=-1)
    preds = model.fit_predict(data)
    mask = pd.Series(False, index=df.index)
    mask.loc[data.index] = preds == -1
    return mask


def detect_outliers_dbscan(
    df: pd.DataFrame, columns: list[str], eps: float = 0.5, min_samples: int = 5
) -> pd.Series:
    """DBSCAN-based outlier detection (label=-1 = noise = outlier)."""
    data = df[columns].dropna()
    if data.empty:
        return pd.Series(False, index=df.index)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(data)
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(scaled)
    mask = pd.Series(False, index=df.index)
    mask.loc[data.index] = labels == -1
    return mask


def detect_outliers_percentile(
    series: pd.Series, lower: float = 0.01, upper: float = 0.99
) -> pd.Series:
    """Return boolean mask for values outside [lower_pct, upper_pct] percentile."""
    lo, hi = series.quantile(lower), series.quantile(upper)
    return (series < lo) | (series > hi)


def winsorize_series(series: pd.Series, limits=(0.01, 0.01)) -> pd.Series:
    """Clip series to [lower, upper] percentile boundaries (Winsorization)."""
    vals = mstats.winsorize(series.dropna(), limits=limits)
    result = series.copy()
    result.loc[series.notna()] = vals
    return result


def handle_outliers(
    df: pd.DataFrame,
    columns: list[str],
    method: str = "iqr",
    action: OutlierAction = "winsorize",
    iqr_multiplier: float = 3.0,
    zscore_threshold: float = 3.5,
    percentile_lower: float = 0.01,
    percentile_upper: float = 0.99,
    contamination: float = 0.05,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Detect and handle outliers in specified numeric columns.

    Args:
        method: 'iqr' | 'zscore' | 'modified_zscore' | 'isolation_forest'
                | 'dbscan' | 'percentile'
        action: 'winsorize' | 'remove' | 'flag' | 'store_separate'

    Returns:
        (clean_df, outlier_df, report)
    """
    df = df.copy()
    overall_mask = pd.Series(False, index=df.index)
    report = {}

    for col in columns:
        if col not in df.columns:
            logger.warning("Outlier column not found: %s", col)
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue

        if method == "iqr":
            mask = detect_outliers_iqr(series, iqr_multiplier)
        elif method == "zscore":
            mask = detect_outliers_zscore(series, zscore_threshold)
        elif method == "modified_zscore":
            mask = detect_outliers_modified_zscore(series, zscore_threshold)
        elif method == "isolation_forest":
            mask = detect_outliers_isolation_forest(df, [col], contamination)
        elif method == "dbscan":
            mask = detect_outliers_dbscan(df, [col])
        elif method == "percentile":
            mask = detect_outliers_percentile(series, percentile_lower, percentile_upper)
        else:
            raise ValueError(f"Unknown outlier method: {method}")

        # Re-align mask to full df index
        full_mask = pd.Series(False, index=df.index)
        full_mask.loc[mask.index] = mask

        count = full_mask.sum()
        report[col] = {
            "method": method, "outlier_count": int(count),
            "action": action,
            "lower_bound": float(series.quantile(percentile_lower)),
            "upper_bound": float(series.quantile(percentile_upper)),
        }
        logger.info("Outliers detected in '%s': %d (method=%s)", col, count, method)

        if action == "winsorize":
            df[col] = winsorize_series(df[col], limits=(percentile_lower, 1 - percentile_upper))
            overall_mask |= pd.Series(False, index=df.index)  # winsorize, don't remove
        elif action == "remove":
            overall_mask |= full_mask
        elif action == "flag":
            df[f"is_outlier_{col}"] = full_mask.astype(int)
        elif action == "store_separate":
            overall_mask |= full_mask

    outlier_df = df[overall_mask].copy() if action in ("remove", "store_separate") else pd.DataFrame()
    clean_df = df[~overall_mask].copy() if action in ("remove", "store_separate") else df

    return clean_df, outlier_df, report
