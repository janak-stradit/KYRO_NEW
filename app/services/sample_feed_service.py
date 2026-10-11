"""
services/sample_feed_service.py — Synthetic CSV files for the Data Feeds page:
one each for customers, accounts and transactions, in the shape a client
would send them.

The three files belong together: accounts refer to the customers by email and
transactions refer to the accounts by reference. They are generated from a
seed, so asking for each file with the same seed and size gives a matching
set. The seed is part of every email and account reference, so a new set never
collides with one loaded earlier.
"""
from __future__ import annotations

import csv
import io
import random
from datetime import date, datetime, timedelta, timezone

from app.services.feed_service import MAX_ROWS
from app.services.live_feed_service import _COUNTERPARTIES, _COUNTRIES, _TXN_TYPES, _amount, _country

MAX_CUSTOMERS = 2000
_TXNS_PER_ACCOUNT = 10
_HISTORY_DAYS = 90

_FIRST = ["James", "Maria", "Wei", "Aisha", "Lucas", "Priya", "Omar", "Sofia", "Kenji", "Elena", "David", "Fatima", "Noah", "Ingrid",
          "Mateo", "Hannah", "Arjun", "Chloe", "Tariq", "Yuki", "Daniel", "Amara", "Viktor", "Leila", "Samuel", "Nadia", "Hugo", "Mei"]
_LAST = ["Smith", "Garcia", "Chen", "Khan", "Silva", "Patel", "Hassan", "Rossi", "Tanaka", "Ivanova", "Cohen", "Ali", "Jensen", "Berg",
         "Lopez", "Schmidt", "Mehta", "Dubois", "Aziz", "Sato", "Novak", "Okafor", "Petrov", "Haddad", "Reyes", "Lindqvist", "Moreau", "Wong"]
_COMPANY = ["Trading", "Holdings", "Logistics", "Capital", "Exports", "Partners", "Industries", "Ventures", "Shipping", "Advisors"]
_ACCOUNT_TYPES = ["Checking", "Savings", "Investment", "Trading"]
_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF"]

HEADERS = {
    "CUSTOMERS": ["Full Name", "Email", "Phone", "Date of Birth", "Country", "Country of Residence", "Customer Type", "PEP"],
    "ACCOUNTS": ["Account Reference", "Customer Email", "Account Type", "Currency", "Balance", "Opened Date"],
    "TRANSACTIONS": ["Account Reference", "Transaction Date", "Transaction Type", "Amount", "Currency", "Counterparty", "Counterparty Country"],
}


def _dataset(seed: int, customers: int) -> dict[str, list[list]]:
    """All three files' rows. Everything is drawn from one seeded generator, so
    the same seed and size always give the same rows."""
    rng = random.Random(seed)
    tag = f"{seed:06d}"
    today = date.today()
    # Whole seconds at midnight UTC, so the dates do not depend on when the file is asked for
    end = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)

    customer_rows, account_rows, accounts = [], [], []
    for i in range(1, customers + 1):
        first, last = rng.choice(_FIRST), rng.choice(_LAST)
        kind = rng.choices(["Individual", "Corporate", "Fund"], weights=[70, 22, 8])[0]
        name = f"{first} {last}" if kind == "Individual" else f"{last} {rng.choice(_COMPANY)} {'Fund' if kind == 'Fund' else 'Ltd'}"
        email = f"{first}.{last}.{tag}.{i}@sample.kyro.example".lower()
        country = rng.choice(_COUNTRIES)
        born = today - timedelta(days=rng.randint(19 * 365, 80 * 365))
        customer_rows.append([
            name, email, f"+{rng.randint(1, 98)} {rng.randint(200, 999)} {rng.randint(1000000, 9999999)}", born.isoformat(),
            country, country if rng.random() < 0.85 else rng.choice(_COUNTRIES), kind, "Yes" if rng.random() < 0.03 else "No",
        ])
        for _ in range(rng.randint(1, 3)):
            ref = f"SF-{tag}-{len(accounts) + 1:05d}"
            currency = rng.choice(_CURRENCIES)
            opened = today - timedelta(days=rng.randint(_HISTORY_DAYS + 30, 5 * 365))
            account_rows.append([ref, email, rng.choice(_ACCOUNT_TYPES), currency, f"{rng.uniform(100, 200_000):.2f}", opened.isoformat()])
            accounts.append((ref, currency, country))

    transaction_rows = []
    for _ in range(min(MAX_ROWS, len(accounts) * _TXNS_PER_ACCOUNT)):
        ref, currency, home = rng.choice(accounts)
        when = end - timedelta(seconds=rng.randint(1, _HISTORY_DAYS * 86400))
        transaction_rows.append([
            ref, when.strftime("%Y-%m-%dT%H:%M:%S"), rng.choice(_TXN_TYPES).title(), f"{_amount(rng):.2f}", currency,
            rng.choice(_COUNTERPARTIES) if rng.random() < 0.85 else "", _country(home, rng),
        ])
    # Oldest first, as a ledger extract would be, so the rules see a consistent history
    transaction_rows.sort(key=lambda row: row[1])
    return {"CUSTOMERS": customer_rows, "ACCOUNTS": account_rows, "TRANSACTIONS": transaction_rows}


def generate(target: str, *, seed: int, customers: int) -> tuple[str, bytes]:
    """(file name, CSV bytes) for one of the three files of the set."""
    rows = _dataset(seed, max(1, min(MAX_CUSTOMERS, customers)))[target]
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(HEADERS[target])
    writer.writerows(rows)
    return f"sample_{target.lower()}_{seed:06d}.csv", out.getvalue().encode("utf-8")
