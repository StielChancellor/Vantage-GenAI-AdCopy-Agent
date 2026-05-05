"""BigQuery writer for historical ad performance data.

Called during CSV ingestion to persist each row to BQ for analytics queries.
Uses streaming inserts (not batch load jobs) for low-latency writes.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, date

import pandas as pd

logger = logging.getLogger("vantage.bq")

_PROJECT = os.environ.get("GCP_PROJECT_ID", "supple-moon-495404-b0")
_DATASET = os.environ.get("BQ_DATASET", "vantage")

_bq_client = None


def _get_client():
    global _bq_client
    if _bq_client is None:
        from google.cloud import bigquery
        _bq_client = bigquery.Client(project=_PROJECT)
    return _bq_client


def _table(name: str) -> str:
    return f"{_PROJECT}.{_DATASET}.{name}"


async def write_ad_performance_rows(
    df: pd.DataFrame,
    brand_id: str,
    training_run_id: str,
    model_version: str = "gemini-3.1-pro-preview",
) -> None:
    """Stream historical ad performance rows to BigQuery.

    Silently drops rows that fail validation rather than failing the batch.
    """
    rows = []
    today = date.today().isoformat()

    for _, row in df.iterrows():
        bq_row: dict = {
            "brand_id": brand_id,
            "platform": str(row.get("platform", "unknown"))[:50],
            "campaign_id": str(row.get("campaign_id", ""))[:100],
            "headline": str(row.get("headline", ""))[:500],
            "description": str(row.get("description", ""))[:1000],
            "ctr": _safe_float(row.get("ctr")),
            "cpc": _safe_float(row.get("cpc")),
            "roas": _safe_float(row.get("roas")),
            "impressions": _safe_int(row.get("impressions")),
            "date": str(row.get("date", today))[:10],
            "training_run_id": training_run_id,
            "model_version": model_version,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(bq_row)

    if not rows:
        return

    _insert_rows("ad_performance_events", rows)


def _insert_rows(table_name: str, rows: list[dict]) -> None:
    try:
        client = _get_client()
        errors = client.insert_rows_json(_table(table_name), rows)
        if errors:
            logger.warning("BQ insert errors for %s: %s", table_name, errors[:3])
        else:
            logger.info("Wrote %d rows to %s.", len(rows), table_name)
    except Exception as exc:
        logger.error("BQ write failed for %s: %s", table_name, exc)


def _safe_float(val) -> float | None:
    try:
        return float(val) if val is not None and str(val).strip() != "" else None
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> int | None:
    try:
        return int(float(val)) if val is not None and str(val).strip() != "" else None
    except (ValueError, TypeError):
        return None
