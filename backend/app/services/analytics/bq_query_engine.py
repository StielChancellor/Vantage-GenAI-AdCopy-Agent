"""Pre-built BigQuery analytical queries for ad performance insights.

Results are cached in Firestore for 24 hours (cache key = query hash + brand_id).
Used by ad_generator.py to inject data-driven context into generation prompts.
"""
from __future__ import annotations

import os
import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("vantage.bq_query")

_PROJECT = os.environ.get("GCP_PROJECT_ID", "supple-moon-495404-b0")
_DATASET = os.environ.get("BQ_DATASET", "vantage")
_CACHE_TTL_HOURS = 24

_bq_client = None


def _get_client():
    global _bq_client
    if _bq_client is None:
        from google.cloud import bigquery
        _bq_client = bigquery.Client(project=_PROJECT)
    return _bq_client


def get_top_performing_headlines(
    brand_id: str,
    platform: str | None = None,
    limit: int = 10,
) -> list[str]:
    """Return top headlines ranked by CTR for this brand."""
    cache_key = _cache_key("top_headlines", brand_id, platform or "all")
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    where_brand = f"brand_id = '{brand_id}'"
    where_platform = f"AND platform = '{platform}'" if platform else ""
    query = f"""
        SELECT headline, AVG(ctr) as avg_ctr
        FROM `{_PROJECT}.{_DATASET}.ad_performance_events`
        WHERE {where_brand} {where_platform}
          AND headline IS NOT NULL AND headline != ''
          AND ctr IS NOT NULL
        GROUP BY headline
        ORDER BY avg_ctr DESC
        LIMIT {limit}
    """
    result = _run_query(query)
    headlines = [row["headline"] for row in result]
    _set_cache(cache_key, headlines)
    return headlines


def get_seasonal_performance(brand_id: str) -> dict[str, float]:
    """Return average CTR by month number (1-12) for this brand."""
    cache_key = _cache_key("seasonal_ctr", brand_id)
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    query = f"""
        SELECT EXTRACT(MONTH FROM date) as month, AVG(ctr) as avg_ctr
        FROM `{_PROJECT}.{_DATASET}.ad_performance_events`
        WHERE brand_id = '{brand_id}'
          AND date IS NOT NULL AND ctr IS NOT NULL
        GROUP BY month
        ORDER BY month
    """
    result = _run_query(query)
    data = {str(int(row["month"])): round(row["avg_ctr"], 4) for row in result}
    _set_cache(cache_key, data)
    return data


def get_platform_insights(brand_id: str) -> dict[str, dict]:
    """Return per-platform summary: avg CTR, top headline, best description."""
    cache_key = _cache_key("platform_insights", brand_id)
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    query = f"""
        SELECT
            platform,
            AVG(ctr) as avg_ctr,
            AVG(roas) as avg_roas,
            COUNT(*) as ad_count
        FROM `{_PROJECT}.{_DATASET}.ad_performance_events`
        WHERE brand_id = '{brand_id}'
          AND platform IS NOT NULL
        GROUP BY platform
        ORDER BY avg_ctr DESC
    """
    result = _run_query(query)
    data = {
        row["platform"]: {
            "avg_ctr": round(row["avg_ctr"] or 0, 4),
            "avg_roas": round(row["avg_roas"] or 0, 2),
            "ad_count": int(row["ad_count"]),
        }
        for row in result
    }
    _set_cache(cache_key, data)
    return data


def get_top_ads_for_scoring(
    brand_id: str,
    platform: str,
    month: int | None = None,
    limit: int = 20,
    campaign_type: str | None = None,
    season: str | None = None,
    min_impressions: int = 100,
) -> list[dict]:
    """Top-performing ads ordered by composite performance_score.

    Filters out low-volume rows (< min_impressions). Optionally filters by
    campaign_type (e.g. 'demandgen_video') and season for retrieval grounding.
    """
    cache_key = _cache_key(
        "top_ads_scoring", brand_id, platform, str(month or 0),
        campaign_type or "any", season or "any", str(min_impressions),
    )
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    where = [f"brand_id = '{_esc(brand_id)}'", f"impressions >= {min_impressions}"]
    if platform and platform != "all":
        where.append(f"platform = '{_esc(platform)}'")
    if campaign_type:
        where.append(f"campaign_type = '{_esc(campaign_type)}'")
    if season:
        where.append(f"season = '{_esc(season)}'")
    if month:
        where.append(f"EXTRACT(MONTH FROM date) = {int(month)}")
    where_clause = " AND ".join(where)

    query = f"""
        SELECT headline, description, ctr, roas, impressions, campaign_type, season,
               performance_score, ad_strength, month, hour_of_day, day_of_week
        FROM `{_PROJECT}.{_DATASET}.ad_performance_events`
        WHERE {where_clause}
          AND COALESCE(performance_score, 0) > 0
        ORDER BY performance_score DESC, impressions DESC
        LIMIT {int(limit)}
    """
    result = _run_query(query)
    _set_cache(cache_key, result)
    return result


def get_pattern_summary(
    brand_id: str,
    campaign_type: str,
    season: str | None = None,
    limit: int = 50,
) -> dict:
    """Aggregate stats over the top performers for a campaign_type × season slice.
    Used by ad_generator to inject style guidance (avg headline length, common
    power words, peak hours/days for push notifications).
    """
    cache_key = _cache_key("pattern_summary", brand_id, campaign_type, season or "any")
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    where = [
        f"brand_id = '{_esc(brand_id)}'",
        f"campaign_type = '{_esc(campaign_type)}'",
        "impressions >= 100",
        "COALESCE(performance_score, 0) > 0",
    ]
    if season:
        where.append(f"season = '{_esc(season)}'")
    where_clause = " AND ".join(where)

    sql = f"""
        SELECT
            AVG(LENGTH(headline)) AS avg_headline_len,
            AVG(LENGTH(description)) AS avg_description_len,
            AVG(ctr) AS avg_ctr,
            AVG(performance_score) AS avg_perf,
            APPROX_TOP_COUNT(hour_of_day, 3) AS top_hours,
            APPROX_TOP_COUNT(day_of_week, 3) AS top_dow,
            COUNT(*) AS sample_size
        FROM `{_PROJECT}.{_DATASET}.ad_performance_events`
        WHERE {where_clause}
    """
    rows = _run_query(sql)
    summary = rows[0] if rows else {}
    _set_cache(cache_key, summary)
    return summary or {}


def _esc(s: str) -> str:
    """Minimal SQL escape for single quotes."""
    return str(s).replace("'", "\\'")


def _run_query(sql: str) -> list[dict]:
    try:
        client = _get_client()
        query_job = client.query(sql)
        return [dict(row) for row in query_job.result()]
    except Exception as exc:
        logger.warning("BQ query failed: %s | SQL: %s", exc, sql[:200])
        return []


def _cache_key(*parts) -> str:
    raw = "|".join(str(p) for p in parts)
    return "bq_cache_" + hashlib.md5(raw.encode()).hexdigest()[:16]


def _get_cache(key: str):
    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
        doc = db.collection("bq_query_cache").document(key).get()
        if doc.exists:
            data = doc.to_dict()
            expires = data.get("expires_at", "")
            if expires and datetime.fromisoformat(expires) > datetime.now(timezone.utc):
                return data.get("result")
    except Exception:
        pass
    return None


def _set_cache(key: str, value) -> None:
    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
        expires = (datetime.now(timezone.utc) + timedelta(hours=_CACHE_TTL_HOURS)).isoformat()
        db.collection("bq_query_cache").document(key).set({
            "result": value,
            "expires_at": expires,
        })
    except Exception:
        pass
