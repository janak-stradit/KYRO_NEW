"""
tests/unit/test_transformation.py — Unit tests for transformation and feature engineering.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import pytest
import numpy as np
import pandas as pd

from pipeline.transformation.transformer import (
    label_encode, ordinal_encode, onehot_encode, frequency_encode,
    log_transform, power_transform, extract_date_features, scale_columns,
)
from pipeline.feature_engineering.engineer import (
    add_aml_flags, add_lag_features, add_rolling_features,
    add_ratio_feature, add_frequency_count, add_rank_feature,
)


class TestEncodings:
    def test_label_encode(self):
        df = pd.DataFrame({"kyc_status": ["COMPLETE", "PENDING", "EXPIRED", "COMPLETE"]})
        result, encoders = label_encode(df, ["kyc_status"])
        assert "kyc_status_encoded" in result.columns
        assert result["kyc_status_encoded"].dtype in [int, np.int64, object]
        assert "kyc_status" in encoders

    def test_ordinal_encode_order(self):
        df = pd.DataFrame({"risk_level": ["LOW", "HIGH", "HIGH", "MEDIUM"]})
        result = ordinal_encode(df, "risk_level", ["LOW", "MEDIUM", "HIGH"])
        assert "risk_level_ordinal" in result.columns
        assert result.loc[result["risk_level"] == "HIGH", "risk_level_ordinal"].iloc[0] == 2
        assert result.loc[result["risk_level"] == "LOW", "risk_level_ordinal"].iloc[0] == 0

    def test_onehot_encode_creates_columns(self):
        df = pd.DataFrame({"txn_type": ["DEPOSIT", "WITHDRAWAL", "DEPOSIT"]})
        result = onehot_encode(df, ["txn_type"])
        assert "txn_type_DEPOSIT" in result.columns
        assert "txn_type_WITHDRAWAL" in result.columns

    def test_frequency_encode(self):
        df = pd.DataFrame({"country": ["US", "US", "GB", "US", "GB"]})
        result = frequency_encode(df, ["country"])
        assert "country_freq" in result.columns
        assert result.loc[result["country"] == "US", "country_freq"].iloc[0] == 3
        assert result.loc[result["country"] == "GB", "country_freq"].iloc[0] == 2


class TestNumericTransforms:
    def test_log_transform_positive(self):
        df = pd.DataFrame({"amount": [10.0, 100.0, 1000.0]})
        result = log_transform(df, ["amount"])
        assert "amount_log" in result.columns
        assert (result["amount_log"] > 0).all()

    def test_log_transform_zero_safe(self):
        df = pd.DataFrame({"amount": [0.0, 1.0, 10.0]})
        result = log_transform(df, ["amount"], offset=1.0)
        assert result["amount_log"].iloc[0] == pytest.approx(0.0)

    def test_power_transform_yeo_johnson(self):
        df = pd.DataFrame({"amount": [10.0, 100.0, 1000.0, 50.0, 200.0]})
        result = power_transform(df, ["amount"], method="yeo-johnson")
        assert "amount_power" in result.columns
        assert not result["amount_power"].isna().any()


class TestDateFeatureExtraction:
    def test_extracts_year_month_day(self):
        df = pd.DataFrame({"transaction_date": pd.to_datetime(["2023-06-15", "2022-01-01"])})
        result = extract_date_features(df, "transaction_date", ["year", "month", "day"])
        assert "transaction_date_year" in result.columns
        assert result["transaction_date_year"].iloc[0] == 2023
        assert result["transaction_date_month"].iloc[0] == 6
        assert result["transaction_date_day"].iloc[0] == 15

    def test_is_weekend_flag(self):
        # 2023-06-17 is a Saturday
        df = pd.DataFrame({"transaction_date": pd.to_datetime(["2023-06-17", "2023-06-19"])})
        result = extract_date_features(df, "transaction_date", ["is_weekend"])
        assert result["transaction_date_is_weekend"].iloc[0] == 1  # Saturday
        assert result["transaction_date_is_weekend"].iloc[1] == 0  # Monday=0


class TestAMLFlags:
    def test_high_value_flag(self):
        df = pd.DataFrame({"amount": [500.0, 15000.0, 9500.0]})
        result = add_aml_flags(df)
        assert result["flag_high_value"].iloc[0] == 0
        assert result["flag_high_value"].iloc[1] == 1

    def test_high_risk_country_flag(self):
        df = pd.DataFrame({"meta_country_code": ["US", "IR", "GB"]})
        result = add_aml_flags(df)
        assert result["flag_high_risk_country"].iloc[0] == 0
        assert result["flag_high_risk_country"].iloc[1] == 1

    def test_pep_flag(self):
        df = pd.DataFrame({"pep_flag": [True, False]})
        result = add_aml_flags(df)
        assert result["flag_pep"].iloc[0] == 1
        assert result["flag_pep"].iloc[1] == 0

    def test_structuring_flag(self):
        df = pd.DataFrame({"amount": [9500.0, 500.0, 10000.0]})
        result = add_aml_flags(df)
        assert result["flag_structuring"].iloc[0] == 1  # 9000-9999 range
        assert result["flag_structuring"].iloc[1] == 0


class TestLagRollingFeatures:
    def setup_method(self):
        self.df = pd.DataFrame({
            "account_id": ["A1"] * 5 + ["A2"] * 5,
            "transaction_date": pd.to_datetime(
                ["2023-01-01","2023-01-02","2023-01-03","2023-01-04","2023-01-05"] * 2
            ),
            "amount": [100, 200, 300, 400, 500, 10, 20, 30, 40, 50],
        })

    def test_lag_features_created(self):
        result = add_lag_features(self.df, "amount", "account_id", "transaction_date", lags=[1, 3])
        assert "amount_lag_1" in result.columns
        assert "amount_lag_3" in result.columns

    def test_lag_1_correct_value(self):
        result = add_lag_features(self.df, "amount", "account_id", "transaction_date", lags=[1])
        a1 = result[result["account_id"] == "A1"].sort_values("transaction_date")
        # Second row lag should equal first row amount
        assert pd.isna(a1["amount_lag_1"].iloc[0])
        assert a1["amount_lag_1"].iloc[1] == 100.0

    def test_rolling_mean_created(self):
        result = add_rolling_features(
            self.df, "amount", "account_id", "transaction_date",
            windows=[3], agg_funcs=["mean"]
        )
        assert "amount_rolling_3_mean" in result.columns

    def test_ratio_feature(self):
        df = pd.DataFrame({"amount": [100.0, 200.0], "balance": [1000.0, 2000.0]})
        result = add_ratio_feature(df, "amount", "balance")
        assert "amount_to_balance_ratio" in result.columns
        assert result["amount_to_balance_ratio"].iloc[0] == pytest.approx(0.1)

    def test_rank_feature(self):
        df = pd.DataFrame({"amount": [100.0, 500.0, 250.0, 50.0]})
        result = add_rank_feature(df, "amount")
        assert "amount_rank" in result.columns
        assert result["amount_rank"].between(0, 1).all()
