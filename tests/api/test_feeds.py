"""
tests/api/test_feeds.py — Data-feed field mapping (Phase 11.4 step 4):
suggested mappings, row checks, and loading customers, accounts and
transactions from client CSV files without code changes.
"""
from __future__ import annotations

import json

import pytest

from app.models.account import Account
from app.models.alert import Alert
from app.models.audit import AuditLog
from app.models.customer import Customer
from app.models.transaction import Transaction

pytestmark = pytest.mark.db

CUSTOMERS_CSV = (
    "Client Name;E-mail;DOB;Nationality;Client Type;Internal Notes\n"
    "Feedco Alpha Ltd;alpha@feedco.example;01/02/1990;GB;corporate;vip\n"
    "Feedco Beta;beta@feedco.example;15/11/1985;FR;Individual;\n"
    "Feedco Gamma;not-an-email;31/12/1970;DE;individual;\n"
    "Feedco Delta;delta@feedco.example;31/02/1980;DE;spaceship;\n"
).encode()

CUSTOMER_MAPPING = {"full_name": "Client Name", "email": "E-mail", "date_of_birth": "DOB", "country": "Nationality", "customer_type": "Client Type"}


def _post(client, headers, path, csv_bytes, **form):
    return client.post(f"/api/v1/feeds/{path}", data=form, files={"file": ("feed.csv", csv_bytes, "text/csv")}, headers=headers)


def _run(client, headers, csv_bytes, target, mapping, **form):
    return _post(client, headers, "run", csv_bytes, target=target, mapping=json.dumps(mapping), **{k: str(v).lower() for k, v in form.items()})


def test_preview_suggests_columns_from_names_and_values(client, auth_headers, compliance_headers):
    assert _post(client, auth_headers, "preview", CUSTOMERS_CSV, target="CUSTOMERS").status_code == 403

    resp = _post(client, compliance_headers, "preview", CUSTOMERS_CSV, target="CUSTOMERS")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["columns"] == ["Client Name", "E-mail", "DOB", "Nationality", "Client Type", "Internal Notes"]
    assert body["row_count"] == 4 and len(body["sample_rows"]) == 4
    suggested = {field: s["column"] for field, s in body["suggested"].items()}
    assert suggested == CUSTOMER_MAPPING  # the semicolon delimiter and the differently named columns are handled
    assert "Internal Notes" not in suggested.values()
    assert all(0 < s["confidence"] <= 1 for s in body["suggested"].values())
    assert {f["name"] for f in body["fields"] if f["required"]} == {"full_name", "email"}


def test_dry_run_reports_bad_rows_and_loads_nothing(client, compliance_headers, db_session):
    resp = _run(client, compliance_headers, CUSTOMERS_CSV, "CUSTOMERS", CUSTOMER_MAPPING)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["dry_run"], body["rows_total"], body["rows_valid"], body["rows_invalid"], body["rows_loaded"]) == (True, 4, 2, 2, 0)
    errors = {e["row"]: e["message"] for e in body["errors"]}
    assert "email" in errors[4].lower()
    assert "not a date" in errors[5] and "not one of INDIVIDUAL, CORPORATE, FUND" in errors[5]
    assert db_session.query(Customer).filter(Customer.email.like("%@feedco.example")).count() == 0


def test_load_is_all_or_nothing_unless_invalid_rows_are_skipped(client, compliance_headers, db_session):
    refused = _run(client, compliance_headers, CUSTOMERS_CSV, "CUSTOMERS", CUSTOMER_MAPPING, dry_run=False)
    assert (refused.json()["rows_loaded"], refused.json()["rows_invalid"]) == (0, 2)
    assert db_session.query(Customer).filter(Customer.email.like("%@feedco.example")).count() == 0

    loaded = _run(client, compliance_headers, CUSTOMERS_CSV, "CUSTOMERS", CUSTOMER_MAPPING, dry_run=False, skip_invalid=True)
    assert (loaded.json()["rows_loaded"], loaded.json()["rows_invalid"]) == (2, 2)
    alpha = db_session.query(Customer).filter_by(email="alpha@feedco.example").one()
    assert (alpha.full_name, alpha.customer_type, alpha.country, alpha.date_of_birth.isoformat()) == ("Feedco Alpha Ltd", "CORPORATE", "GB", "1990-02-01")
    assert db_session.query(AuditLog).filter_by(entity_type="CUSTOMER", entity_id=alpha.id, action="CREATE").count() == 1

    # Loading the same file again adds nothing
    again = _run(client, compliance_headers, CUSTOMERS_CSV, "CUSTOMERS", CUSTOMER_MAPPING, dry_run=False, skip_invalid=True)
    assert (again.json()["rows_loaded"], again.json()["rows_skipped_existing"]) == (0, 2)

    runs = client.get("/api/v1/feeds/runs", headers=compliance_headers).json()
    assert len({r["id"] for r in runs}) >= 3 and all(len(r["filename"]) for r in runs)


def test_accounts_and_transactions_load_by_reference_and_run_the_rules(client, compliance_headers, db_session):
    _run(client, compliance_headers, CUSTOMERS_CSV, "CUSTOMERS", CUSTOMER_MAPPING, dry_run=False, skip_invalid=True)

    accounts_csv = (
        "Acct No,Owner Email,Product,CCY,Balance\n"
        "FC-001,alpha@feedco.example,checking,USD,\"1,250.50\"\n"
        "FC-002,nobody@feedco.example,savings,USD,10\n"
    ).encode()
    account_mapping = {"account_ref": "Acct No", "customer_email": "Owner Email", "account_type": "Product", "currency": "CCY", "balance": "Balance"}
    resp = _run(client, compliance_headers, accounts_csv, "ACCOUNTS", account_mapping, dry_run=False, skip_invalid=True)
    body = resp.json()
    assert (body["rows_loaded"], body["rows_invalid"]) == (1, 1) and "load customers first" in body["errors"][0]["message"]
    account = db_session.query(Account).filter(Account.account_metadata["external_ref"].astext == "FC-001").one()
    assert (float(account.balance), account.account_type) == (1250.50, "CHECKING")

    transactions_csv = (
        "Account,Value Date,Type,Amount,Beneficiary,Country\n"
        "FC-001,2026-09-01T10:00:00,transfer,\"250,000.00\",Acme Trading,GB\n"
        "FC-001,02/09/2026,deposit,75.25,,\n"
        "FC-404,2026-09-03,deposit,10,,\n"
        "FC-001,2026-09-04,transfer,-5,,\n"
    ).encode()
    txn_mapping = {"account_ref": "Account", "transaction_date": "Value Date", "transaction_type": "Type", "amount": "Amount",
                   "meta_counterparty": "Beneficiary", "meta_country": "Country"}
    check = _run(client, compliance_headers, transactions_csv, "TRANSACTIONS", txn_mapping)
    assert (check.json()["rows_valid"], check.json()["rows_invalid"]) == (2, 2)
    messages = " | ".join(e["message"] for e in check.json()["errors"])
    assert "load accounts first" in messages and "amount" in messages.lower()

    loaded = _run(client, compliance_headers, transactions_csv, "TRANSACTIONS", txn_mapping, dry_run=False, skip_invalid=True)
    assert loaded.json()["rows_loaded"] == 2
    txns = db_session.query(Transaction).filter_by(account_id=account.id).order_by(Transaction.amount).all()
    assert [float(t.amount) for t in txns] == [75.25, 250000.00]
    assert txns[0].transaction_date.date().isoformat() == "2026-09-02"  # day first
    # The large transfer went through the rules engine like any other transaction
    assert "R001" in (txns[1].risk_flags or {}).get("triggered_rules", [])
    assert db_session.query(Alert).filter_by(customer_id=account.customer_id).count() >= 1

    again = _run(client, compliance_headers, transactions_csv, "TRANSACTIONS", txn_mapping, dry_run=False, skip_invalid=True)
    assert (again.json()["rows_loaded"], again.json()["rows_skipped_existing"]) == (0, 2)


def test_mapping_problems_are_refused_before_any_row_is_read(client, compliance_headers):
    missing_required = {"full_name": "Client Name"}
    assert "Email" in _run(client, compliance_headers, CUSTOMERS_CSV, "CUSTOMERS", missing_required).json()["detail"]
    wrong_column = {**CUSTOMER_MAPPING, "phone": "Telephone"}
    assert "no column named: Telephone" in _run(client, compliance_headers, CUSTOMERS_CSV, "CUSTOMERS", wrong_column).json()["detail"]
    wrong_field = {**CUSTOMER_MAPPING, "shoe_size": "DOB"}
    assert _run(client, compliance_headers, CUSTOMERS_CSV, "CUSTOMERS", wrong_field).status_code == 422
    assert _post(client, compliance_headers, "run", CUSTOMERS_CSV, target="CUSTOMERS", mapping="not json").status_code == 422
    assert _post(client, compliance_headers, "preview", b"\xff\xfe\x00binary", target="CUSTOMERS").status_code == 415
    assert _post(client, compliance_headers, "preview", b"only one column\nvalue\n", target="CUSTOMERS").status_code == 422


def test_saved_mapping_can_be_reused(client, auth_headers, compliance_headers):
    payload = {"name": "Feedco customers", "target": "CUSTOMERS", "mapping": CUSTOMER_MAPPING, "date_day_first": True}
    assert client.post("/api/v1/feeds/mappings", json=payload, headers=auth_headers).status_code == 403
    saved = client.post("/api/v1/feeds/mappings", json=payload, headers=compliance_headers)
    assert saved.status_code == 201 and saved.json()["mapping"] == CUSTOMER_MAPPING

    # Saving under the same name updates it
    updated = client.post("/api/v1/feeds/mappings", json={**payload, "date_day_first": False}, headers=compliance_headers)
    assert updated.json()["id"] == saved.json()["id"] and updated.json()["date_day_first"] is False
    names = [m["name"] for m in client.get("/api/v1/feeds/mappings", headers=compliance_headers).json()]
    assert names.count("Feedco customers") == 1
    bad = client.post("/api/v1/feeds/mappings", json={**payload, "name": "Bad", "mapping": {"shoe_size": "DOB"}}, headers=compliance_headers)
    assert bad.status_code == 422

    run = _run(client, compliance_headers, CUSTOMERS_CSV, "CUSTOMERS", CUSTOMER_MAPPING, mapping_id=saved.json()["id"])
    assert run.json()["mapping_id"] == saved.json()["id"]
