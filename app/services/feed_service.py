"""
services/feed_service.py — Onboard a client data file without code changes
(Phase 11.4 step 4).

    preview   read a CSV and suggest which column is which KYRO field
    run       check every row against the mapping (dry run), or load the rows

Suggestions are rule-based: column names are compared with each field's
known names, and the sample values must look like the field's type. Rows are
loaded through the same code paths as the API, so customers are screened,
transactions are run through the rules engine, and everything is audited.

Files carry their own keys, not KYRO IDs: customers are matched by email,
accounts by an account reference kept on the account, and transactions by
their account reference.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from dateutil import parser as date_parser
from pydantic import ValidationError
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.customer import Customer
from app.models.feed import FeedRun
from app.models.transaction import Transaction
from app.schemas.account import AccountCreate
from app.schemas.customer import CustomerCreate
from app.schemas.transaction import TransactionCreate
from app.services.audit_service import log_action
from app.services.customer_service import create_customer

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20_000
_SUGGEST_MIN = 60  # name-similarity score below which no column is suggested
_ERRORS_KEPT = 50


class FeedError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str  # text | email | date | datetime | number | bool | choice
    required: bool = False
    names: tuple[str, ...] = ()  # other names this field goes by in client files
    choices: tuple[str, ...] = ()


TARGETS: dict[str, tuple[Field, ...]] = {
    "CUSTOMERS": (
        Field("full_name", "Full name", "text", True, ("name", "customer name", "client name", "legal name", "account holder")),
        Field("email", "Email", "email", True, ("email address", "e-mail", "contact email")),
        Field("phone", "Phone", "text", False, ("telephone", "mobile", "phone number", "contact number")),
        Field("date_of_birth", "Date of birth", "date", False, ("dob", "birth date", "birthdate", "date of incorporation")),
        Field("country", "Country", "text", False, ("nationality", "citizenship", "country of incorporation")),
        Field("residency_country", "Country of residence", "text", False, ("residence", "residency", "country of residence", "domicile")),
        Field("customer_type", "Customer type", "choice", False, ("type", "client type", "entity type", "segment"), ("INDIVIDUAL", "CORPORATE", "FUND")),
        Field("pep_flag", "PEP", "bool", False, ("pep", "politically exposed", "is pep")),
    ),
    "ACCOUNTS": (
        Field("account_ref", "Account reference", "text", True, ("account number", "account no", "account id", "acct", "iban")),
        Field("customer_email", "Customer email", "email", True, ("email", "owner email", "client email", "holder email")),
        Field("account_type", "Account type", "choice", True, ("type", "product", "product type"), ("CHECKING", "SAVINGS", "INVESTMENT", "TRADING")),
        Field("currency", "Currency", "text", False, ("ccy", "currency code")),
        Field("balance", "Balance", "number", False, ("current balance", "available balance", "amount")),
        Field("opened_date", "Opened date", "date", False, ("open date", "opening date", "date opened", "start date")),
    ),
    "TRANSACTIONS": (
        Field("account_ref", "Account reference", "text", True, ("account number", "account no", "account id", "acct", "iban")),
        Field("transaction_date", "Transaction date", "datetime", True, ("date", "value date", "booking date", "posted", "timestamp", "txn date")),
        Field("transaction_type", "Transaction type", "choice", True, ("type", "txn type", "category"), ("DEPOSIT", "WITHDRAWAL", "TRANSFER", "FX", "TRADE")),
        Field("amount", "Amount", "number", True, ("value", "transaction amount", "txn amount", "gross amount")),
        Field("currency", "Currency", "text", False, ("ccy", "currency code")),
        Field("meta_counterparty", "Counterparty", "text", False, ("beneficiary", "payee", "counterparty name", "recipient", "sender")),
        Field("meta_country", "Counterparty country", "text", False, ("country", "beneficiary country", "destination country", "counterparty country")),
    ),
}


# ── Reading the file ─────────────────────────────────────────────────────

def read_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if not data:
        raise FeedError("The file is empty")
    if len(data) > MAX_BYTES:
        raise FeedError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB", 413)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FeedError("The file is not UTF-8 text. Save it as CSV (UTF-8) and try again.", 415) from None
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    columns = [c.strip() for c in (reader.fieldnames or []) if c and c.strip()]
    if len(columns) < 2:
        raise FeedError("Could not find a header row with at least two columns")
    rows = []
    for raw in reader:
        row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k}
        if any(row.values()):
            rows.append(row)
        if len(rows) > MAX_ROWS:
            raise FeedError(f"The file has more than {MAX_ROWS:,} rows; split it into smaller files", 413)
    if not rows:
        raise FeedError("The file has a header but no data rows")
    return columns, rows


# ── Suggesting a mapping ─────────────────────────────────────────────────

def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _number(value: str) -> float:
    cleaned = re.sub(r"[^\d.,\-]", "", value)
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "") if cleaned.rfind(".") > cleaned.rfind(",") else cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        # "1,234" is a thousands separator; "12,50" is a decimal comma
        cleaned = cleaned.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", cleaned) else cleaned.replace(",", ".")
    return float(cleaned)


def _date(value: str, day_first: bool) -> datetime:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value):
        return date_parser.isoparse(value)
    return date_parser.parse(value, dayfirst=day_first)


_BOOL = {"true": True, "yes": True, "y": True, "1": True, "false": False, "no": False, "n": False, "0": False, "": False}


def _convert(field: Field, value: str, day_first: bool) -> Any:
    """Turn a cell into the field's type. Raises ValueError with a readable reason."""
    if field.kind == "number":
        try:
            return _number(value)
        except ValueError:
            raise ValueError(f"'{value}' is not a number") from None
    if field.kind in ("date", "datetime"):
        try:
            parsed = _date(value, day_first)
        except (ValueError, OverflowError):
            raise ValueError(f"'{value}' is not a date") from None
        if field.kind == "date":
            return parsed.date()
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    if field.kind == "bool":
        if value.casefold() not in _BOOL:
            raise ValueError(f"'{value}' is not yes/no")
        return _BOOL[value.casefold()]
    if field.kind == "choice":
        choice = _norm(value).upper().replace(" ", "_")
        if choice not in field.choices:
            raise ValueError(f"'{value}' is not one of {', '.join(field.choices)}")
        return choice
    return value


def _fits(field: Field, samples: list[str]) -> float:
    """Share of the sample values that look like this field's type."""
    values = [s for s in samples if s]
    if not values or field.kind == "text":
        return 1.0
    ok = 0
    for value in values:
        try:
            if field.kind == "email":
                ok += bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))
            else:
                _convert(field, value, True)
                ok += 1
        except ValueError:
            pass
    return ok / len(values)


def suggest(target: str, columns: list[str], rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Best column for each field: {field: {"column", "confidence", "reason"}}; a column is used once."""
    fields = TARGETS[target]
    samples = {c: [r.get(c, "") for r in rows[:25]] for c in columns}
    scored = []
    for field in fields:
        names = (_norm(field.name), _norm(field.label), *(_norm(n) for n in field.names))
        for column in columns:
            name_score = max(fuzz.token_sort_ratio(_norm(column), n) for n in names)
            fit = _fits(field, samples[column])
            if name_score >= _SUGGEST_MIN and fit >= 0.5:
                scored.append((name_score * (0.5 + fit / 2), field.name, column, name_score, fit))

    result: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    for score, field_name, column, name_score, fit in sorted(scored, reverse=True):
        if field_name in result or column in used:
            continue
        used.add(column)
        result[field_name] = {
            "column": column,
            "confidence": round(score / 100, 2),
            "reason": ("name matches" if name_score >= 90 else "name is similar") + (", values fit" if fit >= 0.9 else ", some values do not fit"),
        }
    return result


def preview(target: str, data: bytes) -> dict[str, Any]:
    columns, rows = read_csv(data)
    return {
        "target": target,
        "columns": columns,
        "row_count": len(rows),
        "sample_rows": rows[:5],
        "fields": [
            {"name": f.name, "label": f.label, "kind": f.kind, "required": f.required, "choices": list(f.choices)}
            for f in TARGETS[target]
        ],
        "suggested": suggest(target, columns, rows),
    }


# ── Checking and loading ─────────────────────────────────────────────────

def validate_mapping(target: str, mapping: dict[str, str], columns: list[str]) -> dict[str, str]:
    fields = {f.name: f for f in TARGETS[target]}
    mapping = {k: v for k, v in mapping.items() if v}
    unknown = sorted(set(mapping) - set(fields))
    if unknown:
        raise FeedError(f"Not a field for {target.lower()}: {', '.join(unknown)}")
    missing_cols = sorted({c for c in mapping.values() if c not in columns})
    if missing_cols:
        raise FeedError(f"The file has no column named: {', '.join(missing_cols)}")
    required = sorted(f.label for f in fields.values() if f.required and f.name not in mapping)
    if required:
        raise FeedError(f"Map a column to: {', '.join(required)}")
    return mapping


def _row_values(target: str, mapping: dict[str, str], row: dict[str, str], day_first: bool) -> dict[str, Any]:
    values: dict[str, Any] = {}
    problems = []
    for field in TARGETS[target]:
        column = mapping.get(field.name)
        cell = row.get(column, "") if column else ""
        if not cell:
            if field.required:
                problems.append(f"{field.label} is empty")
            continue
        try:
            values[field.name] = _convert(field, cell, day_first)
        except ValueError as exc:
            problems.append(f"{field.label}: {exc}")
    if problems:
        raise ValueError("; ".join(problems))
    return values


def _pydantic_message(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())


def _account_by_ref(db: Session, ref: str) -> Account | None:
    return db.query(Account).filter(Account.account_metadata["external_ref"].astext == ref).first()


def run(
    db: Session,
    *,
    target: str,
    mapping: dict[str, str],
    data: bytes,
    filename: str,
    day_first: bool,
    dry_run: bool,
    skip_invalid: bool,
    mapping_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> FeedRun:
    """
    Check every row; when `dry_run` is false, load the valid ones. Unless
    `skip_invalid` is set, nothing is loaded if any row is invalid.
    """
    columns, rows = read_csv(data)
    mapping = validate_mapping(target, mapping, columns)

    errors: list[dict[str, Any]] = []
    prepared: list[tuple[int, Any]] = []  # (row number, validated payload or resolved objects)
    existing = 0
    seen_keys: set[Any] = set()

    for number, row in enumerate(rows, start=2):  # row 1 is the header
        try:
            values = _row_values(target, mapping, row, day_first)
            if target == "CUSTOMERS":
                payload = CustomerCreate(**values)
                key = payload.email.casefold()
                if key in seen_keys:
                    raise ValueError(f"Email {payload.email} appears more than once in the file")
                seen_keys.add(key)
                if db.query(Customer.id).filter(Customer.email.ilike(payload.email)).first():
                    existing += 1
                    continue
                prepared.append((number, payload))
            elif target == "ACCOUNTS":
                ref = values.pop("account_ref")
                email = values.pop("customer_email")
                if ref in seen_keys:
                    raise ValueError(f"Account reference {ref} appears more than once in the file")
                seen_keys.add(ref)
                customer = db.query(Customer).filter(Customer.email.ilike(email)).first()
                if customer is None:
                    raise ValueError(f"No customer with email {email}; load customers first")
                if _account_by_ref(db, ref) is not None:
                    existing += 1
                    continue
                payload = AccountCreate(customer_id=customer.id, account_metadata={"external_ref": ref}, **values)
                prepared.append((number, payload))
            else:
                ref = values.pop("account_ref")
                account = _account_by_ref(db, ref)
                if account is None:
                    raise ValueError(f"No account with reference {ref}; load accounts first")
                payload = TransactionCreate(customer_id=account.customer_id, account_id=account.id, source_system="feed", **values)
                key = (account.id, payload.transaction_date, payload.transaction_type, round(payload.amount, 2), payload.meta_counterparty)
                duplicate = key in seen_keys or db.query(Transaction.id).filter(
                    Transaction.account_id == account.id, Transaction.transaction_date == payload.transaction_date,
                    Transaction.transaction_type == payload.transaction_type, Transaction.amount == payload.amount,
                ).first()
                if duplicate:
                    existing += 1
                    continue
                seen_keys.add(key)
                prepared.append((number, payload))
        except ValidationError as exc:
            errors.append({"row": number, "message": _pydantic_message(exc)})
        except ValueError as exc:
            errors.append({"row": number, "message": str(exc)})

    loaded = 0
    if not dry_run and prepared and (skip_invalid or not errors):
        if target == "CUSTOMERS":
            for _, payload in prepared:
                create_customer(db, payload, performed_by=user_id)  # screens and audits each customer
                loaded += 1
        elif target == "ACCOUNTS":
            for _, payload in prepared:
                account = Account(**payload.model_dump())
                db.add(account)
                db.flush()
                log_action(db, entity_type="ACCOUNT", entity_id=account.id, action="CREATE", performed_by=user_id, new_values=payload.model_dump(mode="json"))
                loaded += 1
            db.commit()
        else:
            from app.routers.transactions import _ingest_one  # rules engine, flags, alerts, audit

            for _, payload in prepared:
                _ingest_one(db, payload, user_id)
                loaded += 1
            db.commit()

    record = FeedRun(
        mapping_id=mapping_id, target=target, mapping=mapping, filename=(filename or "feed.csv")[:255],
        sha256=hashlib.sha256(data).hexdigest(), dry_run=dry_run, rows_total=len(rows), rows_valid=len(prepared),
        rows_loaded=loaded, rows_skipped_existing=existing, rows_invalid=len(errors),
        errors=errors[:_ERRORS_KEPT] or None, run_by=user_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
