"""Async batch CSV processor.

Two paths:
  • Adapter path (v2.1): section_type ∈ {google_ads_export, moengage_push}.
    The whole file is parsed, scored, embedded, and written in one shot
    (chunking is unnecessary because the adapter has already exploded the
    wide rows into per-asset records — we score & embed in 50-record batches).
  • Legacy path (v2.0): section_type ∈ {ad_performance, brand_usp, crm_performance}.
    Old DataFrame chunked path; preserved for backwards compatibility.

Triggered by Cloud Tasks after a CSV is uploaded to GCS.
"""
from __future__ import annotations

import io
import asyncio
import logging
import uuid
from datetime import datetime, timezone

import pandas as pd

logger = logging.getLogger("vantage.ingestion")

CHUNK_SIZE = 50

# Adapter section_types, mirrors csv_validator.ADAPTER_SECTION_TYPES
ADAPTER_SECTION_TYPES = {"google_ads_export", "moengage_push"}


async def process_csv_from_gcs(
    gcs_uri: str,
    section_type: str,
    brand_id: str,
    training_run_id: str,
    job_id: str | None = None,
) -> dict:
    """Main entry point. Downloads CSV, validates, processes, returns status."""
    job_id = job_id or str(uuid.uuid4())
    db = _get_firestore()

    _update_job(db, job_id, {
        "status": "running",
        "gcs_uri": gcs_uri,
        "section_type": section_type,
        "brand_id": brand_id,
        "training_run_id": training_run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "processed_rows": 0,
        "total_rows": 0,
        "errors": [],
    })

    try:
        df = await _read_csv_from_gcs(gcs_uri)
    except Exception as exc:
        _update_job(db, job_id, {"status": "failed", "error": str(exc)})
        return {"status": "failed", "error": str(exc)}

    from backend.app.services.ingestion.csv_validator import validate_csv
    report = validate_csv(df, section_type)
    if not report.passed:
        _update_job(db, job_id, {"status": "failed", "error": report.rejection_reason})
        return {"status": "failed", "error": report.rejection_reason}

    if section_type in ADAPTER_SECTION_TYPES:
        return await _run_adapter_path(df, section_type, brand_id, training_run_id, job_id, db)

    return await _run_legacy_path(df, section_type, brand_id, training_run_id, job_id, db)


# ===========================================================================
# v2.1 adapter path
# ===========================================================================


async def _run_adapter_path(
    df: pd.DataFrame,
    section_type: str,
    brand_id: str,
    training_run_id: str,
    job_id: str,
    db,
) -> dict:
    from backend.app.services.ingestion.adapters import parse_google_ads, parse_moengage
    from backend.app.services.analytics.quality_scorer import (
        score_records,
        quality_report_from_records,
    )
    from backend.app.services.embedding.vertex_embedder import embed_records
    from backend.app.services.analytics.bq_writer import write_normalized_records

    if section_type == "google_ads_export":
        records = parse_google_ads(df)
    else:
        records = parse_moengage(df)

    total_input_rows = len(df)
    _update_job(db, job_id, {
        "total_rows": len(records),
        "source_rows": total_input_rows,
        "format": section_type,
    })

    if not records:
        _update_job(db, job_id, {
            "status": "completed",
            "processed_rows": 0,
            "warning": "Adapter produced 0 records — input may be empty or fully zero-impression.",
        })
        return {"status": "completed", "job_id": job_id, "total_rows": 0, "processed_rows": 0}

    # 1. Score every record (mutates in-place)
    score_records(records)
    quality = quality_report_from_records(records, section_type)

    # 2. Persist to BigQuery (all records, including below-floor for archival)
    try:
        await write_normalized_records(records, brand_id, training_run_id)
    except Exception as exc:
        logger.warning("BQ write failed for job %s: %s", job_id, exc)

    # 3. Embed + index only records above the impression floor (perf_score > 0)
    eligible = [r for r in records if r.performance_score > 0]
    embedded_count = 0
    errors: list[str] = []

    for i in range(0, len(eligible), CHUNK_SIZE):
        chunk = eligible[i:i + CHUNK_SIZE]
        try:
            docs = await embed_records(
                chunk,
                brand_id=brand_id,
                training_run_id=training_run_id,
                section_type=section_type,
            )
            embedded_count += len(docs)
            _update_job(db, job_id, {"processed_rows": embedded_count})
        except Exception as exc:
            logger.error("Embed chunk failed for job %s: %s", job_id, exc)
            errors.append(str(exc))

    final_status = "completed" if not errors else "completed_with_errors"
    _update_job(db, job_id, {
        "status": final_status,
        "processed_rows": embedded_count,
        "embedded_rows": embedded_count,
        "skipped_low_volume": len(records) - len(eligible),
        "quality_score": quality.quality_score,
        "quality_passed": quality.passed,
        "quality_warnings": quality.warnings,
        "errors": errors[:20],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "status": final_status,
        "job_id": job_id,
        "source_rows": total_input_rows,
        "total_rows": len(records),
        "processed_rows": embedded_count,
        "skipped_low_volume": len(records) - len(eligible),
        "quality_score": quality.quality_score,
        "error_count": len(errors),
    }


# ===========================================================================
# Legacy v2.0 DataFrame path
# ===========================================================================


async def _run_legacy_path(
    df: pd.DataFrame,
    section_type: str,
    brand_id: str,
    training_run_id: str,
    job_id: str,
    db,
) -> dict:
    total_rows = len(df)
    _update_job(db, job_id, {"total_rows": total_rows})

    chunks = [df.iloc[i:i + CHUNK_SIZE] for i in range(0, total_rows, CHUNK_SIZE)]
    chunk_tasks = [
        _process_legacy_chunk(chunk, section_type, brand_id, training_run_id, idx)
        for idx, chunk in enumerate(chunks)
    ]
    results = await asyncio.gather(*chunk_tasks, return_exceptions=True)

    processed = 0
    all_errors: list[str] = []
    for result in results:
        if isinstance(result, Exception):
            all_errors.append(str(result))
        else:
            processed += result.get("rows", 0)
            _update_job(db, job_id, {"processed_rows": processed})

    if all_errors:
        await _write_failed_rows(job_id, all_errors)

    final_status = "completed" if not all_errors else "completed_with_errors"
    _update_job(db, job_id, {
        "status": final_status,
        "processed_rows": processed,
        "errors": all_errors[:20],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "status": final_status,
        "job_id": job_id,
        "total_rows": total_rows,
        "processed_rows": processed,
        "error_count": len(all_errors),
    }


async def _process_legacy_chunk(
    chunk: pd.DataFrame,
    section_type: str,
    brand_id: str,
    training_run_id: str,
    chunk_idx: int,
) -> dict:
    from backend.app.services.embedding.vertex_embedder import embed_dataframe_chunk
    from backend.app.services.analytics.bq_writer import write_ad_performance_rows

    texts = _legacy_chunk_to_texts(chunk, section_type)
    await embed_dataframe_chunk(texts, brand_id=brand_id, training_run_id=training_run_id)
    if section_type == "ad_performance":
        await write_ad_performance_rows(chunk, brand_id=brand_id, training_run_id=training_run_id)
    return {"rows": len(chunk), "chunk_idx": chunk_idx}


def _legacy_chunk_to_texts(chunk: pd.DataFrame, section_type: str) -> list[str]:
    texts = []
    for _, row in chunk.iterrows():
        if section_type == "ad_performance":
            text = f"Headline: {row.get('headline', '')} | Description: {row.get('description', '')} | CTR: {row.get('ctr', '')}%"
        elif section_type == "brand_usp":
            text = f"USP: {row.get('usp', '')} | Category: {row.get('category', '')}"
        else:
            text = f"Channel: {row.get('channel', '')} | Message: {row.get('message', '')} | Open Rate: {row.get('open_rate', '')}%"
        texts.append(text.strip())
    return texts


# ===========================================================================
# Helpers
# ===========================================================================


async def _read_csv_from_gcs(gcs_uri: str) -> pd.DataFrame:
    from google.cloud import storage
    path = gcs_uri.replace("gs://", "")
    bucket_name, blob_name = path.split("/", 1)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    data = blob.download_as_bytes()
    return pd.read_csv(io.BytesIO(data))


async def _write_failed_rows(job_id: str, errors: list[str]) -> None:
    import os, json
    from google.cloud import storage
    failed_bucket = os.environ.get(
        "GCS_FAILED_BUCKET", "vantage-failed-ingestion-supple-moon-495404-b0"
    )
    client = storage.Client()
    bucket = client.bucket(failed_bucket)
    bucket.blob(f"{job_id}_errors.json").upload_from_string(
        json.dumps(errors), content_type="application/json"
    )


def _get_firestore():
    from backend.app.core.database import get_firestore
    return get_firestore()


def _update_job(db, job_id: str, updates: dict) -> None:
    try:
        db.collection("ingestion_jobs").document(job_id).set(updates, merge=True)
    except Exception as exc:
        logger.warning("Failed to update job %s: %s", job_id, exc)
