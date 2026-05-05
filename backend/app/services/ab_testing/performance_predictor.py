"""A/B performance predictor — scores generated ad variants without ML model training.

Score formula:
  0.4 × semantic similarity to top historical ads
  0.3 × structural pattern match (length compliance, CTA presence, power words)
  0.3 × seasonality alignment

Returns a 0.0–1.0 score and human-readable explanation for each variant.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_POWER_WORDS = {
    "exclusive", "limited", "save", "free", "now", "today", "guaranteed",
    "luxury", "discover", "escape", "award", "best", "celebrate", "offer",
    "deal", "experience", "indulge", "book", "complimentary", "special",
}

_CTA_PATTERNS = re.compile(
    r"\b(book|reserve|explore|discover|save|get|claim|enjoy|call|visit|try|start)\b",
    re.IGNORECASE,
)


@dataclass
class VariantScore:
    platform: str
    headline_sample: str
    score: float
    semantic_score: float
    structural_score: float
    seasonal_score: float
    explanation: str


def score_variant(
    headlines: list[str],
    descriptions: list[str],
    platform: str,
    brand_id: str,
    flight_date: date | str | None = None,
) -> VariantScore:
    """Score a single ad variant.

    Returns a VariantScore with component breakdowns and explanation.
    """
    from backend.app.services.seasonal.season_context import get_seasonal_context

    # Structural score
    structural = _score_structural(headlines, descriptions, platform)

    # Seasonal score
    seasonal_contexts = get_seasonal_context(flight_date)
    seasonal = _score_seasonal(headlines + descriptions, seasonal_contexts)

    # Semantic score (BQ-based — async would complicate this; use sync BQ cache)
    semantic = _score_semantic_sync(headlines, descriptions, brand_id, platform, flight_date)

    total = round(0.4 * semantic + 0.3 * structural + 0.3 * seasonal, 4)

    explanation_parts = []
    if semantic >= 0.7:
        explanation_parts.append("Strong match with historical top performers")
    elif semantic >= 0.4:
        explanation_parts.append("Moderate similarity to historical top ads")
    else:
        explanation_parts.append("Low similarity to historical patterns")

    if structural >= 0.7:
        explanation_parts.append("Good CTA and power word usage")
    if seasonal >= 0.7:
        explanation_parts.append("Strong seasonal relevance")
    elif seasonal_contexts:
        explanation_parts.append(f"Could better leverage {seasonal_contexts[0].name} season")

    return VariantScore(
        platform=platform,
        headline_sample=headlines[0] if headlines else "",
        score=total,
        semantic_score=round(semantic, 4),
        structural_score=round(structural, 4),
        seasonal_score=round(seasonal, 4),
        explanation=" | ".join(explanation_parts) or "Standard quality",
    )


def _score_structural(headlines: list[str], descriptions: list[str], platform: str) -> float:
    """Score based on CTA presence, power words, and character compliance."""
    all_text = " ".join(headlines + descriptions)

    # CTA presence
    has_cta = bool(_CTA_PATTERNS.search(all_text))

    # Power word density
    words = set(all_text.lower().split())
    power_word_count = len(words & _POWER_WORDS)
    power_density = min(power_word_count / max(len(headlines), 1), 1.0)

    # Length compliance (rough check: no headline > 50 chars is a bad sign)
    avg_hl_len = sum(len(h) for h in headlines) / max(len(headlines), 1)
    length_ok = avg_hl_len <= 45  # conservative limit

    score = (
        (0.4 if has_cta else 0.0)
        + 0.4 * min(power_density * 2, 1.0)
        + (0.2 if length_ok else 0.05)
    )
    return min(score, 1.0)


def _score_seasonal(texts: list[str], contexts) -> float:
    """Score based on how many seasonal keywords appear in the ad text."""
    if not contexts:
        return 0.5  # Neutral — no season active

    all_text = " ".join(texts).lower()
    total_keywords = sum(len(ctx.keywords) for ctx in contexts)
    if total_keywords == 0:
        return 0.5

    matches = sum(
        1 for ctx in contexts for kw in ctx.keywords
        if kw.lower() in all_text
    )
    return min(matches / max(total_keywords * 0.3, 1), 1.0)


def _score_semantic_sync(
    headlines: list[str],
    descriptions: list[str],
    brand_id: str,
    platform: str,
    flight_date,
) -> float:
    """Synchronous semantic similarity via BQ top ads (uses Firestore cache)."""
    try:
        from backend.app.services.analytics.bq_query_engine import get_top_ads_for_scoring
        import datetime

        month = None
        if flight_date:
            if isinstance(flight_date, str):
                try:
                    month = datetime.datetime.fromisoformat(flight_date).month
                except Exception:
                    pass
            elif hasattr(flight_date, "month"):
                month = flight_date.month

        top_ads = get_top_ads_for_scoring(brand_id, platform, month=month, limit=20)
        if not top_ads:
            return 0.5

        # Simple token overlap similarity (no vectors needed here)
        query_tokens = set(" ".join(headlines + descriptions).lower().split())
        scores = []
        for ad in top_ads:
            ref_tokens = set(
                (str(ad.get("headline", "")) + " " + str(ad.get("description", ""))).lower().split()
            )
            if not ref_tokens:
                continue
            overlap = len(query_tokens & ref_tokens) / max(len(query_tokens | ref_tokens), 1)
            # Weight by CTR
            ctr_weight = min((ad.get("ctr") or 0) / 10, 1.0)  # normalize assuming max CTR ~10%
            scores.append(overlap * (0.7 + 0.3 * ctr_weight))

        return sum(scores) / len(scores) if scores else 0.5
    except Exception:
        return 0.5
