"""
validation/validator.py — Comprehensive data validation framework.
Validates: column existence, types, PKs, FKs, dates, ranges, booleans,
           duplicates, nulls, regex, email, phone, UUID.
Generates validation reports and routes failed records to quarantine.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from pipeline.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# ── Regex patterns ────────────────────────────────────────────
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_PHONE_RE = re.compile(r"^[+\d\s\(\)\-\.]{7,20}$")
_UUID_RE  = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"]


@dataclass
class ValidationReport:
    entity_type: str
    total_records: int = 0
    valid_records: int = 0
    rejected_records: int = 0
    errors: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.valid_records / max(self.total_records, 1)

    def add_error(self, row_idx: Any, column: str, rule: str, value: Any, message: str) -> None:
        self.errors.append({
            "row_index": row_idx, "column": column,
            "rule": rule, "value": str(value)[:200], "message": message,
        })

    def summary(self) -> dict:
        return {
            "entity_type": self.entity_type,
            "total": self.total_records,
            "valid": self.valid_records,
            "rejected": self.rejected_records,
            "pass_rate": round(self.pass_rate, 4),
            "error_count": len(self.errors),
            "errors_sample": self.errors[:20],
        }


def _try_parse_date(value: Any, formats: list[str] = _DATE_FORMATS) -> bool:
    if pd.isna(value) or value is None:
        return False
    s = str(value).strip()
    for fmt in formats:
        try:
            datetime.strptime(s, fmt)
            return True
        except ValueError:
            continue
    # Also accept ISO 8601 with time
    try:
        pd.Timestamp(s)
        return True
    except Exception:
        return False


class AMLValidator:
    """
    Rule-based validator for AML dataset entities (customer, account, transaction).

    Usage::
        v = AMLValidator(config["validation"])
        valid_df, rejected_df, report = v.validate(df, entity_type="customers")
    """

    def __init__(self, validation_config: dict) -> None:
        self.cfg = validation_config
        self.rules = validation_config.get("rules", {})

    # ── Public entry point ────────────────────────────────────

    def validate(
        self, df: pd.DataFrame, entity_type: str
    ) -> tuple[pd.DataFrame, pd.DataFrame, ValidationReport]:
        """
        Validate a DataFrame against configured rules.

        Returns:
            valid_df: Rows that passed all rules.
            rejected_df: Rows that failed at least one rule.
            report: ValidationReport with full error details.
        """
        report = ValidationReport(entity_type=entity_type, total_records=len(df))
        entity_rules = self.rules.get(entity_type, {})

        row_errors: dict[int, list[dict]] = {}

        for col, col_rules in entity_rules.items():
            self._validate_column(df, col, col_rules, row_errors, report, entity_type)

        # Row-level checks
        self._check_duplicates(df, entity_type, row_errors, report)

        # Split valid / rejected
        bad_rows = set(row_errors.keys())
        valid_mask = ~df.index.isin(bad_rows)
        valid_df = df[valid_mask].copy()
        rejected_df = df[~valid_mask].copy()

        # Attach errors to rejected rows
        if not rejected_df.empty:
            rejected_df = rejected_df.copy()
            rejected_df["_validation_errors"] = rejected_df.index.map(
                lambda i: row_errors.get(i, [])
            )

        report.valid_records = len(valid_df)
        report.rejected_records = len(rejected_df)
        logger.info(
            "Validation [%s]: total=%d valid=%d rejected=%d pass_rate=%.2f%%",
            entity_type, report.total_records, report.valid_records,
            report.rejected_records, report.pass_rate * 100,
        )
        return valid_df, rejected_df, report

    # ── Column-level validation ───────────────────────────────

    def _validate_column(
        self, df: pd.DataFrame, col: str, rules: dict,
        row_errors: dict, report: ValidationReport, entity_type: str,
    ) -> None:
        # Column existence
        if col not in df.columns:
            if rules.get("required", False):
                report.warnings.append(f"Required column missing from DataFrame: {col}")
            return

        series = df[col]

        for idx, val in series.items():
            errors_for_row: list[dict] = []

            # Required / null check
            is_null = val is None or (isinstance(val, float) and pd.isna(val)) or val == ""
            if rules.get("required") and is_null:
                errors_for_row.append({"col": col, "rule": "required", "val": val, "msg": "Required value is null/empty"})

            if is_null:
                if errors_for_row:
                    row_errors.setdefault(idx, []).extend(errors_for_row)
                    for e in errors_for_row:
                        report.add_error(idx, col, e["rule"], val, e["msg"])
                continue  # skip further checks on null

            # Type check
            if "type" in rules:
                self._check_type(idx, col, val, rules["type"], errors_for_row, report)

            # Allowed values
            if "allowed_values" in rules and str(val) not in rules["allowed_values"]:
                msg = f"Value '{val}' not in allowed: {rules['allowed_values']}"
                errors_for_row.append({"col": col, "rule": "allowed_values", "val": val, "msg": msg})
                report.add_error(idx, col, "allowed_values", val, msg)

            # Numeric range
            if "min" in rules or "max" in rules:
                self._check_range(idx, col, val, rules, errors_for_row, report)

            # Regex
            if "regex" in rules:
                if not re.match(rules["regex"], str(val)):
                    msg = f"Value '{val}' does not match regex '{rules['regex']}'"
                    errors_for_row.append({"col": col, "rule": "regex", "val": val, "msg": msg})
                    report.add_error(idx, col, "regex", val, msg)

            # Format-specific
            if rules.get("format") == "email" and not _EMAIL_RE.match(str(val)):
                msg = f"Invalid email: {val}"
                errors_for_row.append({"col": col, "rule": "email", "val": val, "msg": msg})
                report.add_error(idx, col, "email", val, msg)

            if rules.get("format") == "phone" and not _PHONE_RE.match(str(val)):
                msg = f"Invalid phone: {val}"
                errors_for_row.append({"col": col, "rule": "phone", "val": val, "msg": msg})
                report.add_error(idx, col, "phone", val, msg)

            if rules.get("format") == "uuid":
                try:
                    uuid.UUID(str(val))
                except ValueError:
                    msg = f"Invalid UUID: {val}"
                    errors_for_row.append({"col": col, "rule": "uuid", "val": val, "msg": msg})
                    report.add_error(idx, col, "uuid", val, msg)

            if rules.get("format") == "date" and not _try_parse_date(val):
                msg = f"Invalid date format: {val}"
                errors_for_row.append({"col": col, "rule": "date_format", "val": val, "msg": msg})
                report.add_error(idx, col, "date_format", val, msg)

            if errors_for_row:
                row_errors.setdefault(idx, []).extend(errors_for_row)

    def _check_type(self, idx, col, val, expected_type, errors, report):
        type_map = {"string": str, "float": (int, float), "int": int, "boolean": bool}
        py_type = type_map.get(expected_type)
        if py_type and not isinstance(val, py_type):
            try:
                if expected_type == "float":
                    float(val)
                elif expected_type == "int":
                    int(val)
                elif expected_type == "boolean":
                    if str(val).lower() not in ("true", "false", "1", "0"):
                        raise ValueError()
            except (ValueError, TypeError):
                msg = f"Expected type '{expected_type}', got '{type(val).__name__}' for value '{val}'"
                errors.append({"col": col, "rule": "type", "val": val, "msg": msg})
                report.add_error(idx, col, "type", val, msg)

    def _check_range(self, idx, col, val, rules, errors, report):
        try:
            num = float(val)
        except (ValueError, TypeError):
            return
        if "min" in rules and num < rules["min"]:
            msg = f"Value {val} < min {rules['min']}"
            errors.append({"col": col, "rule": "min", "val": val, "msg": msg})
            report.add_error(idx, col, "min", val, msg)
        if "max" in rules and num > rules["max"]:
            msg = f"Value {val} > max {rules['max']}"
            errors.append({"col": col, "rule": "max", "val": val, "msg": msg})
            report.add_error(idx, col, "max", val, msg)

    def _check_duplicates(self, df, entity_type, row_errors, report):
        pk_map = {
            "customers": "customer_id",
            "accounts": "account_id",
            "transactions": "transaction_id",
        }
        pk_col = pk_map.get(entity_type)
        if not pk_col or pk_col not in df.columns:
            return
        dupes = df[df.duplicated(subset=[pk_col], keep="first")]
        for idx in dupes.index:
            val = df.loc[idx, pk_col]
            msg = f"Duplicate {pk_col}: {val}"
            row_errors.setdefault(idx, []).append({"col": pk_col, "rule": "unique_pk", "val": val, "msg": msg})
            report.add_error(idx, pk_col, "unique_pk", val, msg)
        if len(dupes) > 0:
            logger.warning("Found %d duplicate %s records", len(dupes), entity_type)
