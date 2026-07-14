"""
scripts/seed_app_data.py — Generates synthetic customers/accounts/transactions
into the `app` schema and scores each transaction through the same rules
engine the live API uses, so Phase 2 model training has realistic
risk_score/alert labels to learn from.

The existing generator/data_generator.py isn't reused here: its vocabulary
(transaction types, account types, kyc statuses) predates the app/ schema's
CHECK constraints and would violate them.

Usage:
    python scripts/seed_app_data.py --customers 250 --min-txns 10 --max-txns 40
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from faker import Faker

from app.database import SessionLocal
from app.models.account import Account
from app.models.customer import Customer
from app.services.rules_engine import HIGH_RISK_COUNTRIES, apply_to_transaction
from app.models.transaction import Transaction

fake = Faker()

COUNTRIES = [
    "US", "GB", "DE", "FR", "IN", "CN", "JP", "AU", "CA", "BR",
    "SG", "AE", "CH", "NL", "SE", "IT", "ES", "KR", "MX", "ZA",
] + list(HIGH_RISK_COUNTRIES)[:5]  # ensure some real high-risk-country hits

CUSTOMER_TYPES = ["INDIVIDUAL", "CORPORATE", "FUND"]
KYC_STATUSES = ["PENDING", "VERIFIED", "UNDER_REVIEW"]
ACCOUNT_TYPES = ["CHECKING", "SAVINGS", "INVESTMENT", "TRADING"]
TXN_TYPES = ["DEPOSIT", "WITHDRAWAL", "TRANSFER", "FX", "TRADE"]
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF"]
COUNTERPARTY_TYPES = ["INDIVIDUAL", "CORPORATE", "FINANCIAL_INSTITUTION"]


def random_amount() -> float:
    r = random.random()
    if r < 0.60:
        return round(random.uniform(10, 800), 2)
    if r < 0.85:
        return round(random.uniform(800, 8000), 2)
    if r < 0.96:
        return round(random.uniform(8000, 25000), 2)
    return round(random.uniform(25000, 150000), 2)


def seed(num_customers: int, min_txns: int, max_txns: int) -> None:
    db = SessionLocal()
    try:
        for i in range(num_customers):
            customer = Customer(
                full_name=fake.name(),
                email=fake.unique.email(),
                phone=fake.phone_number()[:50],
                date_of_birth=fake.date_of_birth(minimum_age=18, maximum_age=85),
                country=random.choice(COUNTRIES),
                residency_country=random.choice(COUNTRIES),
                kyc_status=random.choice(KYC_STATUSES),
                pep_flag=random.random() < 0.03,
                sanctions_flag=random.random() < 0.015,
                adverse_media_flag=random.random() < 0.05,
                customer_type=random.choice(CUSTOMER_TYPES),
            )
            db.add(customer)
            db.flush()

            accounts = []
            for _ in range(random.randint(1, 3)):
                account = Account(
                    customer_id=customer.id,
                    account_type=random.choice(ACCOUNT_TYPES),
                    currency=random.choice(CURRENCIES),
                    balance=round(random.uniform(100, 200_000), 2),
                    opened_date=fake.date_between(start_date="-5y", end_date="-30d"),
                )
                db.add(account)
                db.flush()
                accounts.append(account)

            num_txns = random.randint(min_txns, max_txns)
            base = datetime.now(timezone.utc) - timedelta(days=120)
            # Ascending dates so rules-engine velocity/history queries see a
            # causally consistent past when scoring each transaction.
            dates = sorted(base + timedelta(seconds=random.randint(0, 120 * 86400)) for _ in range(num_txns))

            for txn_date in dates:
                account = random.choice(accounts)
                country = random.choice(COUNTRIES)
                txn = Transaction(
                    customer_id=customer.id,
                    account_id=account.id,
                    transaction_date=txn_date,
                    transaction_type=random.choice(TXN_TYPES),
                    amount=random_amount(),
                    currency=account.currency,
                    meta_counterparty=fake.company() if random.random() < 0.8 else None,
                    meta_counterparty_type=random.choice(COUNTERPARTY_TYPES),
                    meta_country=country,
                    meta_destination_country=random.choice(COUNTRIES),
                    meta_origin_country=country,
                    meta_source="seed_script",
                    source_system="seed_script",
                )
                db.add(txn)
                db.flush()
                apply_to_transaction(db, txn, customer)

            db.commit()
            if (i + 1) % 25 == 0:
                print(f"seeded {i + 1}/{num_customers} customers")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--customers", type=int, default=250)
    parser.add_argument("--min-txns", type=int, default=10)
    parser.add_argument("--max-txns", type=int, default=40)
    args = parser.parse_args()
    seed(args.customers, args.min_txns, args.max_txns)
    print("done")
