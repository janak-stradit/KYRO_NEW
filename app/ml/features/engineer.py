"""
ml/features/engineer.py — Builds the flat feature vector consumed by the ML
models from a transaction, its customer, and their transaction history.

Real SQL-backed features (not placeholders): rolling stats, velocity counts,
percentiles, z-scores, geo diversity, and behavioral-baseline deviations.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.ml.features.customer_profile import build_customer_profile, calculate_deviation
from app.ml.features.feature_store import cache_json, get_cached_json
from app.services.rules_engine import HIGH_RISK_COUNTRIES

CUSTOMER_TYPE_ENCODING = {"INDIVIDUAL": 0, "CORPORATE": 1, "FUND": 2}
RISK_LEVEL_ENCODING = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
TRANSACTION_TYPE_ENCODING = {"DEPOSIT": 0, "WITHDRAWAL": 1, "TRANSFER": 2, "FX": 3, "TRADE": 4}
CURRENCY_ENCODING_DEFAULT = 0  # unseen currencies fall back to this bucket
CURRENCY_ENCODING = {"USD": 0, "EUR": 1, "GBP": 2, "JPY": 3, "CHF": 4}

GLOBAL_STATS_CACHE_KEY = "ml:global_amount_stats"
GLOBAL_STATS_TTL_SECONDS = 3600


def country_risk_score(country: str | None) -> float:
    if not country:
        return 20.0  # unknown — mild baseline risk, not zero
    return 90.0 if country.strip().upper() in HIGH_RISK_COUNTRIES else 10.0


def get_global_amount_stats(db: Session) -> dict[str, float]:
    """Mean/std/percentile breakpoints of transaction amounts across all
    customers, cached in Redis since recomputing per-request would be
    wasteful (and isn't needed at sub-hourly freshness)."""
    cached = get_cached_json(GLOBAL_STATS_CACHE_KEY)
    if cached is not None:
        return cached

    row = db.query(
        func.avg(Transaction.amount),
        func.stddev_pop(Transaction.amount),
        func.percentile_cont(0.5).within_group(Transaction.amount.asc()),
        func.percentile_cont(0.9).within_group(Transaction.amount.asc()),
        func.percentile_cont(0.99).within_group(Transaction.amount.asc()),
        func.count(Transaction.id),
    ).one()
    mean, std, p50, p90, p99, count = row

    stats = {
        "mean": float(mean or 0),
        "std": float(std or 1) or 1.0,
        "p50": float(p50 or 0),
        "p90": float(p90 or 0),
        "p99": float(p99 or 0),
        "count": int(count or 0),
    }
    cache_json(GLOBAL_STATS_CACHE_KEY, stats, ttl_seconds=GLOBAL_STATS_TTL_SECONDS)
    return stats


def _global_amount_percentile(amount: float, stats: dict[str, float]) -> float:
    breakpoints = [(0.5, stats["p50"]), (0.9, stats["p90"]), (0.99, stats["p99"])]
    percentile = 0.0
    for pct, value in breakpoints:
        if amount >= value:
            percentile = pct
    return percentile * 100


def compute_transaction_features(db: Session, txn: Transaction, customer: Customer) -> dict[str, float]:
    """The full feature vector for one transaction. Returns floats only
    (booleans as 0/1, categoricals label-encoded) so it's ready for sklearn."""
    amount = float(txn.amount)
    txn_date = txn.transaction_date

    # ── Time-based, raw transaction features ───────────────────
    features: dict[str, float] = {
        "amount": amount,
        "currency_encoded": float(CURRENCY_ENCODING.get(txn.currency, CURRENCY_ENCODING_DEFAULT)),
        "transaction_type_encoded": float(TRANSACTION_TYPE_ENCODING.get(txn.transaction_type or "", -1)),
        "hour_of_day": float(txn_date.hour),
        "day_of_week": float(txn_date.weekday()),
        "is_weekend": 1.0 if txn_date.weekday() >= 5 else 0.0,
        "is_night": 1.0 if txn_date.hour < 6 else 0.0,
    }

    # ── One history query covers rolling/velocity/percentile/time-since ───
    lookback_start = txn_date - timedelta(days=90)
    history = (
        db.query(Transaction)
        .filter(
            Transaction.customer_id == txn.customer_id,
            Transaction.transaction_date >= lookback_start,
            Transaction.transaction_date < txn_date,
        )
        .order_by(Transaction.transaction_date.desc())
        .all()
    )

    def _window(days: int) -> list[Transaction]:
        cutoff = txn_date - timedelta(days=days)
        return [t for t in history if t.transaction_date >= cutoff]

    def _mean_std(values: list[float]) -> tuple[float, float]:
        if not values:
            return 0.0, 0.0
        m = sum(values) / len(values)
        if len(values) < 2:
            return m, 0.0
        var = sum((v - m) ** 2 for v in values) / len(values)
        return m, var**0.5

    w7, w30, w90 = _window(7), _window(30), history
    avg7, std7 = _mean_std([float(t.amount) for t in w7])
    avg30, std30 = _mean_std([float(t.amount) for t in w30])
    avg90, _ = _mean_std([float(t.amount) for t in w90])

    w1h = _window(1 / 24)
    w24h = _window(1)
    w7d = _window(7)
    w30d = _window(30)

    features.update(
        {
            "rolling_avg_7d": avg7,
            "rolling_avg_30d": avg30,
            "rolling_avg_90d": avg90,
            "rolling_std_7d": std7,
            "rolling_std_30d": std30,
            "txn_count_1h": float(len(w1h)),
            "txn_count_24h": float(len(w24h)),
            "txn_count_7d": float(len(w7d)),
            "txn_count_30d": float(len(w30d)),
            "amount_sum_24h": float(sum(float(t.amount) for t in w24h)),
            "amount_sum_7d": float(sum(float(t.amount) for t in w7d)),
        }
    )

    # ── Percentiles / z-score vs customer + global history ────
    customer_amounts = sorted(float(t.amount) for t in history)
    if customer_amounts:
        rank = sum(1 for a in customer_amounts if a <= amount)
        features["amount_percentile_customer"] = 100.0 * rank / len(customer_amounts)
    else:
        features["amount_percentile_customer"] = 50.0

    global_stats = get_global_amount_stats(db)
    features["amount_percentile_global"] = _global_amount_percentile(amount, global_stats)
    features["amount_zscore"] = (amount - global_stats["mean"]) / global_stats["std"]

    # ── Time-since-last-transaction features ───────────────────
    if history:
        last_txn = history[0]
        features["time_since_last_txn"] = max(0.0, (txn_date - last_txn.transaction_date).total_seconds() / 60.0)
        same_cp = next((t for t in history if t.meta_counterparty == txn.meta_counterparty and txn.meta_counterparty), None)
        features["time_since_last_txn_same_counterparty"] = (
            max(0.0, (txn_date - same_cp.transaction_date).total_seconds() / 60.0) if same_cp else -1.0
        )
        gaps = [
            (history[i].transaction_date - history[i + 1].transaction_date).total_seconds() / 60.0
            for i in range(len(history) - 1)
        ]
        features["avg_time_between_txns"] = sum(gaps) / len(gaps) if gaps else -1.0
    else:
        features["time_since_last_txn"] = -1.0
        features["time_since_last_txn_same_counterparty"] = -1.0
        features["avg_time_between_txns"] = -1.0

    # ── Customer-level features ─────────────────────────────────
    now = txn_date
    customer_age_days = (now - customer.created_at).days if customer.created_at else 0
    account_count = db.query(func.count(Account.id)).filter(Account.customer_id == customer.id).scalar() or 0
    total_balance = db.query(func.coalesce(func.sum(Account.balance), 0)).filter(Account.customer_id == customer.id).scalar()
    kyc_days = (now - customer.kyc_last_review).days if customer.kyc_last_review else -1

    features.update(
        {
            "customer_age_days": float(customer_age_days),
            "account_count": float(account_count),
            "total_balance": float(total_balance or 0),
            "kyc_days_since_review": float(kyc_days),
            "pep_flag": 1.0 if customer.pep_flag else 0.0,
            "sanctions_flag": 1.0 if customer.sanctions_flag else 0.0,
            "adverse_media_flag": 1.0 if customer.adverse_media_flag else 0.0,
            "current_risk_level": float(RISK_LEVEL_ENCODING.get(customer.risk_level, 0)),
            "current_risk_score": float(customer.risk_score),
            "customer_type_encoded": float(CUSTOMER_TYPE_ENCODING.get(customer.customer_type or "", -1)),
            "country_risk_score": country_risk_score(customer.country),
            "residency_risk_score": country_risk_score(customer.residency_country),
        }
    )

    # ── Counterparty / geographic features ──────────────────────
    countries_30d = {t.meta_country for t in w30d if t.meta_country}
    counterparties_7d = {t.meta_counterparty for t in w7d if t.meta_counterparty}
    counterparties_30d = {t.meta_counterparty for t in w30d if t.meta_counterparty}
    known_counterparties = {t.meta_counterparty for t in history if t.meta_counterparty}

    high_risk_hit = any(
        c and c.strip().upper() in HIGH_RISK_COUNTRIES
        for c in (txn.meta_country, txn.meta_destination_country, txn.meta_origin_country)
    )
    cross_border = bool(
        txn.meta_origin_country and txn.meta_destination_country and txn.meta_origin_country != txn.meta_destination_country
    )

    features.update(
        {
            "geo_diversity_score": float(len(countries_30d)),
            "unique_counterparties_7d": float(len(counterparties_7d)),
            "unique_counterparties_30d": float(len(counterparties_30d)),
            "new_counterparty_flag": 1.0 if (txn.meta_counterparty and txn.meta_counterparty not in known_counterparties) else 0.0,
            "counterparty_country_risk": country_risk_score(txn.meta_country),
            "destination_country_risk": country_risk_score(txn.meta_destination_country),
            "origin_country_risk": country_risk_score(txn.meta_origin_country),
            "high_risk_country_flag": 1.0 if high_risk_hit else 0.0,
            "cross_border_flag": 1.0 if cross_border else 0.0,
            "same_country_flag": 0.0 if cross_border else 1.0,
        }
    )

    # ── Behavioral baseline deviation ───────────────────────────
    profile = build_customer_profile(db, customer.id, as_of=txn_date)
    recent_daily_count = len(w7d) / 7.0
    deviations = calculate_deviation(profile, txn, recent_daily_count)
    features.update(deviations)

    return features
