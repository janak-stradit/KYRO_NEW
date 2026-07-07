"""
Generate 200 customers — clean, validated Excel output.

Guarantees:
  ✓ Zero null / None values in any cell
  ✓ Zero duplicate IDs (customer_id, account_id, transaction_id)
  ✓ Referential integrity (all FK links valid)
  ✓ Risk score / level consistency
  ✓ 16 customer cols | 8 account cols | 17 transaction cols
  ✓ 1-5 accounts per customer, 50-200 transactions per account

Run:
    source venv/bin/activate
    python3 generate_200_clean.py
"""

import os
import sys
import random
import uuid
import time
from datetime import datetime, timedelta, timezone
from faker import Faker
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

fake = Faker()
random.seed(42)      # reproducible output

# ── Config ────────────────────────────────────────────────────
NUM_CUSTOMERS = 200
OUTPUT_DIR    = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Lookup tables ─────────────────────────────────────────────
COUNTRIES = [
    "US","GB","DE","FR","IN","CN","JP","AU","CA","BR",
    "TO","KP","RU","IR","PK","NG","MX","ZA","AE","SG",
    "CH","NL","SE","NO","DK","FI","IT","ES","PT","PL",
]
HIGH_RISK_COUNTRIES = ["KP","IR","SY","CU","VE","MM","BY","RU","SO","YE"]
CURRENCIES          = ["USD","EUR","GBP","CHF","AUD","CAD","JPY","INR","SGD"]
KYC_STATUSES        = ["COMPLETE","PENDING","EXPIRED","PARTIAL"]
CUSTOMER_TYPES      = ["INDIVIDUAL","CORPORATE","PARTNERSHIP","TRUST","NGO"]
ACCOUNT_TYPES       = ["SAVINGS","CHECKING","CREDIT","INVESTMENT","CRYPTO","FX"]
ACCOUNT_STATUSES    = ["ACTIVE","CLOSED","FROZEN","SUSPENDED"]
TRANSACTION_TYPES   = [
    "DEPOSIT","WITHDRAWAL","TRANSFER_IN","TRANSFER_OUT",
    "BUY","SELL","PAYMENT","FEE","REFUND",
]
SOURCE_SYSTEMS      = ["bank_mcp","card_mcp","crypto_mcp","swift_mcp","internal"]
COUNTERPARTY_TYPES  = ["INDIVIDUAL","BANK","CORPORATE","EXCHANGE","UNKNOWN"]
RISK_FLAG_POOL      = [
    "HIGH_VALUE","CROSS_BORDER","HIGH_RISK_COUNTRY",
    "SUSPICIOUS_COUNTERPARTY","UNUSUAL_TIME","UNUSUAL_PATTERN",
    "STRUCTURING","RAPID_MOVEMENT","SANCTIONED_ENTITY",
]

# ── Column definitions ────────────────────────────────────────
CUSTOMER_COLS = [
    "customer_id","full_name","email","phone","date_of_birth",
    "country","residency_country","kyc_status","kyc_last_review",
    "pep_flag","sanctions_flag","adverse_media_flag","risk_level",
    "risk_score","customer_type","customer_metadata",
]
ACCOUNT_COLS = [
    "account_id","customer_id","account_type","account_status",
    "currency","balance","opened_date","account_metadata",
]
TRANSACTION_COLS = [
    "transaction_id","customer_id","account_id","transaction_date",
    "transaction_type","amount","currency","risk_flags",
    "source_system","meta_counterparty","meta_counterparty_type",
    "meta_location","meta_country","meta_country_code",
    "meta_destination_country","meta_origin_country","meta_source",
]
DATA_DICT = [
    ("Customer","customer_id","String","object"),
    ("Customer","full_name","String","object"),
    ("Customer","email","String","object"),
    ("Customer","phone","String","object"),
    ("Customer","date_of_birth","String","object"),
    ("Customer","country","String","object"),
    ("Customer","residency_country","String","object"),
    ("Customer","kyc_status","String","object"),
    ("Customer","kyc_last_review","String","object"),
    ("Customer","pep_flag","Boolean","bool"),
    ("Customer","sanctions_flag","Boolean","bool"),
    ("Customer","adverse_media_flag","Boolean","bool"),
    ("Customer","risk_level","String","object"),
    ("Customer","risk_score","Float","float64"),
    ("Customer","customer_type","String","object"),
    ("Customer","customer_metadata","String","object"),
    ("Accounts","account_id","String","object"),
    ("Accounts","customer_id","String","object"),
    ("Accounts","account_type","String","object"),
    ("Accounts","account_status","String","object"),
    ("Accounts","currency","String","object"),
    ("Accounts","balance","Float","float64"),
    ("Accounts","opened_date","String","object"),
    ("Accounts","account_metadata","String","object"),
    ("Transactions","transaction_id","String","object"),
    ("Transactions","customer_id","String","object"),
    ("Transactions","account_id","String","object"),
    ("Transactions","transaction_date","String","object"),
    ("Transactions","transaction_type","String","object"),
    ("Transactions","amount","Float","float64"),
    ("Transactions","currency","String","object"),
    ("Transactions","risk_flags","String","object"),
    ("Transactions","source_system","String","object"),
    ("Transactions","meta_counterparty","String","object"),
    ("Transactions","meta_counterparty_type","String","object"),
    ("Transactions","meta_location","String","object"),
    ("Transactions","meta_country","String","object"),
    ("Transactions","meta_country_code","String","object"),
    ("Transactions","meta_destination_country","String","object"),
    ("Transactions","meta_origin_country","String","object"),
    ("Transactions","meta_source","String","object"),
]

# ── Helpers ───────────────────────────────────────────────────
def _rand_date(start_year=2015, end_year=2025) -> str:
    start = datetime(start_year, 1, 1)
    delta = datetime(end_year, 12, 31) - start
    return (start + timedelta(days=random.randint(0, delta.days))).strftime("%Y-%m-%d")


def _risk_flags(amount: float, country: str, txn_type: str) -> str:
    """Always returns a non-null string (at least 'NONE')."""
    flags = []
    if amount > 10000:
        flags.append("HIGH_VALUE")
    if country in HIGH_RISK_COUNTRIES:
        flags.append("HIGH_RISK_COUNTRY")
    if txn_type in ("TRANSFER_IN", "TRANSFER_OUT") and random.random() < 0.25:
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
    return ", ".join(flags) if flags else "NONE"


def _metadata(entity: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{{'entity': '{entity}', 'source': 'mock_data_service', 'generated_at': '{ts}Z'}}"


# ── Generators ────────────────────────────────────────────────
def generate_customer(index: int) -> dict:
    cid        = f"CUST-{str(index).zfill(6)}"
    risk_score = round(random.uniform(0, 100), 4)
    if risk_score >= 75:
        risk_level = "CRITICAL"
    elif risk_score >= 50:
        risk_level = "HIGH"
    elif risk_score >= 25:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "customer_id":       cid,
        "full_name":         fake.name(),
        "email":             fake.unique.email(),          # unique emails
        "phone":             fake.phone_number(),
        "date_of_birth":     fake.date_of_birth(minimum_age=18, maximum_age=80).strftime("%Y-%m-%d"),
        "country":           random.choice(COUNTRIES),
        "residency_country": random.choice(COUNTRIES),
        "kyc_status":        random.choice(KYC_STATUSES),
        "kyc_last_review":   _rand_date(2020, 2025),
        "pep_flag":          random.random() < 0.05,
        "sanctions_flag":    random.random() < 0.02,
        "adverse_media_flag":random.random() < 0.08,
        "risk_level":        risk_level,
        "risk_score":        risk_score,
        "customer_type":     random.choice(CUSTOMER_TYPES),
        "customer_metadata": _metadata("customer"),
    }


def generate_accounts(customer_id: str) -> list[dict]:
    num = random.randint(1, 5)
    accounts = []
    for i in range(1, num + 1):
        accounts.append({
            "account_id":       f"ACC-{customer_id}-{str(i).zfill(2)}",
            "customer_id":      customer_id,
            "account_type":     random.choice(ACCOUNT_TYPES),
            "account_status":   random.choice(ACCOUNT_STATUSES),
            "currency":         random.choice(CURRENCIES),
            "balance":          round(random.uniform(100.0, 500000.0), 2),  # no negative balance
            "opened_date":      _rand_date(2010, 2024),
            "account_metadata": _metadata("account"),
        })
    return accounts


def generate_transactions(customer_id: str, account_id: str) -> list[dict]:
    num = random.randint(50, 200)
    seen_ids = set()
    transactions = []
    for _ in range(num):
        # Guaranteed unique transaction_id via uuid4
        txn_id = f"TXN-{account_id}-{uuid.uuid4().hex[:12].upper()}"
        while txn_id in seen_ids:
            txn_id = f"TXN-{account_id}-{uuid.uuid4().hex[:12].upper()}"
        seen_ids.add(txn_id)

        txn_type   = random.choice(TRANSACTION_TYPES)

        # Realistic tiered transaction amount distribution
        # Mirrors actual global banking behaviour:
        #   55% — micro/retail  :  $5   – $500      (everyday payments, fees)
        #   25% — medium        :  $500 – $5,000    (payroll, bills, transfers)
        #   13% — large         :  $5K  – $50,000   (business, wire transfers)
        #    7% — very large    :  $50K – $250,000  (institutional, suspicious)
        # → ~15-20% exceed $10K (CTR threshold) — realistic HIGH_VALUE flag rate
        tier = random.random()
        if tier < 0.55:
            amount = round(random.uniform(5.0, 500.0), 2)
        elif tier < 0.80:
            amount = round(random.uniform(500.0, 5000.0), 2)
        elif tier < 0.93:
            amount = round(random.uniform(5000.0, 50000.0), 2)
        else:
            amount = round(random.uniform(50000.0, 250000.0), 2)

        country_code = random.choice(COUNTRIES)
        cp_type    = random.choice(COUNTERPARTY_TYPES)

        # No null counterparty — always fill based on type
        if cp_type in ("BANK", "CORPORATE", "EXCHANGE"):
            cp_name = fake.company()
        elif cp_type == "INDIVIDUAL":
            cp_name = fake.name()
        else:  # UNKNOWN
            cp_name = "UNKNOWN ENTITY"

        # No null destination/origin — use "N/A" for non-transfer types
        if txn_type in ("TRANSFER_OUT", "TRANSFER_IN"):
            dest_country   = random.choice(COUNTRIES)
        else:
            dest_country   = "N/A"

        if txn_type == "TRANSFER_IN":
            origin_country = random.choice(COUNTRIES)
        else:
            origin_country = "N/A"

        transactions.append({
            "transaction_id":        txn_id,
            "customer_id":           customer_id,
            "account_id":            account_id,
            "transaction_date":      _rand_date(2020, 2025),
            "transaction_type":      txn_type,
            "amount":                amount,
            "currency":              random.choice(CURRENCIES),
            "risk_flags":            _risk_flags(amount, country_code, txn_type),
            "source_system":         random.choice(SOURCE_SYSTEMS),
            "meta_counterparty":     cp_name,
            "meta_counterparty_type":cp_type,
            "meta_location":         fake.city(),          # always filled
            "meta_country":          fake.country(),       # always filled
            "meta_country_code":     country_code,
            "meta_destination_country": dest_country,
            "meta_origin_country":      origin_country,
            "meta_source":           "mock_data_service",
        })
    return transactions


def generate_dataset(n: int) -> dict:
    customers, accounts, transactions = [], [], []
    for i in range(1, n + 1):
        c = generate_customer(i)
        customers.append(c)
        accs = generate_accounts(c["customer_id"])
        accounts.extend(accs)
        for acc in accs:
            transactions.extend(generate_transactions(c["customer_id"], acc["account_id"]))
    return {"customers": customers, "accounts": accounts, "transactions": transactions}


# ── Excel styling ─────────────────────────────────────────────
HEADER_FILL   = PatternFill("solid", fgColor="1F3864")
HEADER_FONT   = Font(bold=True, color="FFFFFF", size=10)
HEADER_ALIGN  = Alignment(horizontal="center", vertical="center", wrap_text=True)
THIN          = Side(style="thin", color="B0B0B0")
HEADER_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _style_header(ws, num_cols: int):
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill   = HEADER_FILL
        cell.font   = HEADER_FONT
        cell.alignment = HEADER_ALIGN
        cell.border = HEADER_BORDER


def _auto_width(ws, max_width=50):
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[col_letter].width = min(max_len + 4, max_width)


def _write_sheet(wb, name, columns, rows):
    ws = wb.create_sheet(name)
    ws.append(columns)
    _style_header(ws, len(columns))
    for row in rows:
        ws.append([row.get(col) for col in columns])
    _auto_width(ws)
    ws.freeze_panes = "A2"
    return ws


# ── Validate dataset ──────────────────────────────────────────
def validate(dataset: dict) -> list[str]:
    errors = []
    customers    = dataset["customers"]
    accounts     = dataset["accounts"]
    transactions = dataset["transactions"]

    # Duplicate IDs
    cids  = [c["customer_id"] for c in customers]
    aids  = [a["account_id"]  for a in accounts]
    tids  = [t["transaction_id"] for t in transactions]
    if len(cids) != len(set(cids)):
        errors.append(f"Duplicate customer_ids: {len(cids)-len(set(cids))}")
    if len(aids) != len(set(aids)):
        errors.append(f"Duplicate account_ids: {len(aids)-len(set(aids))}")
    if len(tids) != len(set(tids)):
        errors.append(f"Duplicate transaction_ids: {len(tids)-len(set(tids))}")

    # Null check
    for i, c in enumerate(customers):
        for k, v in c.items():
            if v is None or v == "":
                errors.append(f"Customer[{i}].{k} is null/empty")

    for i, a in enumerate(accounts):
        for k, v in a.items():
            if v is None or v == "":
                errors.append(f"Account[{i}].{k} is null/empty")

    null_txn_fields = 0
    for t in transactions:
        for k, v in t.items():
            if v is None or v == "":
                null_txn_fields += 1
    if null_txn_fields:
        errors.append(f"{null_txn_fields} null/empty fields found in transactions")

    # Referential integrity
    valid_cids = set(cids)
    valid_aids = set(aids)
    bad_acc_fk = sum(1 for a in accounts     if a["customer_id"] not in valid_cids)
    bad_txn_ck = sum(1 for t in transactions if t["customer_id"] not in valid_cids)
    bad_txn_ak = sum(1 for t in transactions if t["account_id"]  not in valid_aids)
    if bad_acc_fk: errors.append(f"{bad_acc_fk} accounts have invalid customer_id FK")
    if bad_txn_ck: errors.append(f"{bad_txn_ck} transactions have invalid customer_id FK")
    if bad_txn_ak: errors.append(f"{bad_txn_ak} transactions have invalid account_id FK")

    # Risk consistency
    bad_risk = sum(1 for c in customers if not (
        (c["risk_score"] >= 75 and c["risk_level"] == "CRITICAL") or
        (50 <= c["risk_score"] < 75 and c["risk_level"] == "HIGH")  or
        (25 <= c["risk_score"] < 50 and c["risk_level"] == "MEDIUM") or
        (c["risk_score"] < 25 and c["risk_level"] == "LOW")
    ))
    if bad_risk: errors.append(f"{bad_risk} customers with mismatched risk_score/risk_level")

    return errors


# ── MAIN ──────────────────────────────────────────────────────
print("=" * 65)
print("  KYRO AML — 200 Customer Clean Dataset Generator")
print("=" * 65)
print(f"\n▶  Generating {NUM_CUSTOMERS} customers ...")

t0 = time.time()
dataset = generate_dataset(NUM_CUSTOMERS)
gen_time = time.time() - t0

customers    = dataset["customers"]
accounts     = dataset["accounts"]
transactions = dataset["transactions"]

print(f"\n✅  Generation complete in {gen_time:.1f}s")
print(f"   Customers    : {len(customers):>8,}")
print(f"   Accounts     : {len(accounts):>8,}")
print(f"   Transactions : {len(transactions):>8,}")

print(f"\n🔍  Running full data quality checks ...")
errors = validate(dataset)
if errors:
    print("\n❌  Validation FAILED:")
    for e in errors:
        print(f"   • {e}")
    sys.exit(1)

multi_acc = sum(1 for cid in {a["customer_id"] for a in accounts}
                if sum(1 for a in accounts if a["customer_id"] == cid) > 1)
print(f"   ✓ No duplicate customer_ids")
print(f"   ✓ No duplicate account_ids")
print(f"   ✓ No duplicate transaction_ids")
print(f"   ✓ Zero null / empty values across all sheets")
print(f"   ✓ Referential integrity OK (all FK links valid)")
print(f"   ✓ Risk score / level consistency OK")
print(f"   ✓ Multi-account customers : {multi_acc} ({multi_acc/NUM_CUSTOMERS*100:.1f}%)")
print(f"\n✅  All data quality checks PASSED")

# ── Write Excel ───────────────────────────────────────────────
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
filename  = f"aml_200_customers_realistic_{timestamp}.xlsx"
filepath  = os.path.join(OUTPUT_DIR, filename)

print(f"\n📊  Writing Excel file ...")
t1 = time.time()
wb = Workbook()
wb.remove(wb.active)

_write_sheet(wb, "Customer",     CUSTOMER_COLS,     customers)
print(f"   ✓ Customer sheet       — {len(customers):,} rows  ×  {len(CUSTOMER_COLS)} columns")

_write_sheet(wb, "Accounts",     ACCOUNT_COLS,      accounts)
print(f"   ✓ Accounts sheet       — {len(accounts):,} rows  ×  {len(ACCOUNT_COLS)} columns")

_write_sheet(wb, "Transactions", TRANSACTION_COLS,  transactions)
print(f"   ✓ Transactions sheet   — {len(transactions):,} rows  ×  {len(TRANSACTION_COLS)} columns")

# Data_Dictionary sheet
ws_dd = wb.create_sheet("Data_Dictionary")
ws_dd.append(["Table Name", "Column Name", "Required Data Type", "Pandas Dtype"])
_style_header(ws_dd, 4)
for row in DATA_DICT:
    ws_dd.append(list(row))
_auto_width(ws_dd, max_width=40)
ws_dd.freeze_panes = "A2"
print(f"   ✓ Data_Dictionary sheet — {len(DATA_DICT)} entries")

wb.save(filepath)
write_time = time.time() - t1
size_kb = os.path.getsize(filepath) / 1024

print(f"\n   ✓ Saved  → {filepath}")
print(f"   ✓ Size   → {size_kb:.0f} KB")
print(f"   ✓ Write  → {write_time:.1f}s")
print(f"\n{'='*65}")
print(f"  Total time : {time.time()-t0:.1f}s")
print(f"  File       : output/{filename}")
print(f"{'='*65}\n")
