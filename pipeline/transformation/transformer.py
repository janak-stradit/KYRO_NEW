"""
transformation/transformer.py — Data transformation and encoding layer.
Supports: Label/OHE/Ordinal/Frequency/Target Encoding,
          Log/Box-Cox/Yeo-Johnson/Power transforms,
          Polynomial features, Date extraction, Window functions.
Scalers: Standard/MinMax/Robust/MaxAbs/Normalizer — persisted as joblib artifacts.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import (
    LabelEncoder, StandardScaler, MinMaxScaler,
    RobustScaler, MaxAbsScaler, Normalizer, PowerTransformer,
)
from sklearn.preprocessing import PolynomialFeatures

logger = logging.getLogger(__name__)

SCALER_REGISTRY: dict[str, Any] = {}
SCALER_DIR = Path("artifacts/scalers")

_SCALER_MAP = {
    "standard": StandardScaler,
    "minmax": MinMaxScaler,
    "robust": RobustScaler,
    "maxabs": MaxAbsScaler,
    "normalizer": Normalizer,
}


# ── Scaler management ─────────────────────────────────────────

def get_or_fit_scaler(name: str, method: str, data: np.ndarray) -> Any:
    """Return a fitted scaler from registry; fit-and-cache if not present."""
    if name not in SCALER_REGISTRY:
        # Try to load from disk first (prevents train-test leakage across pipeline runs)
        scaler = load_scaler(name)
        if scaler is None:
            cls = _SCALER_MAP.get(method, RobustScaler)
            scaler = cls()
            scaler.fit(data.reshape(-1, 1))
            _persist_scaler(name, scaler)
            logger.info("Fitted new scaler '%s' (%s)", name, method)
        SCALER_REGISTRY[name] = scaler
    return SCALER_REGISTRY[name]


def _persist_scaler(name: str, scaler: Any) -> None:
    SCALER_DIR.mkdir(parents=True, exist_ok=True)
    path = SCALER_DIR / f"{name}.pkl"
    with open(path, "wb") as f:
        pickle.dump(scaler, f)
    logger.debug("Persisted scaler: %s", path)


def load_scaler(name: str) -> Any | None:
    path = SCALER_DIR / f"{name}.pkl"
    if path.exists():
        with open(path, "rb") as f:
            scaler = pickle.load(f)
        SCALER_REGISTRY[name] = scaler
        logger.info("Loaded scaler: %s", name)
        return scaler
    return None


def scale_columns(
    df: pd.DataFrame,
    columns: list[str],
    method: str = "robust",
    suffix: str = "_scaled",
) -> pd.DataFrame:
    """Scale specified columns; appends suffix to column name."""
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            continue
        data = pd.to_numeric(df[col], errors="coerce").fillna(0).values
        scaler = get_or_fit_scaler(f"{col}_{method}", method, data)
        df[f"{col}{suffix}"] = scaler.transform(data.reshape(-1, 1)).flatten()
    return df


# ── Categorical Encoding ──────────────────────────────────────

def label_encode(df: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, dict]:
    """Label-encode categorical columns. Returns df and fitted encoders dict."""
    df = df.copy()
    encoders: dict[str, LabelEncoder] = {}
    for col in columns:
        if col not in df.columns:
            continue
        le = LabelEncoder()
        df[f"{col}_encoded"] = le.fit_transform(df[col].fillna("UNKNOWN").astype(str))
        encoders[col] = le
        logger.debug("Label encoded: %s (%d classes)", col, len(le.classes_))
    return df, encoders


def ordinal_encode(
    df: pd.DataFrame, column: str, categories: list[str]
) -> pd.DataFrame:
    """Map categories to integer ordinals [0, len-1]."""
    df = df.copy()
    cat_map = {v: i for i, v in enumerate(categories)}
    df[f"{column}_ordinal"] = df[column].map(cat_map).fillna(-1).astype(int)
    return df


def onehot_encode(df: pd.DataFrame, columns: list[str], drop_first: bool = False) -> pd.DataFrame:
    """One-hot encode categorical columns using pd.get_dummies."""
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            continue
        dummies = pd.get_dummies(df[col].fillna("UNKNOWN").astype(str), prefix=col, drop_first=drop_first)
        df = pd.concat([df, dummies], axis=1)
        logger.debug("One-hot encoded: %s → %d new cols", col, len(dummies.columns))
    return df


def frequency_encode(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Replace category with its frequency (count) in the column."""
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            continue
        freq = df[col].value_counts()
        df[f"{col}_freq"] = df[col].map(freq).fillna(0).astype(int)
    return df


def target_encode(
    df: pd.DataFrame, columns: list[str], target: str, smoothing: float = 1.0
) -> pd.DataFrame:
    """Bayesian target encoding with smoothing to prevent leakage."""
    if target not in df.columns:
        logger.warning("Target column '%s' not found for target encoding", target)
        return df
    df = df.copy()
    global_mean = df[target].mean()
    for col in columns:
        if col not in df.columns:
            continue
        stats = df.groupby(col)[target].agg(["mean", "count"])
        smooth = (stats["count"] * stats["mean"] + smoothing * global_mean) / (stats["count"] + smoothing)
        df[f"{col}_target_enc"] = df[col].map(smooth).fillna(global_mean)
    return df


# ── Numeric Transforms ────────────────────────────────────────

def log_transform(df: pd.DataFrame, columns: list[str], offset: float = 1.0) -> pd.DataFrame:
    """Apply log(x + offset) transform to handle zero/negative values."""
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            continue
        df[f"{col}_log"] = np.log(df[col].clip(lower=0) + offset)
    return df


def power_transform(
    df: pd.DataFrame, columns: list[str], method: str = "yeo-johnson"
) -> pd.DataFrame:
    """Apply Box-Cox or Yeo-Johnson power transform."""
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            continue
        pt = PowerTransformer(method=method)
        vals = pd.to_numeric(df[col], errors="coerce").fillna(df[col].median()).values
        try:
            df[f"{col}_power"] = pt.fit_transform(vals.reshape(-1, 1)).flatten()
        except Exception as exc:
            logger.warning("Power transform failed for '%s': %s", col, exc)
    return df


def polynomial_features(
    df: pd.DataFrame, columns: list[str], degree: int = 2
) -> pd.DataFrame:
    """Add polynomial interaction features."""
    subset = df[columns].fillna(0)
    pf = PolynomialFeatures(degree=degree, include_bias=False)
    poly_arr = pf.fit_transform(subset)
    poly_cols = [f"poly_{i}" for i in range(poly_arr.shape[1])]
    poly_df = pd.DataFrame(poly_arr, columns=poly_cols, index=df.index)
    return pd.concat([df, poly_df], axis=1)


# ── Date Feature Extraction ───────────────────────────────────

def extract_date_features(
    df: pd.DataFrame,
    col: str,
    features: list[str] | None = None,
    reference_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Extract temporal features from a datetime column.

    features: list of ['year','month','day','dayofweek','quarter',
                        'is_weekend','days_since']
    """
    if col not in df.columns or not pd.api.types.is_datetime64_any_dtype(df[col]):
        logger.warning("Date feature extraction skipped — '%s' is not datetime", col)
        return df
    df = df.copy()
    features = features or ["year", "month", "day", "dayofweek", "quarter", "is_weekend"]
    ref = reference_date or pd.Timestamp.now()
    ts = df[col]

    feat_map = {
        "year": ts.dt.year,
        "month": ts.dt.month,
        "day": ts.dt.day,
        "dayofweek": ts.dt.dayofweek,
        "quarter": ts.dt.quarter,
        "is_weekend": ts.dt.dayofweek.isin([5, 6]).astype(int),
        "days_since": (ref - ts).dt.days,
        "hour": ts.dt.hour if hasattr(ts.dt, "hour") else None,
    }
    for feat in features:
        if feat in feat_map and feat_map[feat] is not None:
            df[f"{col}_{feat}"] = feat_map[feat]
    return df
