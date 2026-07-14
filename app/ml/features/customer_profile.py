"""
ml/features/customer_profile.py — Per-customer behavioral baseline, built from
their own transaction history, and deviation scoring against it.
"""
from __future__ import annotations

import statistics
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.transaction import Transaction

BASELINE_WINDOW_DAYS = 90


@dataclass
class CustomerBehavioralProfile:
    customer_id: uuid.UUID
    sample_size: int = 0
    typical_amount_mean: float | None = None
    typical_amount_std: float | None = None
    typical_frequency_per_day: float = 0.0
    typical_hours: list[int] = field(default_factory=list)
    typical_days: list[int] = field(default_factory=list)
    typical_countries: set[str] = field(default_factory=set)
    typical_counterparties: set[str] = field(default_factory=set)
    typical_transaction_types: set[str] = field(default_factory=set)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def build_customer_profile(
    db: Session, customer_id: uuid.UUID, *, as_of: datetime, window_days: int = BASELINE_WINDOW_DAYS
) -> CustomerBehavioralProfile:
    """Build a behavioral baseline from the customer's transactions in the
    `window_days` preceding `as_of` (exclusive), so scoring a transaction
    never leaks itself into its own baseline."""
    cutoff = as_of - timedelta(days=window_days)
    history = (
        db.query(Transaction)
        .filter(
            Transaction.customer_id == customer_id,
            Transaction.transaction_date >= cutoff,
            Transaction.transaction_date < as_of,
        )
        .all()
    )

    if not history:
        return CustomerBehavioralProfile(customer_id=customer_id, last_updated=as_of)

    amounts = [float(t.amount) for t in history]
    hours = Counter(t.transaction_date.hour for t in history)
    days = Counter(t.transaction_date.weekday() for t in history)

    return CustomerBehavioralProfile(
        customer_id=customer_id,
        sample_size=len(history),
        typical_amount_mean=statistics.mean(amounts),
        typical_amount_std=statistics.pstdev(amounts) if len(amounts) > 1 else 0.0,
        typical_frequency_per_day=len(history) / window_days,
        typical_hours=[h for h, _ in hours.most_common(3)],
        typical_days=[d for d, _ in days.most_common(3)],
        typical_countries={t.meta_country for t in history if t.meta_country},
        typical_counterparties={t.meta_counterparty for t in history if t.meta_counterparty},
        typical_transaction_types={t.transaction_type for t in history if t.transaction_type},
        last_updated=as_of,
    )


def calculate_deviation(profile: CustomerBehavioralProfile, txn: Transaction, recent_daily_count: float) -> dict:
    """Deviation of `txn` from the customer's baseline. `recent_daily_count`
    is the caller-supplied current transaction frequency (txns/day) to
    compare against the baseline's typical_frequency_per_day."""
    amount = float(txn.amount)

    if profile.typical_amount_mean is not None:
        std = profile.typical_amount_std or 1.0
        amount_zscore = (amount - profile.typical_amount_mean) / std
        deviation_from_avg_amount = amount / profile.typical_amount_mean if profile.typical_amount_mean else 1.0
    else:
        amount_zscore = 0.0
        deviation_from_avg_amount = 1.0

    hour_deviation = 1.0 if (profile.typical_hours and txn.transaction_date.hour not in profile.typical_hours) else 0.0
    geo_deviation = 1.0 if (txn.meta_country and profile.typical_countries and txn.meta_country not in profile.typical_countries) else 0.0

    deviation_from_avg_frequency = (
        recent_daily_count / profile.typical_frequency_per_day if profile.typical_frequency_per_day else 1.0
    )

    # Composite: simple weighted sum, clipped for stability.
    pattern_break_score = min(
        10.0,
        abs(amount_zscore) * 0.5 + hour_deviation * 1.5 + geo_deviation * 2.0 + abs(deviation_from_avg_frequency - 1.0) * 0.5,
    )

    return {
        "amount_zscore": amount_zscore,
        "deviation_from_avg_amount": deviation_from_avg_amount,
        "deviation_from_avg_frequency": deviation_from_avg_frequency,
        "hour_deviation": hour_deviation,
        "geo_deviation": geo_deviation,
        "pattern_break_score": pattern_break_score,
    }
