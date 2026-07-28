"""
tests/unit/test_validation.py — Unit tests for the validation layer.
Tests all rule types: required, type, range, regex, email, UUID, allowed_values, duplicates.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import pytest
import pandas as pd
from pipeline.validation.validator import AMLValidator, ValidationReport, _EMAIL_RE, _try_parse_date

# Minimal config for validator
VALIDATION_CFG = {
    "rules": {
        "customers": {
            "customer_id": {"required": True, "type": "string", "regex": "^CUST-\\d{6}$"},
            "email":       {"required": True, "type": "string", "format": "email"},
            "risk_score":  {"required": True, "type": "float",  "min": 0.0, "max": 100.0},
            "risk_level":  {"required": True, "type": "string",
                            "allowed_values": ["LOW","MEDIUM","HIGH"]},
            "pep_flag":    {"required": True, "type": "boolean"},
        },
        "transactions": {
            "transaction_id": {"required": True, "type": "string"},
            "amount":         {"required": True, "type": "float", "min": 0.01},
            "transaction_type": {"required": True, "type": "string",
                                 "allowed_values": ["DEPOSIT","WITHDRAWAL","TRANSFER_IN","TRANSFER_OUT",
                                                    "BUY","SELL","PAYMENT","FEE","REFUND"]},
        },
    }
}


@pytest.fixture
def validator():
    return AMLValidator(VALIDATION_CFG)


@pytest.fixture
def good_customers():
    return pd.DataFrame([
        {"customer_id": "CUST-000001", "email": "alice@bank.com", "risk_score": 55.0,
         "risk_level": "HIGH", "pep_flag": False},
        {"customer_id": "CUST-000002", "email": "bob@corp.io",   "risk_score": 20.0,
         "risk_level": "LOW",  "pep_flag": True},
    ])


class TestEmailRegex:
    def test_valid_emails(self):
        assert _EMAIL_RE.match("user@example.com")
        assert _EMAIL_RE.match("user.name+tag@sub.domain.io")

    def test_invalid_emails(self):
        assert not _EMAIL_RE.match("notanemail")
        assert not _EMAIL_RE.match("missing@")
        assert not _EMAIL_RE.match("@nodomain.com")


class TestDateParser:
    def test_iso_date(self):
        assert _try_parse_date("2023-01-15")

    def test_slash_date(self):
        assert _try_parse_date("15/01/2023")

    def test_invalid_date(self):
        assert not _try_parse_date("not-a-date")

    def test_none_value(self):
        assert not _try_parse_date(None)


class TestValidationReport:
    def test_pass_rate_100(self):
        r = ValidationReport("customers", total_records=10, valid_records=10, rejected_records=0)
        assert r.pass_rate == 1.0

    def test_pass_rate_50(self):
        r = ValidationReport("customers", total_records=10, valid_records=5, rejected_records=5)
        assert r.pass_rate == 0.5

    def test_summary_keys(self):
        r = ValidationReport("transactions", total_records=100)
        s = r.summary()
        assert "total" in s and "valid" in s and "rejected" in s and "pass_rate" in s


class TestAMLValidator:
    def test_valid_customers_pass(self, validator, good_customers):
        valid, rejected, report = validator.validate(good_customers, "customers")
        assert len(valid) == 2
        assert len(rejected) == 0
        assert report.pass_rate == 1.0

    def test_invalid_email_rejected(self, validator):
        df = pd.DataFrame([{
            "customer_id": "CUST-000001", "email": "bad-email",
            "risk_score": 50.0, "risk_level": "HIGH", "pep_flag": False,
        }])
        valid, rejected, report = validator.validate(df, "customers")
        assert len(rejected) == 1
        assert len(valid) == 0

    def test_invalid_risk_level_rejected(self, validator):
        df = pd.DataFrame([{
            "customer_id": "CUST-000001", "email": "good@email.com",
            "risk_score": 50.0, "risk_level": "EXTREME", "pep_flag": False,
        }])
        valid, rejected, _ = validator.validate(df, "customers")
        assert len(rejected) == 1

    def test_out_of_range_risk_score_rejected(self, validator):
        df = pd.DataFrame([{
            "customer_id": "CUST-000001", "email": "ok@email.com",
            "risk_score": 150.0, "risk_level": "HIGH", "pep_flag": True,
        }])
        _, rejected, _ = validator.validate(df, "customers")
        assert len(rejected) == 1

    def test_bad_customer_id_regex(self, validator):
        df = pd.DataFrame([{
            "customer_id": "BAD-ID", "email": "ok@email.com",
            "risk_score": 50.0, "risk_level": "HIGH", "pep_flag": False,
        }])
        _, rejected, _ = validator.validate(df, "customers")
        assert len(rejected) == 1

    def test_missing_required_null(self, validator):
        df = pd.DataFrame([{
            "customer_id": None, "email": "ok@email.com",
            "risk_score": 50.0, "risk_level": "HIGH", "pep_flag": False,
        }])
        _, rejected, _ = validator.validate(df, "customers")
        assert len(rejected) == 1

    def test_duplicate_pk_detection(self, validator):
        df = pd.DataFrame([
            {"customer_id": "CUST-000001", "email": "a@b.com", "risk_score": 10.0, "risk_level": "LOW", "pep_flag": False},
            {"customer_id": "CUST-000001", "email": "c@d.com", "risk_score": 20.0, "risk_level": "LOW", "pep_flag": False},
        ])
        _, rejected, _ = validator.validate(df, "customers")
        assert len(rejected) == 1  # second dupe row rejected

    def test_valid_transaction(self, validator):
        df = pd.DataFrame([{
            "transaction_id": "TXN-001", "amount": 500.0, "transaction_type": "DEPOSIT",
        }])
        valid, rejected, _ = validator.validate(df, "transactions")
        assert len(valid) == 1

    def test_zero_amount_rejected(self, validator):
        df = pd.DataFrame([{
            "transaction_id": "TXN-001", "amount": 0.0, "transaction_type": "DEPOSIT",
        }])
        _, rejected, _ = validator.validate(df, "transactions")
        assert len(rejected) == 1

    def test_invalid_txn_type_rejected(self, validator):
        df = pd.DataFrame([{
            "transaction_id": "TXN-002", "amount": 100.0, "transaction_type": "UNKNOWN_TYPE",
        }])
        _, rejected, _ = validator.validate(df, "transactions")
        assert len(rejected) == 1

    def test_empty_dataframe(self, validator):
        df = pd.DataFrame(columns=["customer_id", "email", "risk_score", "risk_level", "pep_flag"])
        valid, rejected, report = validator.validate(df, "customers")
        assert len(valid) == 0
        assert report.total_records == 0
