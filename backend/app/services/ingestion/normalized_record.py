"""Shared NormalizedAdRecord type — output of all source-specific CSV adapters.

Adapters convert vendor-specific schemas (Google Ads Editor wide format,
MoEngage push export, generic ad_performance) into a uniform list of these
records. Downstream pipeline (embedder, BQ writer, quality scorer) consumes
only this type.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any


# Canonical campaign type enum. Adapters MUST emit one of these values.
# Used as a Vector Search restrict namespace and BQ column.
CAMPAIGN_TYPES = {
    # Google Ads
    "pmax",                  # Performance Max
    "demandgen_image",       # Demand Gen image ad
    "demandgen_carousel",    # Demand Gen carousel ad
    "demandgen_video",       # Demand Gen video ad
    "search_responsive",     # Responsive search ad
    "app_installs",          # Mobile app installs ad
    # MoEngage / push channels
    "push_android",
    "push_ios",
    # Generic / fallback
    "generic_ad",
    "crm_email",
    "brand_usp",
}


@dataclass
class NormalizedAdRecord:
    """A single performance-tagged ad/notification record ready for the pipeline."""

    # Required content
    headline: str
    description: str
    campaign_type: str          # one of CAMPAIGN_TYPES

    # Required metrics
    impressions: int = 0
    ctr: float = 0.0            # percentage, e.g. 6.79 for "6.79%"

    # Optional perf metrics (Google Ads / search)
    cpc: float | None = None
    roas: float | None = None
    ad_strength: str | None = None   # "Excellent" | "Good" | "Average" | "Poor"

    # Temporal signals (UTC)
    sent_at: datetime | None = None
    flight_date: date | None = None  # date the ad/campaign was active
    hour_of_day: int | None = None   # 0-23
    day_of_week: int | None = None   # 0=Mon, 6=Sun
    month: int | None = None         # 1-12
    season: str | None = None        # 'spring' | 'summer' | 'monsoon' | 'autumn' | 'winter'

    # Source-specific extras (kept for prompt enrichment, not for filtering)
    business_name: str = ""
    card_headlines: list[str] = field(default_factory=list)
    long_headlines: list[str] = field(default_factory=list)
    raw_ad_type: str = ""       # original "Ad type" cell from Google Ads, for traceability

    # Computed downstream (set by quality_scorer)
    performance_score: float = 0.0
    confidence_weight: float = 0.0
    recency_decay: float = 1.0
    ctr_normalized: float = 0.0
    impression_bucket: str = "low"   # 'low' | 'mid' | 'high' | 'mass'

    def as_embedding_text(self) -> str:
        """The exact string that gets embedded. Campaign-type prefix is critical
        for sub-type discrimination in the vector space."""
        return f"[{self.campaign_type}] {self.headline} — {self.description}".strip(" —")

    def as_metadata(self, brand_id: str, training_run_id: str, section_type: str) -> dict[str, Any]:
        """Metadata attached to each Vector Search vector. Every field listed
        here must also be configured as a Vector Search restrict namespace if
        we want query-time filtering on it."""
        return {
            "brand_id": brand_id,
            "training_run_id": training_run_id,
            "section_type": section_type,
            "campaign_type": self.campaign_type,
            "month": str(self.month) if self.month else "",
            "season": self.season or "",
            "hour_of_day": str(self.hour_of_day) if self.hour_of_day is not None else "",
            "day_of_week": str(self.day_of_week) if self.day_of_week is not None else "",
            "impression_bucket": self.impression_bucket,
            "ad_strength": self.ad_strength or "",
            "performance_score": round(self.performance_score, 4),
        }

    def as_bq_row(self, brand_id: str, training_run_id: str, model_version: str) -> dict[str, Any]:
        """Row shape for vantage.ad_performance_events streaming insert."""
        d = self.flight_date or (self.sent_at.date() if self.sent_at else date.today())
        return {
            "brand_id": brand_id,
            "platform": _platform_from_campaign_type(self.campaign_type),
            "campaign_id": "",
            "headline": (self.headline or "")[:500],
            "description": (self.description or "")[:1000],
            "ctr": float(self.ctr) if self.ctr else None,
            "cpc": self.cpc,
            "roas": self.roas,
            "impressions": int(self.impressions) if self.impressions else None,
            "date": str(d)[:10],
            "training_run_id": training_run_id,
            "model_version": model_version,
            "ingested_at": datetime.utcnow().isoformat(),
            "campaign_type": self.campaign_type,
            "ad_strength": self.ad_strength,
            "hour_of_day": self.hour_of_day,
            "day_of_week": self.day_of_week,
            "month": self.month,
            "season": self.season,
            "performance_score": round(self.performance_score, 6) if self.performance_score else 0.0,
            "confidence_weight": round(self.confidence_weight, 6),
            "recency_decay": round(self.recency_decay, 6),
            "ctr_normalized": round(self.ctr_normalized, 6),
        }

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.sent_at:
            d["sent_at"] = self.sent_at.isoformat()
        if self.flight_date:
            d["flight_date"] = self.flight_date.isoformat()
        return d


def _platform_from_campaign_type(ct: str) -> str:
    """Map canonical campaign_type back to a coarse 'platform' for legacy BQ filters."""
    if ct.startswith("push_"):
        return "moengage_push"
    if ct in {"pmax", "demandgen_image", "demandgen_carousel", "demandgen_video", "search_responsive", "app_installs"}:
        return "google_ads"
    if ct == "crm_email":
        return "email"
    return "unknown"


def season_for_month(month: int) -> str:
    """Indian hospitality seasonality. Aligned with season_context.py."""
    if month in (3, 4):
        return "spring"
    if month in (5, 6):
        return "summer"
    if month in (7, 8, 9):
        return "monsoon"
    if month in (10, 11):
        return "autumn"
    return "winter"  # 12, 1, 2


def impression_bucket_for(impressions: int) -> str:
    if impressions >= 100_000:
        return "mass"
    if impressions >= 10_000:
        return "high"
    if impressions >= 1_000:
        return "mid"
    return "low"
