import random
import uuid
import time
from datetime import datetime, timedelta, timezone
from faker import Faker

fake = Faker()

# ISO alpha-2 codes we care about; skewed toward major banking jurisdictions
COUNTRIES = [
    "US", "GB", "DE", "FR", "IN", "CN", "JP", "AU", "CA", "BR",
    "TO", "KP", "RU", "IR", "PK", "NG", "MX", "ZA", "AE", "SG",
    "CH", "NL", "SE", "NO", "DK", "FI", "IT", "ES", "PT", "PL",
    "CZ", "HU", "RO", "BG", "HR", "GR", "TR", "KR", "TH", "MY",
    "ID", "PH", "VN", "BD", "LK", "NP", "MM", "KZ", "UZ", "UA",
]

# FATF high-risk / monitored jurisdictions (updated periodically in prod)
HIGH_RISK_COUNTRIES = ["KP", "IR", "SY", "CU", "VE", "MM", "BY", "RU", "SO", "YE"]

CURRENCIES = ["USD", "EUR", "GBP", "CHF", "AUD", "CAD", "JPY", "INR", "SGD"]
KYC_STATUSES = ["COMPLETE", "PENDING", "EXPIRED", "PARTIAL"]
CUSTOMER_TYPES = ["INDIVIDUAL", "CORPORATE", "PARTNERSHIP", "TRUST", "NGO"]
ACCOUNT_TYPES = ["SAVINGS", "CHECKING", "CREDIT", "INVESTMENT", "CRYPTO", "FX"]
ACCOUNT_STATUSES = ["ACTIVE", "CLOSED", "FROZEN", "SUSPENDED"]

TRANSACTION_TYPES = [
    "DEPOSIT", "WITHDRAWAL", "TRANSFER_IN", "TRANSFER_OUT",
    "BUY", "SELL", "PAYMENT", "FEE", "REFUND",
]

SOURCE_SYSTEMS = ["bank_mcp", "card_mcp", "crypto_mcp", "swift_mcp", "internal"]

# Replaced None with just "UNKNOWN" to avoid nulls
COUNTERPARTY_TYPES = ["INDIVIDUAL", "BANK", "CORPORATE", "EXCHANGE", "UNKNOWN"]


def _rand_date(start_year=2015, end_year=2025):
    start = datetime(start_year, 1, 1)
    span = (datetime(end_year, 12, 31) - start).days
    return start + timedelta(days=random.randint(0, span))


def _build_risk_flags(amount, country, txn_type):
    flags = []

    if amount > 10000:
        flags.append("HIGH_VALUE")
    if country in HIGH_RISK_COUNTRIES:
        flags.append("HIGH_RISK_COUNTRY")
    if txn_type in ("TRANSFER_IN", "TRANSFER_OUT") and random.random() < 0.2:
        flags.append("CROSS_BORDER")

    # rough time-of-day proxy — late night / early morning
    if random.randint(0, 23) < 6 or random.randint(0, 23) > 22:
        flags.append("UNUSUAL_TIME")

    if random.random() < 0.05:
        flags.append("SUSPICIOUS_COUNTERPARTY")
    if random.random() < 0.03:
        flags.append("UNUSUAL_PATTERN")
    if random.random() < 0.02:
        flags.append("STRUCTURING")
    if random.random() < 0.02:
        flags.append("RAPID_MOVEMENT")

    return ", ".join(flags) if flags else "NONE"


def _txn_amount():
    # log-normal-ish tiered distribution; keeps HIGH_VALUE rate around 20%
    # rather than the flat uniform which gave ~90% HIGH_VALUE hits
    r = random.random()
    if r < 0.55:
        return round(random.uniform(5.0, 500.0), 2)
    elif r < 0.80:
        return round(random.uniform(500.0, 5000.0), 2)
    elif r < 0.93:
        return round(random.uniform(5000.0, 50000.0), 2)
    else:
        return round(random.uniform(50000.0, 250000.0), 2)


def generate_customer(index):
    cid = f"CUST-{str(index).zfill(6)}"
    score = round(random.uniform(0, 100), 4)

    if score >= 66:
        level = "HIGH"
    elif score >= 33:
        level = "MEDIUM"
    else:
        level = "LOW"

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "customer_id": cid,
        "full_name": fake.name(),
        "email": fake.email(),
        "phone": fake.phone_number(),
        "date_of_birth": fake.date_of_birth(minimum_age=18, maximum_age=80).strftime("%Y-%m-%d"),
        "country": random.choice(COUNTRIES),
        "residency_country": random.choice(COUNTRIES),
        "kyc_status": random.choice(KYC_STATUSES),
        "kyc_last_review": _rand_date(2020, 2025).strftime("%Y-%m-%d"),
        "pep_flag": random.random() < 0.05,
        "sanctions_flag": random.random() < 0.02,
        "adverse_media_flag": random.random() < 0.08,
        "risk_level": level,
        "risk_score": score,
        "customer_type": random.choice(CUSTOMER_TYPES),
        "customer_metadata": f"{{'source': 'mock_data_service', 'generated_at': '{ts}'}}",
    }


def generate_accounts(customer_id, num_accounts=None):
    count = num_accounts or random.randint(1, 5)
    accounts = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i in range(1, count + 1):
        acc_id = f"ACC-{customer_id}-{str(i).zfill(2)}"
        accounts.append({
            "account_id": acc_id,
            "customer_id": customer_id,
            "account_type": random.choice(ACCOUNT_TYPES),
            "account_status": random.choice(ACCOUNT_STATUSES),
            "currency": random.choice(CURRENCIES),
            "balance": round(random.uniform(-5000, 500000), 2),
            "opened_date": _rand_date(2010, 2024).strftime("%Y-%m-%d"),
            "account_metadata": f"{{'source': 'mock_data_service', 'generated_at': '{ts}'}}",
        })
    return accounts


def generate_transactions(customer_id, account_id, num_transactions=None):
    count = num_transactions or random.randint(5, 20)
    txns = []
    for _ in range(count):
        txn_type = random.choice(TRANSACTION_TYPES)
        amount = _txn_amount()
        country_code = random.choice(COUNTRIES)

        cp_type = random.choice(COUNTERPARTY_TYPES)
        if cp_type in ("BANK", "CORPORATE", "EXCHANGE"):
            cp_name = fake.company()
        elif cp_type == "INDIVIDUAL":
            cp_name = fake.name()
        else:
            cp_name = "UNKNOWN"

        dest = random.choice(COUNTRIES) if txn_type in ("TRANSFER_OUT", "TRANSFER_IN") else country_code
        origin = random.choice(COUNTRIES) if txn_type == "TRANSFER_IN" else country_code

        # Use a short uuid to guarantee no collisions
        suffix = uuid.uuid4().hex[:8]
        txn_id = f"TXN-{account_id}-{suffix}"

        txns.append({
            "transaction_id": txn_id,
            "customer_id": customer_id,
            "account_id": account_id,
            "transaction_date": _rand_date(2020, 2025).isoformat(),
            "transaction_type": txn_type,
            "amount": amount,
            "currency": random.choice(CURRENCIES),
            "risk_flags": _build_risk_flags(amount, country_code, txn_type),
            "source_system": random.choice(SOURCE_SYSTEMS),
            "meta_counterparty": cp_name,
            "meta_counterparty_type": cp_type,
            "meta_location": fake.city(),
            "meta_country": fake.country(),
            "meta_country_code": country_code,
            "meta_destination_country": dest,
            "meta_origin_country": origin,
            "meta_source": "mock_data_service",
        })
    return txns


def generate_dataset(num_customers=5000, start_id=1):
    customers, accounts, transactions = [], [], []

    for i in range(start_id, start_id + num_customers):
        c = generate_customer(i)
        customers.append(c)

        accs = generate_accounts(c["customer_id"])
        accounts.extend(accs)

        for acc in accs:
            transactions.extend(
                generate_transactions(c["customer_id"], acc["account_id"])
            )

    return {"customers": customers, "accounts": accounts, "transactions": transactions}
