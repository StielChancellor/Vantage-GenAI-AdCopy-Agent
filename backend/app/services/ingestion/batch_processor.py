"""Async batch CSV processor — streams from GCS, chunks into 50-row batches,
embeds each chunk, writes to BigQuery, and tracks progress in Firestore.

Triggered by Cloud Tasks after a CSV is uploaded to GCS.
"""
from __future__ import annotations

import io
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import pandas as pd

logger = logging.getLogger("vantage.ingestion")

CHUNK_SIZE = 50


async def process_csv_from_gcs(
    gcs_uri: str,
    section_type: str,
    brand_id: str,
    training_run_id: str,
    job_id: str | None = None,
) -> dict:
    """Main entry point. Downloads CSV from GCS, validates, chunks, embeds, and writes to BQ.

    Returns a status dict with total_rows, embedded_rows, errors.
    """
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

    # Download and parse CSV
    try:
        df = await _read_csv_from_gcs(gcs_uri)
    except Exception as exc:
        _update_job(db, job_id, {"status": "failed", "error": str(exc)})
        return {"status": "failed", "error": str(exc)}

    # Validate
    from backend.app.services.ingestion.csv_validator import validate_csv
    report = validate_csv(df, section_type)
    if not report.passed:
        _update_job(db, job_id, {
            "status": "failed",
            "error": report.rejection_reason,
        })
        return {"status": "failed", "error": report.rejection_reason}

    total_rows = len(df)
    _update_job(db, job_id, {"total_rows": total_rows})

    # Process in chunks
    processed = 0
    all_errors: list[str] = []
    chunks = [df.iloc[i:i + CHUNK_SIZE] for i in range(0, total_rows, CHUNK_SIZE)]

    chunk_tasks = [
        _process_chunk(chunk, section_type, brand_id, training_run_id, idx)
        for idx, chunk in enumerate(chunks)
    ]
    results = await asyncio.gather(*chunk_tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            all_errors.append(str(result))
        else:
            processed += result.get("rows", 0)
            _update_job(db, job_id, {"processed_rows": processed})

    # Write failed rows to GCS if any errors
    if all_errors:
        await _write_failed_rows(gcs_uri, all_errors)

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


async def _process_chunk(
    chunk: pd.DataFrame,
    section_type: str,
    brand_id: str,
    training_run_id: str,
    chunk_idx: int,
) -> dict:
    """Embed one chunk and write to BigQuery."""
    from backend.app.services.embedding.vertex_embedder import embed_dataframe_chunk
    from backend.app.services.analytics.bq_writer import write_ad_performance_rows

    texts = _chunk_to_texts(chunk, section_type)
    embeddings = await embed_dataframe_chunk(texts, brand_id=brand_id, training_run_id=training_run_id)

    if section_type == "ad_performance":
        await write_ad_performance_rows(chunk, brand_id=brand_id, training_run_id=training_run_id)

    return {"rows": len(chunk), "chunk_idx": chunk_idx}


def _chunk_to_texts(chunk: pd.DataFrame, section_type: str) -> list[str]:
    """Convert DataFrame rows to text strings for embedding."""
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


async def _read_csv_from_gcs(gcs_uri: str) -> pd.DataFrame:
    from google.cloud import storage
    # Parse gs://bucket/path
    path = gcs_uri.replace("gs://", "")
    bucket_name, blob_name = path.split("/", 1)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    data = blob.download_as_bytes()
    return pd.read_csv(io.BytesIO(data))


async def _write_failed_rows(original_uri: str, errors: list[str]) -> None:
    import os, json
    from google.cloud import storage
    failed_bucket = os.environ.get("GCS_FAILED_BUCKET", "vantage-failed-ingestion-supple-moon-495404-b0")
    client = storage.Client()
    bucket = client.bucket(failed_bucket)
    blob_name = original_uri.replace("gs://", "").replace("/", "_") + "_errors.json"
    bucket.blob(blob_name).upload_from_string(json.dumps(errors), content_type="application/json")


def _get_firestore():
    from backend.app.core.database import get_firestore
    return get_firestore()


def _update_job(db, job_id: str, updates: dict) -> None:
    try:
        db.collection("ingestion_jobs").document(job_id).set(updates, merge=True)
    except Exception as exc:
        logger.warning("Failed to update job %s: %s", job_id, exc)
