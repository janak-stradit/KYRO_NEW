"""
tests/api/test_rules_r1.py — Rules engine R1: base-currency amounts, noise
reduction, one sanctions case per customer, alert provenance, daily
consolidation, replay and the ML label freeze.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.config import get_settings
from app.models.account import Account
from app.models.alert import Alert
from app.models.customer import Customer
from app.models.fx_rate import FxRate
from app.models.transaction import Transaction
from app.services import fx_service, rules_replay
from app.services.rules_engine import RuleOptions, apply_to_transaction, evaluate, open_sanctions_case

MONDAY_NOON = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)

_ECB = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube><Cube time="2026-07-10">
    <Cube currency="USD" rate="1.10"/><Cube currency="JPY" rate="165.00"/><Cube currency="GBP" rate="0.85"/>
  </Cube></Cube>
</gesmes:Envelope>"""


@pytest.fixture
def switches(monkeypatch):
    """Turn R1 switches on for one test: switches(noise=True, base=True, consolidate=True)."""
    settings = get_settings()

    def turn(*, base=False, noise=False, consolidate=False):
        monkeypatch.setattr(settings, "rules_base_currency_enabled", base)
        monkeypatch.setattr(settings, "rules_noise_reduction_enabled", noise)
        monkeypatch.setattr(settings, "rules_consolidate_daily", consolidate)
        monkeypatch.setattr(settings, "base_currency", "USD")

    turn()
    return turn


def _customer(db_session, email, **extra):
    customer = Customer(full_name="R1 Test", email=email, **extra)
    db_session.add(customer)
    db_session.flush()
    account = Account(customer_id=customer.id, account_type="CHECKING", balance=1000)
    db_session.add(account)
    db_session.flush()
    return customer, account


def _txn(db_session, customer, account, *, amount, currency="USD", at=MONDAY_NOON, **extra):
    txn = Transaction(customer_id=customer.id, account_id=account.id, transaction_date=at, amount=amount, currency=currency, **extra)
    db_session.add(txn)
    db_session.flush()
    return txn


# ── Exchange rates (no database) ─────────────────────────────────────────

def test_ecb_rates_are_converted_to_the_base_currency():
    rows = {r["currency"]: r for r in fx_service.parse_ecb(_ECB, "USD")}
    assert rows["EUR"]["rate_to_base"] == Decimal("1.1000000000")             # 1 EUR = 1.10 USD
    assert rows["JPY"]["rate_to_base"] == (Decimal("1.10") / Decimal("165")).quantize(Decimal("1e-10"))
    assert "USD" not in rows and rows["GBP"]["rate_date"] == date(2026, 7, 10)
    with pytest.raises(ValueError):
        fx_service.parse_ecb(_ECB, "CHF")


# ── Base currency ────────────────────────────────────────────────────────

@pytest.mark.db
def test_r001_compares_in_the_base_currency_when_switched_on(db_session, switches):
    fx_service.store(db_session, fx_service.parse_ecb(_ECB, "USD"))
    customer, account = _customer(db_session, "r1.fx@example.com")
    yen = _txn(db_session, customer, account, amount=15000, currency="JPY")  # about 100 USD

    conversion = fx_service.apply(db_session, yen)
    assert conversion.amount_base == Decimal("100.00") and not conversion.stale
    assert "R001" in {r.rule_id for r in evaluate(db_session, yen, customer)}  # switch off: compared as 15,000
    switches(base=True)
    assert "R001" not in {r.rule_id for r in evaluate(db_session, yen, customer)}

    euros = _txn(db_session, customer, account, amount=9500, currency="EUR")  # 10,450 USD
    fx_service.apply(db_session, euros)
    assert "R001" in {r.rule_id for r in evaluate(db_session, euros, customer)}


@pytest.mark.db
def test_a_missing_or_old_rate_is_marked(db_session):
    db_session.add(FxRate(rate_date=date(2026, 6, 1), currency="GBP", rate_to_base=Decimal("1.25"), source="TEST"))
    db_session.flush()
    stale = fx_service.convert(db_session, 100, "GBP", date(2026, 7, 13))
    assert stale.amount_base == Decimal("125.00") and stale.stale
    missing = fx_service.convert(db_session, 100, "XAF", date(2026, 7, 13))
    assert missing.amount_base is None and missing.missing


# ── Noise reduction ──────────────────────────────────────────────────────

@pytest.mark.db
def test_pep_and_sanctions_are_not_raised_on_every_payment(db_session, switches):
    switches(noise=True)
    customer, account = _customer(db_session, "r1.pep@example.com", pep_flag=True, sanctions_flag=True)
    _, _, alert = apply_to_transaction(db_session, _txn(db_session, customer, account, amount=50), customer)
    assert alert is None


@pytest.mark.db
def test_weak_indicators_alone_do_not_alert(db_session, switches, monkeypatch):
    customer, account = _customer(db_session, "r1.weak@example.com")
    saturday = MONDAY_NOON - timedelta(days=2)
    # Make the weak indicators enough to reach the alert threshold on their own
    from app.services import rules_engine
    monkeypatch.setitem(rules_engine.DEFAULTS, "ALERT_THRESHOLD", 30)
    txn = _txn(db_session, customer, account, amount=5000, at=saturday, meta_counterparty="New Co")  # R007 + R008 + R009
    _, _, legacy = apply_to_transaction(db_session, txn, customer)
    assert legacy is not None

    switches(noise=True)
    txn2 = _txn(db_session, customer, account, amount=6000, at=saturday + timedelta(hours=2), meta_counterparty="Other Co")
    _, _, quiet = apply_to_transaction(db_session, txn2, customer)
    assert quiet is None


@pytest.mark.db
def test_rapid_succession_looks_back_only(db_session, switches):
    customer, account = _customer(db_session, "r1.r010@example.com")
    first = _txn(db_session, customer, account, amount=10)
    _txn(db_session, customer, account, amount=10, at=MONDAY_NOON + timedelta(seconds=30))
    assert "R010" in {r.rule_id for r in evaluate(db_session, first, customer)}  # legacy also counts the later one
    switches(noise=True)
    assert "R010" not in {r.rule_id for r in evaluate(db_session, first, customer)}


@pytest.mark.db
def test_a_confirmed_sanctions_match_opens_one_case(db_session, switches):
    customer, _ = _customer(db_session, "r1.sanctions@example.com")
    assert open_sanctions_case(db_session, customer, "test") is None  # switch off: R006 alerts per payment instead
    switches(noise=True)
    case = open_sanctions_case(db_session, customer, "Confirmed match on Test Person")
    assert case is not None and case.alert_type == "SANCTIONS" and case.sla_days
    assert open_sanctions_case(db_session, customer, "again") is None


# ── Provenance and consolidation ─────────────────────────────────────────

@pytest.mark.db
def test_alerts_record_the_rule_version_values_and_evidence(db_session, switches):
    customer, account = _customer(db_session, "r1.provenance@example.com", sanctions_flag=True)
    txn = _txn(db_session, customer, account, amount=20000)
    _, _, alert = apply_to_transaction(db_session, txn, customer)
    assert alert.rule_version and len(alert.rule_version) == 16
    assert alert.evidence_transaction_ids == [txn.id]
    assert alert.parameters["thresholds"]["AMOUNT_THRESHOLD"] == 10000
    assert {r["rule"] for r in alert.parameters["rules"]} >= {"R001", "R006"}


@pytest.mark.db
def test_one_open_rules_alert_per_customer_per_day(db_session, switches):
    switches(consolidate=True)
    customer, account = _customer(db_session, "r1.consolidate@example.com")
    now = datetime.now(timezone.utc)
    first = _txn(db_session, customer, account, amount=60000, at=now)
    second = _txn(db_session, customer, account, amount=70000, at=now + timedelta(minutes=5))
    _, _, a1 = apply_to_transaction(db_session, first, customer)
    _, _, a2 = apply_to_transaction(db_session, second, customer)
    assert a1.id == a2.id
    assert a2.evidence_transaction_ids == [first.id, second.id]
    assert db_session.query(Alert).filter_by(customer_id=customer.id).count() == 1


# ── Replay ───────────────────────────────────────────────────────────────

@pytest.mark.db
def test_replay_reports_what_a_change_would_do_and_writes_nothing(db_session, switches):
    customer, account = _customer(db_session, "r1.replay@example.com", pep_flag=True)
    txn = _txn(db_session, customer, account, amount=50)
    _, _, alert = apply_to_transaction(db_session, txn, customer)  # legacy: PEP alerts on every payment
    alert.status, alert.resolution_outcome = "ESCALATED", "ESCALATED"
    alert.created_at = MONDAY_NOON
    db_session.flush()

    report = rules_replay.replay(db_session, MONDAY_NOON - timedelta(days=1), MONDAY_NOON + timedelta(days=1),
                                 RuleOptions(noise_reduction=True))
    assert report["transactions_replayed"] == 1
    assert report["alerting_transactions"] == {"current": 1, "proposed": 0}
    assert report["rule_hits"]["current"].get("R005") == 1 and "R005" not in report["rule_hits"]["proposed"]
    assert [lost["alert_id"] for lost in report["possible_lost_true_positives"]] == [str(alert.id)]
    db_session.refresh(txn)
    assert txn.risk_score is not None  # unchanged by the replay


@pytest.mark.db
def test_replay_endpoint_needs_rules_permission(client, auth_headers, compliance_headers):
    body = {"start": "2026-07-01T00:00:00Z", "end": "2026-07-02T00:00:00Z"}
    assert client.post("/api/v1/rules/replay", json=body, headers=auth_headers).status_code == 403
    resp = client.post("/api/v1/rules/replay", json=body, headers=compliance_headers)
    assert resp.status_code == 200 and resp.json()["proposed_options"]["noise_reduction"] is True
    assert client.get("/api/v1/rules/fx", headers=compliance_headers).json()["base_currency"] == get_settings().base_currency


# ── ML label freeze ──────────────────────────────────────────────────────

def test_ml_retraining_refuses_a_changed_label_definition(monkeypatch, switches):
    from app.ml.training import pipeline
    from app.ml.training.trainer import label_definition

    legacy = label_definition(RuleOptions())
    monkeypatch.setattr(pipeline, "_active_label_definition", lambda registry: legacy)
    switches(noise=True)
    assert label_definition() != legacy
    with pytest.raises(pipeline.LabelDefinitionChanged):
        pipeline.run_training_pipeline()
