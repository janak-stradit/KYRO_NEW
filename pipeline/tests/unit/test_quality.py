"""
tests/unit/test_quality.py — Unit tests for the data quality framework.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import pytest
import pandas as pd
from pipeline.quality.data_quality import DataQualityChecker, DataQualityReport

QUALITY_CFG = {
    "completeness_threshold": 0.95,
    "uniqueness_threshold": 1.0,
    "validity_threshold": 0.98,
    "drift_detection": False,
    "drift_threshold": 0.05,
    "generate_score": True,
}


@pytest.fixture
def checker():
    return DataQualityChecker(QUALITY_CFG)


@pytest.fixture
def good_customers():
    return pd.DataFrame([
        {"customer_id": f"CUST-{i:06d}", "risk_score": float(i % 100),
         "risk_level": "LOW" if i % 100 < 25 else "HIGH",
         "kyc_status": "COMPLETE", "pep_flag": False}
        for i in range(1, 101)
    ])


class TestCompleteness:
    def test_full_data_scores_1(self, checker, good_customers):
        report = checker.check(good_customers, "customers")
        dim = report.dimensions["completeness"]
        assert dim.score == pytest.approx(1.0)
        assert dim.passed

    def test_partial_nulls_lowers_score(self, checker):
        df = pd.DataFrame({
            "customer_id": ["C1", "C2", None, None, None],
            "risk_score": [10.0, 20.0, None, None, None],
        })
        report = checker.check(df, "customers")
        dim = report.dimensions["completeness"]
        assert dim.score < 1.0

    def test_all_nulls_scores_zero(self, checker):
        df = pd.DataFrame({"customer_id": [None, None], "risk_score": [None, None]})
        report = checker.check(df, "customers")
        assert report.dimensions["completeness"].score == 0.0


class TestUniqueness:
    def test_unique_pks_score_1(self, checker, good_customers):
        report = checker.check(good_customers, "customers")
        assert report.dimensions["uniqueness"].score == 1.0

    def test_duplicate_pks_lower_score(self, checker):
        df = pd.DataFrame({"customer_id": ["C1", "C1", "C2"]})
        report = checker.check(df, "customers")
        assert report.dimensions["uniqueness"].score < 1.0
        assert not report.dimensions["uniqueness"].passed


class TestValidity:
    def test_valid_customers_score_1(self, checker):
        df = pd.DataFrame({
            "customer_id": ["C1", "C2"],
            "risk_score": [50.0, 20.0],
            "risk_level": ["HIGH", "LOW"],
            "kyc_status": ["COMPLETE", "PENDING"],
        })
        report = checker.check(df, "customers")
        assert report.dimensions["validity"].score == pytest.approx(1.0)

    def test_invalid_risk_level_penalised(self, checker):
        df = pd.DataFrame({
            "customer_id": ["C1"],
            "risk_score": [50.0],
            "risk_level": ["EXTREME"],  # not in allowed list
            "kyc_status": ["COMPLETE"],
        })
        report = checker.check(df, "customers")
        assert report.dimensions["validity"].score < 1.0


class TestConsistency:
    def test_aligned_risk_passes(self, checker):
        df = pd.DataFrame({
            "customer_id": ["C1"],
            "risk_score": [80.0],
            "risk_level": ["HIGH"],
        })
        report = checker.check(df, "customers")
        assert report.dimensions["consistency"].score == 1.0

    def test_misaligned_risk_fails(self, checker):
        df = pd.DataFrame({
            "customer_id": ["C1"],
            "risk_score": [80.0],
            "risk_level": ["LOW"],   # wrong — score is 80 → HIGH
        })
        report = checker.check(df, "customers")
        assert report.dimensions["consistency"].score < 1.0


class TestOverallScore:
    def test_overall_is_mean_of_dimensions(self, checker, good_customers):
        report = checker.check(good_customers, "customers")
        scores = [d.score for d in report.dimensions.values()]
        expected = sum(scores) / len(scores)
        assert report.overall_score == pytest.approx(expected, abs=0.001)

    def test_empty_df_fails(self, checker):
        df = pd.DataFrame(columns=["customer_id", "risk_score"])
        report = checker.check(df, "customers")
        assert not report.dimensions["anomaly_detection"].passed

    def test_report_to_dict(self, checker, good_customers):
        report = checker.check(good_customers, "customers")
        d = report.to_dict()
        assert "overall_score" in d
        assert "dimensions" in d
        assert "completeness" in d["dimensions"]
