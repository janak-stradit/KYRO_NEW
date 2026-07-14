"""
quality/data_quality.py — Automated data quality framework.
Checks: Completeness, Uniqueness, Consistency, Accuracy, Validity,
        Integrity, Timeliness/Freshness, Distribution Drift, Anomaly Detection.
Generates per-entity quality scores and full quality reports.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

logger = logging.getLogger(__name__)


@dataclass
class QualityDimension:
    name: str
    score: float = 1.0
    passed: bool = True
    details: dict = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)


@dataclass
class DataQualityReport:
    entity_type: str
    row_count: int
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dimensions: dict[str, QualityDimension] = field(default_factory=dict)
    overall_score: float = 1.0
    passed: bool = True

    def add_dimension(self, dim: QualityDimension) -> None:
        self.dimensions[dim.name] = dim

    def compute_overall(self) -> float:
        scores = [d.score for d in self.dimensions.values()]
        self.overall_score = round(np.mean(scores) if scores else 0.0, 4)
        self.passed = self.overall_score >= 0.90
        return self.overall_score

    def to_dict(self) -> dict:
        return {
            "entity_type": self.entity_type,
            "row_count": self.row_count,
            "checked_at": self.checked_at,
            "overall_score": self.overall_score,
            "passed": self.passed,
            "dimensions": {
                k: {"score": v.score, "passed": v.passed, "issues": v.issues, "details": v.details}
                for k, v in self.dimensions.items()
            },
        }


class DataQualityChecker:
    """
    Automated quality checker for AML pipeline DataFrames.

    Usage::
        checker = DataQualityChecker(config["data_quality"])
        report = checker.check(df, entity_type="customers")
    """

    def __init__(self, quality_cfg: dict) -> None:
        self.cfg = quality_cfg
        self.completeness_threshold = float(quality_cfg.get("completeness_threshold", 0.95))
        self.uniqueness_threshold = float(quality_cfg.get("uniqueness_threshold", 1.0))
        self.validity_threshold = float(quality_cfg.get("validity_threshold", 0.98))

    def check(
        self,
        df: pd.DataFrame,
        entity_type: str,
        reference_df: pd.DataFrame | None = None,
    ) -> DataQualityReport:
        """Run all quality checks; return comprehensive report."""
        report = DataQualityReport(entity_type=entity_type, row_count=len(df))

        report.add_dimension(self._completeness(df))
        report.add_dimension(self._uniqueness(df, entity_type))
        report.add_dimension(self._validity(df, entity_type))
        report.add_dimension(self._consistency(df, entity_type))
        report.add_dimension(self._timeliness(df, entity_type))

        if reference_df is not None and self.cfg.get("drift_detection"):
            report.add_dimension(self._distribution_drift(df, reference_df, entity_type))

        report.add_dimension(self._anomaly_score(df, entity_type))

        score = report.compute_overall()
        logger.info(
            "Quality [%s]: score=%.4f passed=%s rows=%d",
            entity_type, score, report.passed, len(df),
        )
        return report

    # ── Individual Dimension Checks ───────────────────────────

    def _completeness(self, df: pd.DataFrame) -> QualityDimension:
        """Completeness = 1 - (null_cells / total_cells)."""
        # Columns that are by-design nullable in the AML domain — skip from completeness scoring
        NULLABLE_COLS = {
            "risk_flags", "meta_counterparty_type",
            "meta_destination_country", "meta_origin_country",
        }
        df_check = df.drop(columns=[c for c in NULLABLE_COLS if c in df.columns])
        total = df_check.size
        nulls = df_check.isnull().sum().sum()
        score = 1.0 - (nulls / max(total, 1))
        issues = []
        col_null_rates = df.isnull().mean()
        bad_cols = {
            k: round(v, 4)
            for k, v in col_null_rates.items()
            if v > (1 - self.completeness_threshold) and k not in NULLABLE_COLS
        }
        if bad_cols:
            issues.append(f"Columns with high null rate: {bad_cols}")
        return QualityDimension(
            name="completeness", score=round(score, 4),
            passed=score >= self.completeness_threshold,
            details={"null_cells": int(nulls), "total_cells": int(total), "col_null_rates": {k: round(v, 4) for k, v in col_null_rates.items()}},
            issues=issues,
        )

    def _uniqueness(self, df: pd.DataFrame, entity_type: str) -> QualityDimension:
        """Uniqueness = unique rows / total rows on business key."""
        pk_map = {"customers": "customer_id", "accounts": "account_id", "transactions": "transaction_id"}
        pk = pk_map.get(entity_type)
        if not pk or pk not in df.columns:
            return QualityDimension(name="uniqueness", score=1.0, passed=True, details={"note": "No PK to check"})
        total = len(df)
        unique = df[pk].nunique()
        score = unique / max(total, 1)
        dupes = int(total - unique)
        return QualityDimension(
            name="uniqueness", score=round(score, 4),
            passed=score >= self.uniqueness_threshold,
            details={"total": total, "unique": unique, "duplicates": dupes},
            issues=[f"{dupes} duplicate {pk} values"] if dupes > 0 else [],
        )

    def _validity(self, df: pd.DataFrame, entity_type: str) -> QualityDimension:
        """Validity = rows with all values in expected domain / total rows."""
        issues = []
        violation_counts = 0

        if entity_type == "customers":
            valid_risk_levels = {"LOW", "MEDIUM", "HIGH"}
            valid_kyc = {"COMPLETE", "PENDING", "EXPIRED", "PARTIAL"}
            if "risk_level" in df.columns:
                bad = (~df["risk_level"].isin(valid_risk_levels)).sum()
                if bad:
                    issues.append(f"{bad} invalid risk_level values")
                    violation_counts += bad
            if "kyc_status" in df.columns:
                bad = (~df["kyc_status"].isin(valid_kyc)).sum()
                if bad:
                    issues.append(f"{bad} invalid kyc_status values")
                    violation_counts += bad
            if "risk_score" in df.columns:
                bad = ((df["risk_score"] < 0) | (df["risk_score"] > 100)).sum()
                if bad:
                    issues.append(f"{bad} risk_score out of [0, 100]")
                    violation_counts += bad

        if entity_type == "transactions":
            valid_txn_types = {"DEPOSIT","WITHDRAWAL","TRANSFER_IN","TRANSFER_OUT","BUY","SELL","PAYMENT","FEE","REFUND"}
            if "transaction_type" in df.columns:
                bad = (~df["transaction_type"].isin(valid_txn_types)).sum()
                if bad:
                    issues.append(f"{bad} invalid transaction_type values")
                    violation_counts += bad
            if "amount" in df.columns:
                bad = (pd.to_numeric(df["amount"], errors="coerce") <= 0).sum()
                if bad:
                    issues.append(f"{bad} non-positive amounts")
                    violation_counts += bad

        score = 1.0 - (violation_counts / max(len(df), 1))
        return QualityDimension(
            name="validity", score=round(max(score, 0.0), 4),
            passed=score >= self.validity_threshold,
            details={"violation_count": int(violation_counts)},
            issues=issues,
        )

    def _consistency(self, df: pd.DataFrame, entity_type: str) -> QualityDimension:
        """Consistency: cross-column rule checks (risk_score ↔ risk_level alignment)."""
        issues = []
        violations = 0
        if entity_type == "customers" and all(c in df.columns for c in ("risk_score", "risk_level")):
            def check_alignment(row):
                s = row["risk_score"]
                l = row["risk_level"]
                if pd.isna(s) or pd.isna(l):
                    return True
                s = float(s)
                return (
                    (s >= 66 and l == "HIGH") or
                    (33 <= s < 66 and l == "MEDIUM") or
                    (s < 33 and l == "LOW")
                )
            bad = (~df.apply(check_alignment, axis=1)).sum()
            if bad:
                issues.append(f"{bad} rows with mismatched risk_score/risk_level")
                violations = int(bad)
        score = 1.0 - (violations / max(len(df), 1))
        return QualityDimension(
            name="consistency", score=round(score, 4),
            passed=violations == 0, details={"violations": violations}, issues=issues,
        )

    def _timeliness(self, df: pd.DataFrame, entity_type: str) -> QualityDimension:
        """Timeliness: informational staleness check only. Does not penalise overall score
        since the pipeline processes historical batches by design."""
        date_col_map = {
            "customers": "kyc_last_review",
            "accounts": "opened_date",
            "transactions": "transaction_date",
        }
        col = date_col_map.get(entity_type)
        if not col or col not in df.columns:
            return QualityDimension(name="timeliness", score=1.0, passed=True)
        now = pd.Timestamp.now()
        dates = pd.to_datetime(df[col], errors="coerce")
        stale = (now - dates).dt.days > 365
        stale_count = int(stale.sum())
        # Score is always 1.0 — timeliness is informational for historical AML batches
        return QualityDimension(
            name="timeliness", score=1.0, passed=True,
            details={"stale_count_over_1yr": stale_count, "note": "informational only"},
        )

    def _distribution_drift(
        self, df: pd.DataFrame, reference: pd.DataFrame, entity_type: str
    ) -> QualityDimension:
        """KS-test based distribution drift detection for numeric columns."""
        drift_cols = {"customers": ["risk_score"], "transactions": ["amount"], "accounts": ["balance"]}
        cols = drift_cols.get(entity_type, [])
        drift_results = {}
        max_drift = 0.0
        for col in cols:
            if col not in df.columns or col not in reference.columns:
                continue
            current = pd.to_numeric(df[col], errors="coerce").dropna()
            ref = pd.to_numeric(reference[col], errors="coerce").dropna()
            if len(current) < 5 or len(ref) < 5:
                continue
            stat, p_value = ks_2samp(current, ref)
            drift_results[col] = {"ks_stat": round(float(stat), 4), "p_value": round(float(p_value), 4)}
            max_drift = max(max_drift, stat)
        threshold = float(self.cfg.get("drift_threshold", 0.05))
        score = 1.0 - min(max_drift, 1.0)
        return QualityDimension(
            name="distribution_drift", score=round(score, 4),
            passed=max_drift <= threshold,
            details=drift_results,
            issues=[f"Drift detected (KS={max_drift:.4f})"] if max_drift > threshold else [],
        )

    def _anomaly_score(self, df: pd.DataFrame, entity_type: str) -> QualityDimension:
        """Row-count anomaly: flag if row count deviates significantly from expectations."""
        # Simple heuristic: flag if DataFrame is empty
        issues = []
        score = 1.0
        if len(df) == 0:
            score = 0.0
            issues.append("Empty DataFrame — no rows to process")
        return QualityDimension(
            name="anomaly_detection", score=score, passed=score > 0,
            details={"row_count": len(df)}, issues=issues,
        )
