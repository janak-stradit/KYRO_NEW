"""
tests/app/test_rules_engine.py — Direct unit tests for the R001-R010 rules engine.
"""
from datetime import datetime, timezone

import pytest

from app.models.account import Account
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.services.rules_engine import evaluate, recommended_action_for, score_from_rules

pytestmark = pytest.mark.db


def _make_customer(db_session, **overrides) -> Customer:
    customer = Customer(full_name="Rules Test", email=overrides.pop("email", "rules@example.com"), **overrides)
    db_session.add(customer)
    db_session.flush()
    return customer


def _make_account(db_session, customer: Customer) -> Account:
    account = Account(customer_id=customer.id, account_type="CHECKING", balance=1000)
    db_session.add(account)
    db_session.flush()
    return account


def _make_txn(db_session, customer, account, **overrides) -> Transaction:
    txn = Transaction(
        customer_id=customer.id,
        account_id=account.id,
        transaction_date=overrides.pop("transaction_date", datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)),  # a Monday
        amount=overrides.pop("amount", 100),
        currency="USD",
        **overrides,
    )
    db_session.add(txn)
    db_session.flush()
    return txn


def test_amount_threshold_rule_r001(db_session):
    customer = _make_customer(db_session, email="r001@example.com")
    account = _make_account(db_session, customer)
    txn = _make_txn(db_session, customer, account, amount=15000)

    rules = evaluate(db_session, txn, customer)
    assert any(r.rule_id == "R001" for r in rules)


def test_pep_and_sanctions_rules(db_session):
    customer = _make_customer(db_session, email="r005r006@example.com", pep_flag=True, sanctions_flag=True)
    account = _make_account(db_session, customer)
    txn = _make_txn(db_session, customer, account, amount=100)

    rules = evaluate(db_session, txn, customer)
    ids = {r.rule_id for r in rules}
    assert "R005" in ids
    assert "R006" in ids

    score = score_from_rules(rules)
    assert score == 100  # capped
    assert recommended_action_for(rules, score) == "SAR"


def test_weekend_activity_rule_r008(db_session):
    customer = _make_customer(db_session, email="r008@example.com")
    account = _make_account(db_session, customer)
    saturday = datetime(2026, 7, 11, 10, 0, tzinfo=timezone.utc)
    txn = _make_txn(db_session, customer, account, amount=50, transaction_date=saturday)

    rules = evaluate(db_session, txn, customer)
    assert any(r.rule_id == "R008" for r in rules)


def test_round_amount_rule_r009(db_session):
    customer = _make_customer(db_session, email="r009@example.com")
    account = _make_account(db_session, customer)
    txn = _make_txn(db_session, customer, account, amount=5000)

    rules = evaluate(db_session, txn, customer)
    assert any(r.rule_id == "R009" for r in rules)


def test_no_rules_triggered_for_ordinary_transaction(db_session):
    customer = _make_customer(db_session, email="clean@example.com")
    account = _make_account(db_session, customer)
    # A Monday, small non-round amount, no flags.
    txn = _make_txn(db_session, customer, account, amount=123.45)

    rules = evaluate(db_session, txn, customer)
    assert rules == []
    assert score_from_rules(rules) == 0
    assert recommended_action_for(rules, 0) is None
