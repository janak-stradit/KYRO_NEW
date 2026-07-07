"""
Core data generator module.
Mirrors the exact schema from CUST-ML-TEST-001_ml_dataset.xlsx:
  - Customer  (16 columns)
  - Accounts  (8 columns)
  - Transactions (17 columns)
"""

import random
import uuid
import time
from datetime import datetime, timedelta, timezone
from faker import Faker

fake = Faker()

# ─────────────────────────────────────────────
# ENUM / LOOKUP CONSTANTS (derived from the sample file)
# ─────────────────────────────────────────────
COUNTRIES = [
    "US", "GB", "DE", "FR", "IN", "CN", "JP", "AU", "CA", "BR",
    "TO", "KP", "RU", "IR", "PK", "NG", "MX", "ZA", "AE", "SG",
    "CH", "NL", "SE", "NO", "DK", "FI", "IT", "ES", "PT", "PL",
    "CZ", "HU", "RO", "BG", "HR", "GR", "TR", "KR", "TH", "MY",
    "ID", "PH", "VN", "BD", "LK", "NP", "MM", "KZ", "UZ", "UA",
]
HIGH_RISK_COUNTRIES = ["KP", "IR", "SY", "CU", "VE", "MM", "BY", "RU", "SO", "YE"]
CURRENCIES = ["USD", "EUR", "GBP", "CHF", "AUD", "CAD", "JPY", "INR", "SGD"]
KYC_STATUSES = ["COMPLETE", "PENDING", "EXPIRED", "PARTIAL"]
RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
CUSTOMER_TYPES = ["INDIVIDUAL", "CORPORATE", "PARTNERSHIP", "TRUST", "NGO"]
ACCOUNT_TYPES = ["SAVINGS", "CHECKING", "CREDIT", "INVESTMENT", "CRYPTO", "FX"]
ACCOUNT_STATUSES = ["ACTIVE", "CLOSED", "FROZEN", "SUSPENDED"]
TRANSACTION_TYPES = [
    "DEPOSIT", "WITHDRAWAL", "TRANSFER_IN", "TRANSFER_OUT",
    "BUY", "SELL", "PAYMENT", "FEE", "REFUND",
]
SOURCE_SYSTEMS = ["bank_mcp", "card_mcp", "crypto_mcp", "swift_mcp", "internal"]
COUNTERPARTY_TYPES = ["INDIVIDUAL", "BANK", "CORPORATE", "EXCHANGE", "UNKNOWN", None]
RISK_FLAG_POOL = [
    "HIGH_VALUE", "CROSS_BORDER", "HIGH_RISK_COUNTRY",
    "SUSPICIOUS_COUNTERPARTY", "UNUSUAL_TIME", "UNUSUAL_PATTERN",
    "STRUCTURING", "RAPID_MOVEMENT", "SANCTIONED_ENTITY",
]


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _random_date(start_year=2015, end_year=2025) -> datetime:
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = end - start
    return start + timedelta(days=random.randint(0, delta.days))


def _risk_flags(amount: float, country: str, txn_type: str) -> str | None:
    """Generate realistic AML risk flags based on transaction attributes."""
    flags = []
    if amount > 10000:
        flags.append("HIGH_VALUE")
    if country in HIGH_RISK_COUNTRIES:
        flags.append("HIGH_RISK_COUNTRY")
    if txn_type in ("TRANSFER_IN", "TRANSFER_OUT") and random.random() < 0.2:
        flags.append("CROSS_BORDER")
    hour = random.randint(0, 23)
    if hour < 6 or hour > 22:
        flags.append("UNUSUAL_TIME")
    if random.random() < 0.05:
        flags.append("SUSPICIOUS_COUNTERPARTY")
    if random.random() < 0.03:
        flags.append("UNUSUAL_PATTERN")
    if random.random() < 0.02:
        flags.append("STRUCTURING")
    if random.random() < 0.02:
        flags.append("RAPID_MOVEMENT")
    return ", ".join(flags) if flags else None


# ─────────────────────────────────────────────
# GENERATORS
# ─────────────────────────────────────────────
def generate_customer(index: int) -> dict:
    """Generate one customer record."""
    cid = f"CUST-{str(index).zfill(6)}"
    country = random.choice(COUNTRIES)
    residency = random.choice(COUNTRIES)
    risk_score = round(random.uniform(0, 100), 4)

    if risk_score >= 75:
        risk_level = "CRITICAL"
    elif risk_score >= 50:
        risk_level = "HIGH"
    elif risk_score >= 25:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    kyc_review = _random_date(2020, 2025)
    pep = random.random() < 0.05
    sanctions = random.random() < 0.02
    adverse = random.random() < 0.08

    return {
        "customer_id": cid,
        "full_name": fake.name(),
        "email": fake.email(),
        "phone": fake.phone_number(),
        "date_of_birth": fake.date_of_birth(minimum_age=18, maximum_age=80).strftime("%Y-%m-%d"),
        "country": country,
        "residency_country": residency,
        "kyc_status": random.choice(KYC_STATUSES),
        "kyc_last_review": kyc_review.strftime("%Y-%m-%d"),
        "pep_flag": pep,
        "sanctions_flag": sanctions,
        "adverse_media_flag": adverse,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "customer_type": random.choice(CUSTOMER_TYPES),
        "customer_metadata": str({
            "source": "mock_data_service",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }),
    }


def generate_accounts(customer_id: str, num_accounts: int | None = None) -> list[dict]:
    """Generate 1-5 accounts for a customer."""
    num = num_accounts or random.randint(1, 5)
    accounts = []
    for i in range(1, num + 1):
        acc_id = f"ACC-{customer_id}-{str(i).zfill(2)}"
        opened = _random_date(2010, 2024)
        accounts.append({
            "account_id": acc_id,
            "customer_id": customer_id,
            "account_type": random.choice(ACCOUNT_TYPES),
            "account_status": random.choice(ACCOUNT_STATUSES),
            "currency": random.choice(CURRENCIES),
            "balance": round(random.uniform(-5000, 500000), 2),
            "opened_date": opened.strftime("%Y-%m-%d"),
            "account_metadata": str({
                "source": "mock_data_service",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }),
        })
    return accounts


def generate_transactions(
    customer_id: str,
    account_id: str,
    num_transactions: int | None = None,
) -> list[dict]:
    """Generate transactions for one account (default 50-200)."""
    num = num_transactions or random.randint(50, 200)
    transactions = []
    for _ in range(num):
        txn_date = _random_date(2020, 2025)
        txn_type = random.choice(TRANSACTION_TYPES)
        amount = round(random.uniform(1, 100000), 2)
        currency = random.choice(CURRENCIES)
        meta_country_code = random.choice(COUNTRIES)
        meta_destination = random.choice(COUNTRIES) if txn_type in ("TRANSFER_OUT", "TRANSFER_IN") else None
        meta_origin = random.choice(COUNTRIES) if txn_type == "TRANSFER_IN" else None
        cp_type = random.choice(COUNTERPARTY_TYPES)
        cp_name = fake.company() if cp_type in ("BANK", "CORPORATE", "EXCHANGE") else (
            fake.name() if cp_type == "INDIVIDUAL" else None
        )
        unique_suffix = int(time.time() * 1000) + random.randint(0, 999999)
        txn_id = f"TXN-{account_id}-{unique_suffix}"

        transactions.append({
            "transaction_id": txn_id,
            "customer_id": customer_id,
            "account_id": account_id,
            "transaction_date": txn_date.isoformat(),
            "transaction_type": txn_type,
            "amount": amount,
            "currency": currency,
            "risk_flags": _risk_flags(amount, meta_country_code, txn_type),
            "source_system": random.choice(SOURCE_SYSTEMS),
            "meta_counterparty": cp_name,
            "meta_counterparty_type": cp_type,
            "meta_location": fake.city() if random.random() < 0.7 else None,
            "meta_country": fake.country() if random.random() < 0.7 else None,
            "meta_country_code": meta_country_code,
            "meta_destination_country": meta_destination,
            "meta_origin_country": meta_origin,
            "meta_source": "mock_data_service",
        })
    return transactions


# ─────────────────────────────────────────────
# MAIN BATCH GENERATOR
# ─────────────────────────────────────────────
def generate_dataset(num_customers: int = 5000) -> dict:
    """
    Generate a full dataset for `num_customers` customers.
    Returns:
        {
            "customers": [...],
            "accounts": [...],
            "transactions": [...],
        }
    """
    all_customers = []
    all_accounts = []
    all_transactions = []

    for i in range(1, num_customers + 1):
        customer = generate_customer(i)
        all_customers.append(customer)

        accounts = generate_accounts(customer["customer_id"])
        all_accounts.extend(accounts)

        for acc in accounts:
            txns = generate_transactions(customer["customer_id"], acc["account_id"])
            all_transactions.extend(txns)

    return {
        "customers": all_customers,
        "accounts": all_accounts,
        "transactions": all_transactions,
    }
