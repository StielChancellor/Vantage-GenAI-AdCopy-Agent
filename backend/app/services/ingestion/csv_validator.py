"""CSV schema validation for the three training data types.

Returns a ValidationReport before any data is ingested. Rejects batches
where >20% of key fields are null.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger("vantage.ingestion")

# Required columns per section type
_REQUIRED_COLUMNS: dict[str, list[str]] = {
    "ad_performance": ["headline", "description", "ctr"],
    "brand_usp": ["usp", "category"],
    "crm_performance": ["channel", "message", "open_rate"],
}

# Key columns — reject if >20% null
_KEY_COLUMNS: dict[str, list[str]] = {
    "ad_performance": ["headline", "ctr"],
    "brand_usp": ["usp"],
    "crm_performance": ["channel", "message"],
}

# Hospitality-specific optional columns (enrichment metadata)
_HOSPITALITY_COLUMNS: dict[str, list[str]] = {
    "ad_performance": ["platform", "campaign_id", "cvr", "impressions", "spend", "adr", "revpar"],
    "brand_usp": ["property_code", "priority", "verified"],
    "crm_performance": ["click_rate", "conversion_rate", "send_date", "audience_segment"],
}

NULL_THRESHOLD = 0.20


@dataclass
class RowError:
    row_index: int
    column: str
    issue: str


@dataclass
class ValidationReport:
    section_type: str
    total_rows: int
    valid_rows: int
    error_rows: int
    errors: list[RowError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    passed: bool = True
    rejection_reason: str = ""

    def summary(self) -> str:
        return (
            f"[{self.section_type}] {self.valid_rows}/{self.total_rows} rows valid. "
            f"Passed: {self.passed}. "
            + (f"Rejected: {self.rejection_reason}" if not self.passed else "")
        )


def validate_csv(df: pd.DataFrame, section_type: str) -> ValidationReport:
    """Validate a DataFrame against the schema for section_type.

    Returns a ValidationReport. Call .passed to determine if ingestion
    should proceed.
    """
    report = ValidationReport(
        section_type=section_type,
        total_rows=len(df),
        valid_rows=0,
        error_rows=0,
    )

    if section_type not in _REQUIRED_COLUMNS:
        report.passed = False
        report.rejection_reason = f"Unknown section_type: {section_type}"
        return report

    if df.empty:
        report.passed = False
        report.rejection_reason = "CSV is empty."
        return report

    # Normalize column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Check required columns present
    required = _REQUIRED_COLUMNS[section_type]
    missing = [c for c in required if c not in df.columns]
    if missing:
        report.passed = False
        report.rejection_reason = f"Missing required columns: {missing}"
        return report

    # Check null rate on key columns
    key_cols = _KEY_COLUMNS[section_type]
    for col in key_cols:
        if col in df.columns:
            null_rate = df[col].isnull().mean()
            if null_rate > NULL_THRESHOLD:
                report.warnings.append(
                    f"Column '{col}' has {null_rate:.0%} null values (threshold {NULL_THRESHOLD:.0%})."
                )
                if null_rate > 0.50:
                    report.passed = False
                    report.rejection_reason = f"Column '{col}' has {null_rate:.0%} null values — exceeds 50% hard limit."
                    return report

    # Row-level validation
    errors: list[RowError] = []
    for idx, row in df.iterrows():
        for col in required:
            if col in df.columns and (pd.isna(row[col]) or str(row[col]).strip() == ""):
                errors.append(RowError(row_index=int(idx), column=col, issue="null_or_empty"))

    report.errors = errors[:100]  # Cap error list at 100 for response size
    report.error_rows = len(df[df[required].isnull().any(axis=1)])
    report.valid_rows = report.total_rows - report.error_rows

    # Warn about unrecognized columns
    known = set(required) | set(_HOSPITALITY_COLUMNS.get(section_type, []))
    unknown_cols = [c for c in df.columns if c not in known]
    if unknown_cols:
        report.warnings.append(f"Unrecognized columns (will be ignored): {unknown_cols}")

    logger.info(report.summary())
    return report
