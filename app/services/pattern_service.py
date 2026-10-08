"""
services/pattern_service.py — Behavioural patterns, measured against each
customer's own history.

For every customer, the last 30 days of transactions (the *window*) are
compared with the 90 days before that (the *baseline*). A pattern is flagged
only when the window departs from that customer's baseline, so a customer
who has always behaved a certain way is not flagged for it. Transactions are
dated by when they happened, not when they were loaded.

Most patterns need an established baseline (at least MIN_BASELINE
transactions); a customer without one is not judged. The thresholds below
are a starting policy for compliance to tune, not a standard.
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.transaction import Transaction
from app.services import rule_config_service

WINDOW_DAYS = 30
BASELINE_DAYS = 90
MIN_BASELINE = 5            # baseline transactions needed before a customer is judged
AMOUNT_MULTIPLE = 2.0       # unusual amount: more than this many times the customer's previous largest
VELOCITY_MULTIPLE = 3.0     # velocity spike: a day with this many times the usual daily count...
VELOCITY_MIN_PER_DAY = 4    # ...and at least this many transactions
NEW_SHARE_JUMP = 0.3        # counterparties / countries: share of new ones up by this much...
NEW_SHARE_MIN = 3           # ...with at least this many new ones in the window
DORMANT_DAYS = 45           # reactivation: silent for at least this long before the window
DORMANT_MIN_HISTORY = 3     # ...after at least this many earlier transactions

PATTERNS: list[dict[str, Any]] = [
    {
        "id": "THRESHOLD_BREACH", "legacy_name": "TRANSACTION_SIZE", "label": "Unusual Amount",
        "description": "A transaction more than double the largest the customer made in that currency over the previous 90 days.",
        "icon": "fa-money-bill-wave", "color": "danger", "severity": "HIGH", "hit_unit": "transactions",
    },
    {
        "id": "VELOCITY_SPIKE", "legacy_name": "FREQUENCY", "label": "Velocity Spike",
        "description": "A day with at least four transactions and three times the customer's usual daily number.",
        "icon": "fa-tachometer-alt", "color": "warning", "severity": "MEDIUM", "hit_unit": "days",
    },
    {
        "id": "GEOGRAPHIC_SHIFT", "legacy_name": "GEOGRAPHY", "label": "Geographic Shift",
        "description": "First dealings with a high-risk jurisdiction, or a clear rise in the share of transactions involving countries new to the customer.",
        "icon": "fa-globe", "color": "info", "severity": "HIGH", "hit_unit": "transactions",
    },
    {
        "id": "COUNTERPARTY_CHANGES", "legacy_name": "COUNTERPARTY", "label": "Counterparty Changes",
        "description": "A clear rise in the share of transactions going to counterparties the customer has not used before.",
        "icon": "fa-network-wired", "color": "primary", "severity": "MEDIUM", "hit_unit": "transactions",
    },
    {
        "id": "COMPLEXITY_SHIFT", "legacy_name": "COMPLEXITY_SHIFT", "label": "New Transaction Type",
        "description": "A type of transaction (for example FX or trade) the customer had not used in the previous 90 days.",
        "icon": "fa-project-diagram", "color": "secondary", "severity": "MEDIUM", "hit_unit": "transactions",
    },
    {
        "id": "INACTIVE_REACTIVATION", "legacy_name": "INACTIVE_REACTIVATION", "label": "Inactive Reactivation",
        "description": "Activity resuming after at least 45 days of silence on a previously active customer.",
        "icon": "fa-redo", "color": "success", "severity": "HIGH", "hit_unit": "transactions",
    },
]
PATTERN_LABELS = {p["id"]: p["label"] for p in PATTERNS}


def _money(amount: float, currency: str | None) -> str:
    return f"{amount:,.2f} {currency or ''}".strip()


def _new_share(baseline_values: list[str], window: list, index: int) -> tuple[list, float, float]:
    """
    Window transactions whose value at `index` the customer has not used
    before, with the share of such first-time values now and in the baseline.
    A customer who always deals with new parties is not flagged for continuing to.
    """
    seen: set[str] = set()
    first_time = 0
    for value in baseline_values:
        first_time += value not in seen
        seen.add(value)
    with_value = [t for t in window if t[index]]
    fresh = []
    for t in with_value:
        if t[index] not in seen:
            fresh.append(t)
            seen.add(t[index])
    before = first_time / len(baseline_values) if baseline_values else 0.0
    now = len(fresh) / len(with_value) if with_value else 0.0
    return fresh, now, before


def _detect(
    baseline: list, window: list, earlier_count: int, last_before_window: datetime | None, high_risk: set[str]
) -> dict[str, dict[str, Any]]:
    """
    Patterns for one customer. `baseline` and `window` are that customer's
    transactions (oldest first) as rows of (date, amount, currency,
    counterparty, country, type). Returns {pattern_id: {"hits", "evidence", "last"}}.
    """
    found: dict[str, dict[str, Any]] = {}
    if not window:
        return found
    established = len(baseline) >= MIN_BASELINE

    def add(pattern: str, hits: int, evidence: str, last: datetime) -> None:
        found[pattern] = {"hits": hits, "evidence": evidence, "last": last}

    # Reactivation is about the absence of a recent baseline, so it is checked first
    first = window[0][0]
    if last_before_window is not None and earlier_count >= DORMANT_MIN_HISTORY:
        gap = (first - last_before_window).days
        if gap >= DORMANT_DAYS:
            add("INACTIVE_REACTIVATION", len(window), f"{len(window)} transactions after {gap} days with none", window[-1][0])

    if not established:
        return found

    # Unusual amount, per currency (amounts in different currencies are not comparable)
    largest: dict[str, float] = {}
    counts: Counter = Counter()
    for _, amount, currency, *_ in baseline:
        largest[currency] = max(largest.get(currency, 0.0), float(amount))
        counts[currency] += 1
    large = [t for t in window if counts[t[2]] >= MIN_BASELINE and float(t[1]) > AMOUNT_MULTIPLE * largest[t[2]]]
    if large:
        top = max(large, key=lambda t: float(t[1]) / largest[t[2]])
        add("THRESHOLD_BREACH", len(large),
            f"{_money(float(top[1]), top[2])} against a previous largest of {_money(largest[top[2]], top[2])}", max(t[0] for t in large))

    # Velocity: busiest window days against the usual number on an active baseline day
    baseline_days = Counter(t[0].date() for t in baseline)
    usual_per_day = sum(baseline_days.values()) / len(baseline_days)
    spikes = {day: n for day, n in Counter(t[0].date() for t in window).items()
              if n >= VELOCITY_MIN_PER_DAY and n >= VELOCITY_MULTIPLE * usual_per_day}
    if spikes:
        day, n = max(spikes.items(), key=lambda kv: kv[1])
        add("VELOCITY_SPIKE", len(spikes), f"{n} transactions on {day.isoformat()} against a usual {usual_per_day:.1f} a day",
            max(t[0] for t in window if t[0].date() in spikes))

    # Geography: a first high-risk jurisdiction, or new countries turning up much more often than before
    baseline_countries = [t[4] for t in baseline if t[4]]
    risky_before = {c.upper() for c in baseline_countries} & high_risk
    risky_now = [t for t in window if t[4] and t[4].upper() in high_risk]
    fresh, now, before = _new_share(baseline_countries, window, 4)
    if risky_now and not risky_before:
        add("GEOGRAPHIC_SHIFT", len(risky_now),
            "first dealings with a high-risk jurisdiction: " + ", ".join(sorted({t[4] for t in risky_now})[:4]), max(t[0] for t in risky_now))
    elif baseline_countries and len(fresh) >= NEW_SHARE_MIN and now - before >= NEW_SHARE_JUMP:
        add("GEOGRAPHIC_SHIFT", len(fresh), f"{now:.0%} of transactions involve a country new to the customer, up from {before:.0%}",
            max(t[0] for t in fresh))

    # New transaction type
    known_types = {t[5] for t in baseline if t[5]}
    novel = [t for t in window if t[5] and t[5] not in known_types]
    if novel and known_types:
        add("COMPLEXITY_SHIFT", len(novel), "first use of " + ", ".join(sorted({str(t[5]).lower() for t in novel})), max(t[0] for t in novel))

    # Counterparties: transactions going to someone new much more often than before
    baseline_counterparties = [t[3] for t in baseline if t[3]]
    fresh, now, before = _new_share(baseline_counterparties, window, 3)
    if baseline_counterparties and len(fresh) >= NEW_SHARE_MIN and now - before >= NEW_SHARE_JUMP:
        add("COUNTERPARTY_CHANGES", len(fresh), f"{now:.0%} of transactions to new counterparties, up from {before:.0%}",
            max(t[0] for t in fresh))
    return found


def pattern_activity(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """Pattern totals and per-customer findings for the current window."""
    now = now or datetime.now(timezone.utc)
    window_start = now - timedelta(days=WINDOW_DAYS)
    baseline_start = window_start - timedelta(days=BASELINE_DAYS)

    rows = (
        db.query(
            Transaction.customer_id, Transaction.transaction_date, Transaction.amount, Transaction.currency,
            Transaction.meta_counterparty, Transaction.meta_country, Transaction.transaction_type,
        )
        .filter(Transaction.transaction_date >= baseline_start, Transaction.transaction_date <= now)
        .order_by(Transaction.transaction_date)
        .all()
    )
    baseline: dict[uuid.UUID, list] = defaultdict(list)
    window: dict[uuid.UUID, list] = defaultdict(list)
    for customer_id, *txn in rows:
        (window if txn[0] >= window_start else baseline)[customer_id].append(tuple(txn))

    # History before the window, for the reactivation check (may be older than the baseline)
    history = {
        customer_id: (count, last)
        for customer_id, count, last in db.query(
            Transaction.customer_id, func.count(Transaction.id), func.max(Transaction.transaction_date)
        ).filter(Transaction.customer_id.in_(list(window)), Transaction.transaction_date < window_start).group_by(Transaction.customer_id)
    } if window else {}

    open_alerts = {
        customer_id: (count, top or 0)
        for customer_id, count, top in db.query(Alert.customer_id, func.count(Alert.id), func.max(Alert.risk_score))
        .filter(Alert.status != "RESOLVED", Alert.customer_id.in_(list(window))).group_by(Alert.customer_id)
    } if window else {}

    from app.services.rules_engine import DEFAULTS  # avoids an import cycle

    high_risk = {str(c).upper() for c in rule_config_service.get_effective_config(db, DEFAULTS, None)["HIGH_RISK_COUNTRIES"]}

    totals = {p["id"]: {"hits": 0, "customers": set()} for p in PATTERNS}
    customer_rows: list[dict[str, Any]] = []
    for customer_id, txns in window.items():
        earlier_count, last_before = history.get(customer_id, (0, None))
        for pattern, finding in _detect(baseline.get(customer_id, []), txns, earlier_count, last_before, high_risk).items():
            totals[pattern]["hits"] += finding["hits"]
            totals[pattern]["customers"].add(customer_id)
            alerts, top = open_alerts.get(customer_id, (0, 0))
            customer_rows.append({
                "customer_id": customer_id, "pattern": pattern, "hits": finding["hits"], "evidence": finding["evidence"],
                "open_alerts": alerts, "max_risk_score": top, "last_triggered_at": finding["last"],
            })

    flagged = {r["customer_id"] for r in customer_rows}
    return {
        "window_days": WINDOW_DAYS,
        "baseline_days": BASELINE_DAYS,
        "transactions_in_window": sum(len(t) for t in window.values()),
        "customers_active": len(window),
        "customers_with_baseline": sum(1 for c in window if len(baseline.get(c, [])) >= MIN_BASELINE),
        "customers_flagged": len(flagged),
        "patterns": [
            {
                **p,
                "rule_ids": [],  # kept for older clients; patterns no longer map to rules
                "hit_count": totals[p["id"]]["hits"],
                "customers": len(totals[p["id"]]["customers"]),
                "open_alerts": sum(open_alerts.get(c, (0, 0))[0] for c in totals[p["id"]]["customers"]),
            }
            for p in PATTERNS
        ],
        "customer_rows": customer_rows,
    }
