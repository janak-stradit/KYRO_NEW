"""
scripts/sample_profiles.py — Synthetic onboarding details for sample customers
and accounts: address, occupation or industry, source of funds, expected
activity, relationship manager, account number, product and purpose.

Everything written here is made up and is marked `"sample_data": true`.
Values are derived from the record's id, so running it again changes nothing.

Usage (fills in existing records that have no profile yet):
    python scripts/sample_profiles.py
    python scripts/sample_profiles.py --refresh    (regenerate the sample profiles written earlier)
"""
from __future__ import annotations

import os
import random
import sys
import uuid
from datetime import date, timedelta
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from faker import Faker

OCCUPATIONS = ["Software engineer", "Physician", "Teacher", "Accountant", "Retired", "Restaurant owner", "Lawyer", "Civil engineer",
               "Real estate agent", "Consultant", "Nurse", "Import/export trader", "Architect", "Sales manager", "Self-employed"]
INDUSTRIES = ["Wholesale trade", "Software", "Construction", "Commodities trading", "Real estate", "Manufacturing", "Logistics",
              "Hospitality", "Professional services", "Precious metals dealing", "Money services", "Retail"]
FUND_TYPES = ["Hedge fund", "Private equity fund", "Family office", "Pension fund", "Venture capital fund", "Real estate fund"]
SOURCES_INDIVIDUAL = ["Salary", "Business income", "Pension", "Investments", "Inheritance", "Property sale", "Savings"]
SOURCES_ENTITY = ["Operating revenue", "Investor subscriptions", "Shareholder capital", "Asset sales", "Trading profits", "Loan proceeds"]
PURPOSES = ["Day-to-day banking", "Savings", "Investment", "Trade settlement", "Payroll", "Treasury management", "International payments"]
CHANNELS = ["Branch", "Online", "Relationship manager", "Introducer"]
MANAGERS = ["A. Whitfield", "R. Nakamura", "S. Okafor", "L. Fernandes", "M. Lindqvist", "T. Haddad"]
ID_TYPES = ["Passport", "National ID card", "Driving licence"]
PRODUCTS = {
    "CHECKING": ["Current account", "Premium current account"],
    "SAVINGS": ["Instant-access savings", "Fixed-term deposit"],
    "INVESTMENT": ["Managed portfolio", "Custody account"],
    "TRADING": ["Brokerage account", "Margin trading account"],
}
ACCOUNT_PURPOSES = {
    "CHECKING": ["Day-to-day payments", "Payroll and supplier payments", "Receiving client payments"],
    "SAVINGS": ["Savings", "Cash reserve", "Tax reserve"],
    "INVESTMENT": ["Long-term investment", "Custody of securities"],
    "TRADING": ["Securities trading", "FX and derivatives trading"],
}
TURNOVER_BANDS = {"INDIVIDUAL": (2_000, 25_000), "CORPORATE": (20_000, 400_000), "FUND": (100_000, 1_500_000)}
BRANCHES = ["London City", "Frankfurt", "Zurich", "Singapore", "New York", "Dubai DIFC"]


def _rng(record_id: uuid.UUID) -> tuple[random.Random, Faker]:
    seed = record_id.int % (2**32)
    fake = Faker()
    fake.seed_instance(seed)
    return random.Random(seed), fake


def customer_profile(customer_id: uuid.UUID, customer_type: str | None, country: str | None, currency: str = "USD") -> dict[str, Any]:
    """A made-up onboarding profile for one customer."""
    rng, fake = _rng(customer_id)
    kind = customer_type or "INDIVIDUAL"
    low, high = TURNOVER_BANDS.get(kind, TURNOVER_BANDS["INDIVIDUAL"])
    onboarded_days = rng.randint(200, 2400)
    profile: dict[str, Any] = {
        "sample_data": True,
        "address": {"line1": fake.street_address(), "city": fake.city(), "postal_code": fake.postcode(), "country": country},
        "onboarded_on": (date.today() - timedelta(days=onboarded_days)).isoformat(),
        "onboarding_channel": rng.choice(CHANNELS),
        "relationship_manager": rng.choice(MANAGERS),
        "purpose_of_relationship": rng.choice(PURPOSES),
        "expected_monthly_turnover": {"amount": round(rng.uniform(low, high), -2), "currency": currency},
        "tax_residency": country,
    }
    if kind == "INDIVIDUAL":
        profile.update({
            "occupation": rng.choice(OCCUPATIONS),
            "employer": fake.company() if rng.random() < 0.7 else None,
            "source_of_funds": rng.choice(SOURCES_INDIVIDUAL),
            "source_of_wealth": rng.choice(SOURCES_INDIVIDUAL),
            "id_document": {"type": rng.choice(ID_TYPES), "number_ending": f"{rng.randint(0, 9999):04d}",
                            "expires_on": (date.today() + timedelta(days=rng.randint(-200, 2500))).isoformat()},
        })
    else:
        profile.update({
            "industry": rng.choice(FUND_TYPES if kind == "FUND" else INDUSTRIES),
            "registration_number": f"{rng.choice('ABCDEFGH')}{rng.randint(1_000_000, 9_999_999)}",
            # a company exists before it becomes a customer
            "incorporated_on": (date.today() - timedelta(days=onboarded_days + rng.randint(180, 7000))).isoformat(),
            "source_of_funds": rng.choice(SOURCES_ENTITY),
            "source_of_wealth": rng.choice(SOURCES_ENTITY),
            "employees": rng.choice([3, 8, 15, 40, 120, 600]) if kind == "CORPORATE" else None,
        })
    return profile


def account_profile(account_id: uuid.UUID, account_type: str | None) -> dict[str, Any]:
    """Made-up account details: a number, the product, what the account is for."""
    rng, _ = _rng(account_id)
    kind = account_type if account_type in PRODUCTS else "CHECKING"
    return {
        "sample_data": True,
        "account_number": f"{rng.randint(10_000_000, 99_999_999)}",
        "product": rng.choice(PRODUCTS[kind]),
        "purpose": rng.choice(ACCOUNT_PURPOSES[kind]),
        "opened_channel": rng.choice(CHANNELS),
        "branch": rng.choice(BRANCHES),
    }


def enrich_existing(refresh: bool = False) -> dict[str, int]:
    """
    Give a profile to every customer and account that has none; existing
    metadata keys are kept. With `refresh`, profiles this script wrote earlier
    (marked sample_data) are generated again.
    """
    from app.database import SessionLocal
    from app.models.account import Account
    from app.models.customer import Customer

    db = SessionLocal()
    try:
        customers = accounts = 0
        first_currency = {}
        for account in db.query(Account).order_by(Account.created_at):
            first_currency.setdefault(account.customer_id, account.currency)
            existing = account.account_metadata or {}
            if not existing.get("product") or (refresh and existing.get("sample_data")):
                fresh = account_profile(account.id, account.account_type)
                account.account_metadata = {**existing, **fresh} if existing.get("sample_data") else {**fresh, **existing}
                accounts += 1
        for customer in db.query(Customer):
            existing = customer.customer_metadata or {}
            if not existing.get("source_of_funds") or (refresh and existing.get("sample_data")):
                profile = customer_profile(customer.id, customer.customer_type, customer.country, first_currency.get(customer.id, "USD"))
                customer.customer_metadata = {**existing, **profile} if existing.get("sample_data") else {**profile, **existing}
                customers += 1
        db.commit()
        return {"customers": customers, "accounts": accounts}
    finally:
        db.close()


if __name__ == "__main__":
    print(enrich_existing(refresh="--refresh" in sys.argv))
