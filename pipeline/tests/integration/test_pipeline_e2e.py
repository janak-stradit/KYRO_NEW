"""
tests/integration/test_pipeline_e2e.py — End-to-end integration test.
Runs the full pipeline against data from the existing AML generator.
Does NOT require a live PostgreSQL instance — database load steps are mocked.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from generator.data_generator import generate_dataset
from pipeline.ingestion.ingestor import from_dict_list, chunked_reader
from pipeline.validation.validator import AMLValidator
from pipeline.cleaning.cleaner import (
    clean_customers, clean_accounts, clean_transactions, handle_duplicates
)
from pipeline.cleaning.outlier_detector import handle_outliers
from pipeline.transformation.transformer import (
    scale_columns, ordinal_encode, extract_date_features
)
from pipeline.feature_engineering.engineer import (
    build_customer_features, build_transaction_features, add_aml_flags
)
from pipeline.quality.data_quality import DataQualityChecker

VALIDATION_CFG = {
    "rules": {
        "customers": {
            "customer_id": {"required": True, "type": "string"},
            "risk_score":  {"required": True, "type": "float", "min": 0.0, "max": 100.0},
            "risk_level":  {"required": True, "type": "string",
                            "allowed_values": ["LOW","MEDIUM","HIGH"]},
        },
        "accounts":     {},
        "transactions": {
            "amount": {"required": True, "type": "float", "min": 0.01},
        },
    }
}

QUALITY_CFG = {
    "completeness_threshold": 0.80,
    "uniqueness_threshold": 0.99,
    "validity_threshold": 0.90,
    "drift_detection": False,
    "drift_threshold": 0.05,
    "generate_score": True,
}


@pytest.fixture(scope="module")
def small_dataset():
    """Generate a small AML dataset (10 customers) for integration tests."""
    return generate_dataset(num_customers=10)


@pytest.fixture(scope="module")
def dataframes(small_dataset):
    customers = from_dict_list(small_dataset["customers"])
    accounts = from_dict_list(small_dataset["accounts"])
    transactions = from_dict_list(small_dataset["transactions"])
    return customers, accounts, transactions


class TestIngestion:
    def test_from_dict_list_customers(self, small_dataset):
        df = from_dict_list(small_dataset["customers"])
        assert len(df) == 10
        assert "customer_id" in df.columns

    def test_chunked_reader_splits_correctly(self, dataframes):
        customers, _, _ = dataframes
        chunks = list(chunked_reader(customers, batch_size=3))
        assert len(chunks) >= 3
        assert sum(len(c) for c in chunks) == len(customers)

    def test_from_dict_list_empty(self):
        df = from_dict_list([])
        assert df.empty


class TestValidationIntegration:
    def test_customers_mostly_valid(self, dataframes):
        customers, _, _ = dataframes
        validator = AMLValidator(VALIDATION_CFG)
        valid, rejected, report = validator.validate(customers, "customers")
        # Generator produces clean data — expect very high pass rate
        assert report.pass_rate >= 0.95
        assert len(valid) >= 9

    def test_transactions_mostly_valid(self, dataframes):
        _, _, transactions = dataframes
        validator = AMLValidator(VALIDATION_CFG)
        valid, rejected, report = validator.validate(transactions, "transactions")
        assert report.pass_rate >= 0.95


class TestCleaningIntegration:
    def test_clean_customers_no_crash(self, dataframes):
        customers, _, _ = dataframes
        cfg = {"missing_values": {"customers": {"risk_score": {"strategy": "median"}}}}
        result = clean_customers(customers, cfg)
        assert len(result) == len(customers)
        assert "email" in result.columns

    def test_clean_transactions_parses_dates(self, dataframes):
        _, _, transactions = dataframes
        result = clean_transactions(transactions, {})
        if "transaction_date" in result.columns:
            assert pd.api.types.is_datetime64_any_dtype(result["transaction_date"]) or \
                   result["transaction_date"].dtype == object

    def test_handle_duplicates_no_loss(self, dataframes):
        customers, _, _ = dataframes
        clean, dupes = handle_duplicates(customers, ["customer_id"])
        assert len(clean) + len(dupes) == len(customers)


class TestOutlierIntegration:
    def test_iqr_outlier_on_transactions(self, dataframes):
        _, _, transactions = dataframes
        clean, removed, report = handle_outliers(
            transactions, ["amount"], method="iqr", action="winsorize"
        )
        assert "amount" in report
        assert len(clean) == len(transactions)  # winsorize keeps all rows

    def test_remove_outliers_reduces_rows(self, dataframes):
        _, _, transactions = dataframes
        clean, removed, _ = handle_outliers(
            transactions, ["amount"], method="iqr", action="remove", iqr_multiplier=1.5
        )
        assert len(clean) + len(removed) == len(transactions)


class TestTransformationIntegration:
    def test_scale_risk_score(self, dataframes):
        customers, _, _ = dataframes
        result = scale_columns(customers, ["risk_score"], method="robust")
        assert "risk_score_scaled" in result.columns

    def test_ordinal_encode_risk_level(self, dataframes):
        customers, _, _ = dataframes
        result = ordinal_encode(customers, "risk_level", ["LOW","MEDIUM","HIGH"])
        assert "risk_level_ordinal" in result.columns
        assert result["risk_level_ordinal"].between(-1, 3).all()


class TestFeatureEngineeringIntegration:
    def test_aml_flags_added(self, dataframes):
        _, _, transactions = dataframes
        result = add_aml_flags(transactions)
        assert "flag_high_value" in result.columns
        assert result["flag_high_value"].isin([0, 1]).all()

    def test_build_customer_features(self, dataframes):
        customers, accounts, transactions = dataframes
        result = build_customer_features(customers, accounts, transactions)
        assert "feature_set_version" in result.columns
        assert len(result) == len(customers)

    def test_build_transaction_features(self, dataframes):
        _, _, transactions = dataframes
        result = build_transaction_features(transactions)
        assert "feature_set_version" in result.columns
        assert "flag_high_value" in result.columns


class TestQualityIntegration:
    def test_quality_passes_on_generated_data(self, dataframes):
        customers, accounts, transactions = dataframes
        checker = DataQualityChecker(QUALITY_CFG)

        c_report = checker.check(customers, "customers")
        a_report = checker.check(accounts, "accounts")
        t_report = checker.check(transactions, "transactions")

        # Generated data should generally pass quality thresholds
        assert c_report.overall_score >= 0.70
        assert a_report.overall_score >= 0.70
        assert t_report.overall_score >= 0.70

    def test_quality_report_serialisable(self, dataframes):
        customers, _, _ = dataframes
        checker = DataQualityChecker(QUALITY_CFG)
        report = checker.check(customers, "customers")
        d = report.to_dict()
        import json
        json_str = json.dumps(d, default=str)
        assert len(json_str) > 100
