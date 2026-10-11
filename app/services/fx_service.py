"""
services/fx_service.py — Exchange rates into the base currency, so rules compare
amounts in one currency (rules engine R1).

Rates come from the European Central Bank's daily reference rates (quoted per
euro, published on working days around 16:00 CET) and are stored converted to the
base currency (settings.base_currency). A transaction uses the latest rate on or
before its date; a rate more than STALE_AFTER_DAYS old is still used but marked
stale on the evaluation. With no rate at all the amount stays unconverted and the
rules compare the original amount (marked fx_missing), which over-alerts rather
than missing anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.fx_rate import FxRate
from app.models.transaction import Transaction

STALE_AFTER_DAYS = 5


@dataclass
class Conversion:
    amount_base: Decimal | None
    rate: Decimal | None
    rate_date: date | None
    stale: bool

    @property
    def missing(self) -> bool:
        return self.rate is None


def base_currency() -> str:
    return get_settings().base_currency.upper()


def convert(db: Session, amount: float | Decimal, currency: str | None, on: date) -> Conversion:
    """`amount` in `currency` on date `on`, in the base currency."""
    code = (currency or base_currency()).upper()
    amount = Decimal(str(amount))
    if code == base_currency():
        return Conversion(amount, Decimal(1), on, False)
    row = (
        db.query(FxRate.rate_to_base, FxRate.rate_date)
        .filter(FxRate.currency == code, FxRate.rate_date <= on)
        .order_by(FxRate.rate_date.desc())
        .first()
    )
    if row is None:
        return Conversion(None, None, None, False)
    rate = Decimal(str(row.rate_to_base))
    return Conversion((amount * rate).quantize(Decimal("0.01")), rate, row.rate_date, (on - row.rate_date).days > STALE_AFTER_DAYS)


def apply(db: Session, txn: Transaction) -> Conversion:
    """Fill amount_base / fx_rate on a transaction and return the conversion used."""
    conversion = convert(db, txn.amount, txn.currency, txn.transaction_date.date())
    txn.amount_base = conversion.amount_base
    txn.fx_rate = conversion.rate
    return conversion


# ── Loading rates ────────────────────────────────────────────────────────

def parse_ecb(xml_bytes: bytes, base: str) -> list[dict]:
    """ECB daily XML (rates per 1 EUR) → rows of {rate_date, currency, rate_to_base}."""
    rows: list[dict] = []
    for day in ET.fromstring(xml_bytes).iter():
        if day.tag.endswith("Cube") and day.get("time"):
            per_eur = {"EUR": Decimal(1)}
            per_eur.update({c.get("currency"): Decimal(c.get("rate")) for c in day if c.get("currency") and c.get("rate")})
            if base not in per_eur:
                raise ValueError(f"The ECB file has no rate for the base currency {base}")
            rate_date = date.fromisoformat(day.get("time"))
            # 1 unit of X = (per_eur[base] / per_eur[X]) units of base
            rows += [
                {"rate_date": rate_date, "currency": code, "rate_to_base": (per_eur[base] / value).quantize(Decimal("1e-10"))}
                for code, value in per_eur.items()
                if code != base
            ]
    return rows


def store(db: Session, rows: list[dict], source: str = "ECB") -> int:
    for row in rows:
        stmt = pg_insert(FxRate).values(**row, source=source)
        db.execute(stmt.on_conflict_do_update(
            constraint="uq_fx_rate_date_currency", set_={"rate_to_base": row["rate_to_base"], "source": source},
        ))
    db.commit()
    return len(rows)


def refresh_from_ecb(db: Session) -> dict:
    settings = get_settings()
    response = httpx.get(settings.fx_rates_url, timeout=30, follow_redirects=True)
    response.raise_for_status()
    rows = parse_ecb(response.content, base_currency())
    return {"stored": store(db, rows), "rate_date": max((r["rate_date"] for r in rows), default=None)}


def backfill_amount_base(db: Session, *, batch_size: int = 1000) -> int:
    """Convert transactions that have no base amount yet, where a rate is now known. Safe to repeat."""
    done = 0
    last_id = None
    while True:
        query = db.query(Transaction).filter(Transaction.amount_base.is_(None)).order_by(Transaction.id)
        if last_id is not None:
            query = query.filter(Transaction.id > last_id)
        batch = query.limit(batch_size).all()
        if not batch:
            break
        for txn in batch:
            if apply(db, txn).amount_base is not None:
                done += 1
        last_id = batch[-1].id
        db.commit()
    return done


def status(db: Session) -> dict:
    latest = db.query(func.max(FxRate.rate_date)).scalar()
    return {
        "base_currency": base_currency(),
        "latest_rate_date": latest.isoformat() if latest else None,
        "currencies": db.query(func.count(func.distinct(FxRate.currency))).scalar() or 0,
        "stale": latest is None or (datetime.now(timezone.utc).date() - latest).days > STALE_AFTER_DAYS,
        "transactions_without_base_amount": db.query(func.count(Transaction.id)).filter(Transaction.amount_base.is_(None)).scalar() or 0,
    }
