"""BigQuery audit logger — streams generation and training events to BQ.

All write operations are fire-and-forget (best effort). A failure here
must never break the primary ad generation flow.
"""
import os
import hashlib
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

logger = logging.getLogger("vantage.audit")

_BQ_PROJECT = os.environ.get("GCP_PROJECT_ID", "supple-moon-495404-b0")
_BQ_DATASET = os.environ.get("BQ_DATASET", "vantage")

_bq_client = None


def _get_bq_client():
    global _bq_client
    if _bq_client is None:
        from google.cloud import bigquery
        _bq_client = bigquery.Client(project=_BQ_PROJECT)
    return _bq_client


def _table(name: str) -> str:
    return f"{_BQ_PROJECT}.{_BQ_DATASET}.{name}"


async def log_generation(
    brand_id: str,
    user_id: str,
    platform: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    ad_content: str = "",
    training_run_id: str = "",
    request_type: str = "ad_copy",
) -> None:
    """Stream one row to vantage.generation_audit."""
    content_hash = hashlib.sha256(ad_content.encode()).hexdigest()[:16] if ad_content else ""
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "brand_id": brand_id,
        "user_id": user_id,
        "platform": platform,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
        "ad_content_hash": content_hash,
        "training_run_id": training_run_id,
        "request_type": request_type,
    }
    _insert_rows("generation_audit", [row])


async def log_training_run(
    brand_id: str,
    run_id: str,
    mode: str,
    section_type: str,
    row_count: int,
    quality_score: float,
    status: str,
    model_version: str = "",
) -> None:
    """Stream one row to vantage.training_audit."""
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "brand_id": brand_id,
        "run_id": run_id,
        "mode": mode,
        "section_type": section_type,
        "row_count": row_count,
        "quality_score": quality_score,
        "status": status,
        "model_version": model_version,
    }
    _insert_rows("training_audit", [row])


async def log_safety_event(
    brand_id: str,
    user_id: str,
    category: str,
    severity: str,
    content_hash: str,
    blocked: bool,
) -> None:
    """Stream one row to vantage.safety_events."""
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "brand_id": brand_id,
        "user_id": user_id,
        "category": category,
        "severity": severity,
        "content_hash": content_hash,
        "blocked": blocked,
    }
    _insert_rows("safety_events", [row])


def _insert_rows(table_name: str, rows: list[dict]) -> None:
    try:
        client = _get_bq_client()
        errors = client.insert_rows_json(_table(table_name), rows)
        if errors:
            logger.warning("BQ insert errors for %s: %s", table_name, errors)
    except Exception as exc:
        logger.warning("BQ audit log failed for %s: %s", table_name, exc)
