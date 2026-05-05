"""Training data quality + per-record performance scoring.

Two responsibilities:

1. **Per-record performance_score** — `score_records()` mutates each
   NormalizedAdRecord in-place, adding `performance_score`,
   `confidence_weight`, `recency_decay`, `ctr_normalized`, and
   `impression_bucket`. Records with `impressions < IMPRESSION_FLOOR`
   are zeroed out — this is the "high CTR with negligible delivery"
   filter the user demanded.

   performance_score = recency_decay * confidence_weight * ctr_normalized

   - recency_decay   = 0.5 ** (age_days / 180)         (6-month half-life)
   - confidence_weight = log10(1+impr) / log10(1+50000) capped at 1.0
   - ctr_normalized    = min(ctr / median_ctr_for_type, 2.0)

2. **Dataset-level QualityReport** — kept for backward compatibility with
   the legacy DataFrame path. Indexing is blocked if score < 0.4.
"""
from __future__ import annotations

import logging
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta, date
from typing import Iterable

import pandas as pd

from backend.app.services.ingestion.normalized_record import (
    NormalizedAdRecord,
    impression_bucket_for,
)

logger = logging.getLogger("vantage.quality")

# ---------- Per-record scoring constants ----------

IMPRESSION_FLOOR = 100         # Records below this get performance_score = 0
RECENCY_HALFLIFE_DAYS = 180    # 6-month half-life
CONFIDENCE_CAP_IMPRESSIONS = 50_000   # Above this, confidence_weight = 1.0
CTR_NORMALIZE_CAP = 2.0        # Cap normalized CTR at 2× the type median

# Fallback medians used when a campaign_type has no historical data yet.
# Derived from industry benchmarks for hospitality.
DEFAULT_MEDIAN_CTR: dict[str, float] = {
    "pmax": 5.0,
    "demandgen_image": 6.0,
    "demandgen_carousel": 7.0,
    "demandgen_video": 6.5,
    "search_responsive": 8.0,
    "app_installs": 2.5,
    "push_android": 1.2,
    "push_ios": 1.2,
    "generic_ad": 5.0,
    "crm_email": 3.0,
    "brand_usp": 5.0,
}

# ---------- Dataset-level scoring constants ----------
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
    avg_performance_score: float = 0.0
    records_above_floor: int = 0
    warnings: list[str] = field(default_factory=list)
    details: str = ""

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] Quality={self.quality_score:.2f} | "
            f"Recency={self.recency_score:.2f} Completeness={self.completeness_score:.2f} "
            f"Diversity={self.diversity_score:.2f} | "
            f"AvgPerf={self.avg_performance_score:.3f} above-floor={self.records_above_floor}/{self.row_count}"
        )


# ===========================================================================
# Per-record performance scoring (the v2.1 core fix)
# ===========================================================================


def score_records(
    records: list[NormalizedAdRecord],
    type_medians: dict[str, float] | None = None,
    today: date | None = None,
) -> None:
    """Mutate each record in-place with performance_score and components.

    type_medians — optional override of {campaign_type: median_ctr_pct}.
    Falls back to a per-batch median, then DEFAULT_MEDIAN_CTR.
    """
    if not records:
        return
    today = today or date.today()
    medians = _compute_medians(records, type_medians)

    for rec in records:
        # Impression bucket (always set, used for retrieval filtering)
        rec.impression_bucket = impression_bucket_for(rec.impressions or 0)

        # Hard floor — zero out low-volume records
        if (rec.impressions or 0) < IMPRESSION_FLOOR:
            rec.recency_decay = 0.0
            rec.confidence_weight = 0.0
            rec.ctr_normalized = 0.0
            rec.performance_score = 0.0
            continue

        # Recency decay
        if rec.flight_date:
            age_days = max(0, (today - rec.flight_date).days)
        else:
            age_days = 0  # Unknown date = treat as fresh
        rec.recency_decay = 0.5 ** (age_days / RECENCY_HALFLIFE_DAYS)

        # Confidence weight from impressions (log-scaled)
        rec.confidence_weight = min(
            1.0,
            math.log10(1 + rec.impressions) / math.log10(1 + CONFIDENCE_CAP_IMPRESSIONS),
        )

        # Normalized CTR (relative to per-type median)
        median = medians.get(rec.campaign_type, DEFAULT_MEDIAN_CTR.get(rec.campaign_type, 5.0))
        if median <= 0:
            median = 1.0
        rec.ctr_normalized = min(rec.ctr / median, CTR_NORMALIZE_CAP)

        rec.performance_score = round(
            rec.recency_decay * rec.confidence_weight * rec.ctr_normalized, 6
        )


def _compute_medians(
    records: list[NormalizedAdRecord],
    overrides: dict[str, float] | None,
) -> dict[str, float]:
    """Per-campaign-type CTR medians. Computed from the batch when ≥5 records
    exist for that type; otherwise falls back to DEFAULT_MEDIAN_CTR."""
    overrides = overrides or {}
    by_type: dict[str, list[float]] = defaultdict(list)
    for r in records:
        if r.ctr and (r.impressions or 0) >= IMPRESSION_FLOOR:
            by_type[r.campaign_type].append(r.ctr)

    medians: dict[str, float] = {}
    for ct, vals in by_type.items():
        if len(vals) >= 5:
            medians[ct] = statistics.median(vals)
        else:
            medians[ct] = DEFAULT_MEDIAN_CTR.get(ct, 5.0)
    medians.update(overrides)
    return medians


def quality_report_from_records(
    records: list[NormalizedAdRecord],
    section_type: str,
) -> QualityReport:
    """Generate a dataset-level QualityReport from already-scored records."""
    n = len(records)
    if n == 0:
        return QualityReport(
            section_type=section_type, row_count=0, quality_score=0.0, passed=False,
            details="empty record set",
        )

    above_floor = sum(1 for r in records if r.performance_score > 0)
    avg_perf = sum(r.performance_score for r in records) / n
    recency = sum(r.recency_decay for r in records) / n
    completeness = sum(
        1 for r in records if r.headline and r.description
    ) / n
    headlines = [r.headline.lower() for r in records if r.headline]
    diversity = (len(set(headlines)) / len(headlines)) if headlines else 0.5

    quality_score = round(
        RECENCY_WEIGHT * recency
        + COMPLETENESS_WEIGHT * completeness
        + DIVERSITY_WEIGHT * min(diversity * 1.2, 1.0),
        4,
    )
    passed = quality_score >= MIN_QUALITY_SCORE and above_floor > 0

    warnings: list[str] = []
    if above_floor / n < 0.3:
        warnings.append(
            f"Only {above_floor}/{n} records cleared the {IMPRESSION_FLOOR}-impression floor. "
            "Most uploaded data is too low-volume to be useful for training."
        )
    if recency < 0.3:
        warnings.append(f"Average recency_decay is {recency:.2f} — most data is older than 12 months.")
    if diversity < 0.5:
        warnings.append(f"High duplication: {1 - diversity:.0%} of headlines are duplicates.")

    report = QualityReport(
        section_type=section_type,
        row_count=n,
        quality_score=quality_score,
        passed=passed,
        recency_score=round(recency, 4),
        completeness_score=round(completeness, 4),
        diversity_score=round(min(diversity * 1.2, 1.0), 4),
        avg_performance_score=round(avg_perf, 6),
        records_above_floor=above_floor,
        warnings=warnings,
        details=f"impression_floor={IMPRESSION_FLOOR} half_life={RECENCY_HALFLIFE_DAYS}d",
    )
    logger.info(report.summary())
    return report


# ===========================================================================
# Legacy dataset-level scoring (kept for ad_performance/brand_usp/crm path)
# ===========================================================================


def score_training_data(df: pd.DataFrame, section_type: str) -> QualityReport:
    """Legacy DataFrame-based scoring. Use score_records() for v2.1 path."""
    warnings: list[str] = []
    recency = _score_recency(df, warnings)
    completeness = _score_completeness(df, section_type, warnings)
    diversity = _score_diversity(df, section_type, warnings)
    total = round(
        RECENCY_WEIGHT * recency
        + COMPLETENESS_WEIGHT * completeness
        + DIVERSITY_WEIGHT * diversity,
        4,
    )
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
    return report


def _score_recency(df: pd.DataFrame, warnings: list[str]) -> float:
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
            warnings.append(f"Only {fresh_rate:.0%} of rows are from the last {STALE_MONTHS} months.")
        return float(fresh_rate)
    except Exception:
        return 0.5


def _score_completeness(df: pd.DataFrame, section_type: str, warnings: list[str]) -> float:
    key_cols_map = {
        "ad_performance": ["headline", "description", "ctr"],
        "brand_usp": ["usp", "category"],
        "crm_performance": ["channel", "message", "open_rate"],
    }
    key_cols = [c for c in key_cols_map.get(section_type, []) if c in df.columns]
    if not key_cols:
        return 0.7
    completeness = df[key_cols].notnull().all(axis=1).mean()
    if completeness < 0.8:
        warnings.append(f"Completeness is {completeness:.0%} — some key fields are missing.")
    return float(completeness)


def _score_diversity(df: pd.DataFrame, section_type: str, warnings: list[str]) -> float:
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
    return float(min(unique_rate * 1.2, 1.0))
