"""CSV schema validation + adapter dispatch.

Two paths:
  A. Adapter-based (preferred for new sources):
     section_type = 'google_ads_export' | 'moengage_push'
     Auto-detects schema, then delegates to a NormalizedAdRecord adapter.
     The downstream pipeline consumes NormalizedAdRecord — never raw CSV.
  B. Legacy generic schemas (kept for backward compatibility):
     section_type = 'ad_performance' | 'brand_usp' | 'crm_performance'
     Validates required columns and lets the legacy DataFrame path through.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger("vantage.ingestion")

# Required columns per legacy section type
_REQUIRED_COLUMNS: dict[str, list[str]] = {
    "ad_performance": ["headline", "description", "ctr"],
    "brand_usp": ["usp", "category"],
    "crm_performance": ["channel", "message", "open_rate"],
}

# Key columns — reject if >50% null on these
_KEY_COLUMNS: dict[str, list[str]] = {
    "ad_performance": ["headline", "ctr"],
    "brand_usp": ["usp"],
    "crm_performance": ["channel", "message"],
}

_HOSPITALITY_COLUMNS: dict[str, list[str]] = {
    "ad_performance": ["platform", "campaign_id", "cvr", "impressions", "spend", "adr", "revpar"],
    "brand_usp": ["property_code", "priority", "verified"],
    "crm_performance": ["click_rate", "conversion_rate", "send_date", "audience_segment"],
}

# Adapter-driven section types (these skip column normalization — adapters
# read original column names with capitalisation, spaces, parens preserved).
ADAPTER_SECTION_TYPES = {"google_ads_export", "moengage_push"}

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
    detected_format: str = ""

    def summary(self) -> str:
        return (
            f"[{self.section_type}] {self.valid_rows}/{self.total_rows} rows valid. "
            f"Passed: {self.passed}. "
            + (f"Detected: {self.detected_format}. " if self.detected_format else "")
            + (f"Rejected: {self.rejection_reason}" if not self.passed else "")
        )


def validate_csv(df: pd.DataFrame, section_type: str) -> ValidationReport:
    """Validate a DataFrame. For adapter section types, runs format detection
    BEFORE column normalization to keep original column names intact for the
    adapter."""
    report = ValidationReport(
        section_type=section_type,
        total_rows=len(df),
        valid_rows=0,
        error_rows=0,
    )

    if df.empty:
        report.passed = False
        report.rejection_reason = "CSV is empty."
        return report

    # ---------- Adapter-driven path ----------
    if section_type in ADAPTER_SECTION_TYPES:
        from backend.app.services.ingestion.adapters import (
            detect_google_ads,
            detect_moengage,
        )
        if section_type == "google_ads_export":
            if not detect_google_ads(df):
                report.passed = False
                report.rejection_reason = (
                    "Does not look like a Google Ads Editor export. "
                    "Required columns: 'Ad type', 'Impr.', 'CTR'."
                )
                return report
            report.detected_format = "google_ads_editor"
        elif section_type == "moengage_push":
            if not detect_moengage(df):
                report.passed = False
                report.rejection_reason = (
                    "Does not look like a MoEngage push export. "
                    "Required columns: 'Campaign Sent Time', 'All Platform Impressions'."
                )
                return report
            report.detected_format = "moengage_push"

        report.valid_rows = report.total_rows
        report.passed = True
        logger.info(report.summary())
        return report

    # ---------- Legacy generic path ----------
    if section_type not in _REQUIRED_COLUMNS:
        report.passed = False
        report.rejection_reason = f"Unknown section_type: {section_type}"
        return report

    # Normalize column names (legacy path only)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    required = _REQUIRED_COLUMNS[section_type]
    missing = [c for c in required if c not in df.columns]
    if missing:
        report.passed = False
        report.rejection_reason = f"Missing required columns: {missing}"
        return report

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
                    report.rejection_reason = (
                        f"Column '{col}' has {null_rate:.0%} null values — exceeds 50% hard limit."
                    )
                    return report

    errors: list[RowError] = []
    for idx, row in df.iterrows():
        for col in required:
            if col in df.columns and (pd.isna(row[col]) or str(row[col]).strip() == ""):
                errors.append(RowError(row_index=int(idx), column=col, issue="null_or_empty"))

    report.errors = errors[:100]
    report.error_rows = len(df[df[required].isnull().any(axis=1)])
    report.valid_rows = report.total_rows - report.error_rows

    known = set(required) | set(_HOSPITALITY_COLUMNS.get(section_type, []))
    unknown_cols = [c for c in df.columns if c not in known]
    if unknown_cols:
        report.warnings.append(f"Unrecognized columns (will be ignored): {unknown_cols}")

    logger.info(report.summary())
    return report
