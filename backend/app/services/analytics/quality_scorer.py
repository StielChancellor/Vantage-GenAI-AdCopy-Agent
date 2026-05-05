"""Training data quality scorer.

Evaluates a training dataset before it is indexed. Returns a QualityReport
with a score between 0.0 and 1.0. Indexing is blocked if score < 0.4.

Scoring dimensions:
  - Recency (40%): penalizes data older than 18 months
  - Completeness (30%): fraction of non-null key fields
  - Diversity (30%): estimated headline uniqueness (low duplication = high score)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import pandas as pd

logger = logging.getLogger("vantage.quality")

MIN_QUALITY_SCORE = 0.4
RECENCY_WEIGHT = 0.4
COMPLETENESS_WEIGHT = 0.3
DIVERSITY_WEIGHT = 0.3

STALE_MONTHS = 18


@dataclass
class QualityReport:
    section_type: str
    row_count: int
    quality_score: float
    passed: bool
    recency_score: float = 0.0
    completeness_score: float = 0.0
    diversity_score: float = 0.0
    warnings: list[str] = field(default_factory=list)
    details: str = ""

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] Quality={self.quality_score:.2f} | "
            f"Recency={self.recency_score:.2f} | "
            f"Completeness={self.completeness_score:.2f} | "
            f"Diversity={self.diversity_score:.2f}"
        )


def score_training_data(df: pd.DataFrame, section_type: str) -> QualityReport:
    """Compute a quality score for a training DataFrame.

    Args:
        df: Pre-validated DataFrame (run csv_validator first).
        section_type: 'ad_performance' | 'brand_usp' | 'crm_performance'

    Returns:
        QualityReport with score and dimension breakdowns.
    """
    warnings: list[str] = []

    recency = _score_recency(df, warnings)
    completeness = _score_completeness(df, section_type, warnings)
    diversity = _score_diversity(df, section_type, warnings)

    total = (
        RECENCY_WEIGHT * recency
        + COMPLETENESS_WEIGHT * completeness
        + DIVERSITY_WEIGHT * diversity
    )
    total = round(total, 4)
    passed = total >= MIN_QUALITY_SCORE

    report = QualityReport(
        section_type=section_type,
        row_count=len(df),
        quality_score=total,
        passed=passed,
        recency_score=round(recency, 4),
        completeness_score=round(completeness, 4),
        diversity_score=round(diversity, 4),
        warnings=warnings,
        details=f"Min threshold: {MIN_QUALITY_SCORE}",
    )

    logger.info(report.summary())
    if not passed:
        logger.warning(
            "Training data quality below threshold (%.2f < %.2f). Indexing blocked.",
            total,
            MIN_QUALITY_SCORE,
        )
    return report


def _score_recency(df: pd.DataFrame, warnings: list[str]) -> float:
    """0.0 = all data is stale, 1.0 = all data is fresh."""
    if "date" not in df.columns:
        warnings.append("No 'date' column — recency score defaulted to 0.5.")
        return 0.5

    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_MONTHS * 30)
    try:
        dates = pd.to_datetime(df["date"], errors="coerce")
        valid = dates.dropna()
        if valid.empty:
            warnings.append("Could not parse any dates — recency score defaulted to 0.5.")
            return 0.5
        fresh_rate = (valid.dt.tz_localize("UTC", ambiguous="NaT") > cutoff).mean()
        if fresh_rate < 0.5:
            warnings.append(
                f"Only {fresh_rate:.0%} of rows are from the last {STALE_MONTHS} months."
            )
        return float(fresh_rate)
    except Exception:
        return 0.5


def _score_completeness(df: pd.DataFrame, section_type: str, warnings: list[str]) -> float:
    """Fraction of non-null values across key columns."""
    key_cols_map = {
        "ad_performance": ["headline", "description", "ctr"],
        "brand_usp": ["usp", "category"],
        "crm_performance": ["channel", "message", "open_rate"],
    }
    key_cols = [c for c in key_cols_map.get(section_type, []) if c in df.columns]
    if not key_cols:
        return 0.7  # No key cols to check, assume moderate

    completeness = df[key_cols].notnull().all(axis=1).mean()
    if completeness < 0.8:
        warnings.append(f"Completeness is {completeness:.0%} — some key fields are missing.")
    return float(completeness)


def _score_diversity(df: pd.DataFrame, section_type: str, warnings: list[str]) -> float:
    """Estimate uniqueness. High duplication = low diversity = low score."""
    if section_type == "ad_performance" and "headline" in df.columns:
        texts = df["headline"].dropna().astype(str).str.lower()
    elif section_type == "brand_usp" and "usp" in df.columns:
        texts = df["usp"].dropna().astype(str).str.lower()
    elif section_type == "crm_performance" and "message" in df.columns:
        texts = df["message"].dropna().astype(str).str.lower()
    else:
        return 0.7

    if texts.empty:
        return 0.5

    unique_rate = texts.nunique() / len(texts)
    if unique_rate < 0.5:
        warnings.append(f"High duplication detected — only {unique_rate:.0%} unique texts.")
    return float(min(unique_rate * 1.2, 1.0))  # Slight boost for near-unique datasets
