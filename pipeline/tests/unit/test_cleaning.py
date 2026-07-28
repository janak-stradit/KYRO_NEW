"""
tests/unit/test_cleaning.py — Unit tests for data cleaning layer.
Tests: string normalisation, date parsing, imputation strategies,
       outlier detection methods, duplicate resolution.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import pytest
import numpy as np
import pandas as pd

from pipeline.cleaning.cleaner import (
    clean_string, clean_string_series, parse_date_series,
    clip_negative_amounts, impute_missing, handle_duplicates,
)
from pipeline.cleaning.outlier_detector import (
    detect_outliers_iqr, detect_outliers_zscore,
    detect_outliers_modified_zscore, winsorize_series, handle_outliers,
)


class TestCleanString:
    def test_strips_whitespace(self):
        assert clean_string("  hello world  ") == "hello world"

    def test_collapses_double_spaces(self):
        assert clean_string("hello   world") == "hello world"

    def test_strips_html_tags(self):
        assert clean_string("<b>Bold</b>") == "Bold"

    def test_html_entity_decode(self):
        assert clean_string("Tom &amp; Jerry") == "Tom & Jerry"

    def test_upper_case(self):
        assert clean_string("hello", case="upper") == "HELLO"

    def test_lower_case(self):
        assert clean_string("HELLO", case="lower") == "hello"

    def test_none_returns_none(self):
        assert clean_string(None) is None

    def test_empty_string_returns_none(self):
        assert clean_string("   ") is None

    def test_unicode_normalisation(self):
        # Decomposed 'é' (e + combining accent) → NFC composed 'é'
        assert clean_string("\u0065\u0301") == "\u00e9"

    def test_removes_control_chars(self):
        result = clean_string("hello\x00world")
        assert "\x00" not in result
        assert "helloworld" in result


class TestParseDateSeries:
    def test_iso_format(self):
        s = pd.Series(["2023-01-15", "2022-06-30"])
        result = parse_date_series(s)
        assert result.iloc[0] == pd.Timestamp("2023-01-15")

    def test_mixed_formats(self):
        s = pd.Series(["2023-01-15", "15/06/2022", "2021-12-31T00:00:00Z"])
        result = parse_date_series(s)
        assert result.notna().all()

    def test_invalid_date_returns_default(self):
        s = pd.Series(["not-a-date"])
        result = parse_date_series(s, default=pd.Timestamp("2000-01-01"))
        assert result.iloc[0] == pd.Timestamp("2000-01-01")

    def test_none_returns_default(self):
        s = pd.Series([None])
        result = parse_date_series(s)
        assert pd.isna(result.iloc[0])


class TestClipNegativeAmounts:
    def test_negatives_clipped(self):
        s = pd.Series([-100.0, 0.0, 500.0, -0.5])
        result = clip_negative_amounts(s, fill=0.0)
        assert (result >= 0).all()

    def test_positive_unchanged(self):
        s = pd.Series([10.0, 500.0, 1000.0])
        result = clip_negative_amounts(s)
        assert list(result) == [10.0, 500.0, 1000.0]


class TestImputeMissing:
    def test_median_imputation(self):
        df = pd.DataFrame({"amount": [10.0, 20.0, None, 30.0]})
        result = impute_missing(df, {"amount": {"strategy": "median"}})
        assert result["amount"].isna().sum() == 0
        assert result["amount"].iloc[2] == 20.0

    def test_mean_imputation(self):
        df = pd.DataFrame({"risk_score": [10.0, 30.0, None]})
        result = impute_missing(df, {"risk_score": {"strategy": "mean"}})
        assert result["risk_score"].iloc[2] == pytest.approx(20.0)

    def test_mode_imputation(self):
        df = pd.DataFrame({"risk_level": ["LOW", "LOW", None, "HIGH"]})
        result = impute_missing(df, {"risk_level": {"strategy": "mode"}})
        assert result["risk_level"].iloc[2] == "LOW"

    def test_constant_imputation(self):
        df = pd.DataFrame({"meta_counterparty": ["Alice", None, "Bob"]})
        result = impute_missing(df, {"meta_counterparty": {"strategy": "constant", "fill_value": "UNKNOWN"}})
        assert result["meta_counterparty"].iloc[1] == "UNKNOWN"

    def test_zero_imputation(self):
        df = pd.DataFrame({"balance": [100.0, None, 200.0]})
        result = impute_missing(df, {"balance": {"strategy": "zero"}})
        assert result["balance"].iloc[1] == 0.0

    def test_ffill_imputation(self):
        df = pd.DataFrame({"country": ["US", None, None, "GB"]})
        result = impute_missing(df, {"country": {"strategy": "ffill"}})
        assert result["country"].iloc[1] == "US"
        assert result["country"].iloc[2] == "US"

    def test_missing_col_silently_skipped(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        result = impute_missing(df, {"nonexistent_col": {"strategy": "median"}})
        assert list(result.columns) == ["a"]


class TestHandleDuplicates:
    def test_exact_duplicates_removed(self):
        df = pd.DataFrame([
            {"customer_id": "C1", "name": "Alice"},
            {"customer_id": "C1", "name": "Alice"},  # exact duplicate
        ])
        clean, dupes = handle_duplicates(df, ["customer_id"])
        assert len(clean) == 1
        assert len(dupes) == 1

    def test_no_duplicates(self):
        df = pd.DataFrame([
            {"customer_id": "C1", "name": "Alice"},
            {"customer_id": "C2", "name": "Bob"},
        ])
        clean, dupes = handle_duplicates(df, ["customer_id"])
        assert len(clean) == 2
        assert len(dupes) == 0

    def test_missing_business_key_returns_original(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        clean, dupes = handle_duplicates(df, ["nonexistent_key"])
        assert len(clean) == 3


class TestOutlierDetection:
    def setup_method(self):
        self.normal = pd.Series([10, 12, 11, 13, 10, 12, 11, 1000])  # 1000 is outlier

    def test_iqr_detects_outlier(self):
        mask = detect_outliers_iqr(self.normal, multiplier=1.5)
        assert mask.iloc[-1] is True or mask.iloc[-1]

    def test_zscore_detects_outlier(self):
        mask = detect_outliers_zscore(self.normal, threshold=2.0)
        assert mask.iloc[-1]

    def test_modified_zscore_detects_outlier(self):
        mask = detect_outliers_modified_zscore(self.normal, threshold=2.0)
        assert mask.iloc[-1]

    def test_winsorize_clips_outliers(self):
        result = winsorize_series(self.normal, limits=(0.2, 0.2))
        assert result.max() < 1000

    def test_handle_outliers_winsorize(self):
        df = pd.DataFrame({"amount": [10, 12, 11, 13, 10, 12, 11, 10000]})
        clean, removed, report = handle_outliers(df, ["amount"], method="iqr", action="winsorize", percentile_lower=0.2, percentile_upper=0.8)
        assert "amount" in report
        assert clean["amount"].max() < 10000

    def test_handle_outliers_remove(self):
        df = pd.DataFrame({"amount": [10, 12, 11, 13, 10, 12, 11, 10000]})
        clean, removed, _ = handle_outliers(df, ["amount"], method="iqr", action="remove", iqr_multiplier=1.5)
        assert len(removed) >= 1
        assert 10000 not in clean["amount"].values
