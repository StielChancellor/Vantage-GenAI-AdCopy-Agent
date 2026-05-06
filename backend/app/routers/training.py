"""Training API endpoints — Phase 2.1 overhaul.

Supports 3 modes (CSV, Text, CSV+Text), generic section types (legacy AI
summarization flow), and adapter section types (v2.1 deterministic ingestion
pipeline: validate → score → embed → BQ).
"""
import io
import json
import logging
import time
import uuid
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from starlette.responses import StreamingResponse

from backend.app.core.auth import require_admin
from backend.app.core.database import get_firestore
from backend.app.models.schemas import TrainingUploadResponse, TrainingAnswerRequest
from backend.app.services.training_engine import (
    start_training_session,
    answer_training_questions,
    get_training_sessions,
    get_training_directives,
    export_sessions_csv,
)

logger = logging.getLogger("vantage.training")
router = APIRouter(prefix="/training", tags=["training"])


# Section types that bypass the AI summarization flow and run the v2.1
# deterministic ingestion pipeline (adapter → score → embed → BQ).
_ADAPTER_SECTION_TYPES = {"google_ads_export", "moengage_push"}


def _read_csv_robust(contents: bytes) -> pd.DataFrame:
    """Try several encodings — Windows-1252 is common for Google Ads exports
    (smart quotes, em-dashes), MoEngage uses UTF-8."""
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(contents), encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except Exception as exc:
            # Other errors (parse, etc.) — re-raise immediately
            raise
    raise HTTPException(
        400,
        f"Could not decode CSV. Tried utf-8, cp1252, latin-1. Last error: {last_error}",
    )


@router.get("/progress/{run_id}")
async def get_training_progress(run_id: str, _user=Depends(require_admin)):
    """Live progress for an in-flight v2.1 ingestion run. Polled by the
    frontend every ~800ms while a training_run is uploading. Returns:
        {phase, processed, total, percent, message, status}
    `status` is 'running' until completion, then 'completed' or 'failed'.
    Returns {percent: 0, status: 'pending'} if no doc yet (request is mid-flight)."""
    try:
        db = get_firestore()
        doc = db.collection("ingestion_progress").document(run_id).get()
        if doc.exists:
            return doc.to_dict()
    except Exception as exc:
        logger.debug("progress fetch failed: %s", exc)
    return {"percent": 0, "phase": "starting", "status": "pending", "message": "Initializing..."}


@router.post("/upload", response_model=TrainingUploadResponse)
async def upload_training_data(
    file: UploadFile = File(None),
    section_type: str = Form("ad_performance"),
    training_mode: str = Form("csv_only"),
    text_input: str = Form(""),
    kpi_columns: str = Form("[]"),
    hero_columns: str = Form("[]"),
    brand_id: str = Form(""),
    run_id: str = Form(""),
    remarks: str = Form(""),
    _user=Depends(require_admin),
):
    """Upload CSV/text and start training. Routes to the right pipeline based
    on section_type. If run_id is supplied, the client can poll
    /training/progress/{run_id} for live updates. `remarks` is a free-text
    note attached to the session record for human context."""
    try:
        kpi_list = json.loads(kpi_columns) if kpi_columns else []
    except (json.JSONDecodeError, TypeError):
        kpi_list = []

    try:
        hero_list = json.loads(hero_columns) if hero_columns else []
    except (json.JSONDecodeError, TypeError):
        hero_list = []

    df = None
    if training_mode in ("csv_only", "csv_and_text"):
        if not file or not file.filename:
            raise HTTPException(400, "CSV file required for this training mode.")
        if not file.filename.endswith(".csv"):
            raise HTTPException(400, "Only CSV files are supported.")
        contents = await file.read()
        df = _read_csv_robust(contents)
        if df.empty:
            raise HTTPException(400, "CSV file is empty.")

    if training_mode == "text_only" and not text_input.strip():
        raise HTTPException(400, "Text input required for text-only training mode.")

    # ---------- v2.1 adapter ingestion path ----------
    if section_type in _ADAPTER_SECTION_TYPES:
        if df is None:
            raise HTTPException(400, f"section_type={section_type} requires a CSV file.")
        return await _run_v21_ingestion(
            df=df,
            section_type=section_type,
            brand_id=(brand_id or _user.get("name") or "_global"),
            user_id=_user.get("uid", "unknown"),
            run_id_override=run_id or None,
            remarks=remarks,
        )

    # ---------- Legacy AI summarization path ----------
    return start_training_session(
        section_type=section_type,
        training_mode=training_mode,
        df=df,
        text_input=text_input,
        kpi_columns=kpi_list,
        hero_columns=hero_list,
    )


# Vertex AI text-embedding-005 pricing: $0.025 per 1M input tokens.
# 1 token ≈ 4 characters of English text.
_EMBED_USD_PER_M_TOKENS = 0.025
_USD_TO_INR = 85
_EMBED_MODEL = "text-embedding-005"


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _embed_cost_inr(total_tokens: int) -> float:
    cost_usd = (total_tokens / 1_000_000) * _EMBED_USD_PER_M_TOKENS
    return round(cost_usd * _USD_TO_INR, 6)


def _update_progress(
    run_id: str,
    phase: str,
    percent: int,
    message: str,
    processed: int = 0,
    total: int = 0,
    status: str = "running",
) -> None:
    """Write live progress to Firestore so the frontend polling endpoint sees it."""
    try:
        db = get_firestore()
        db.collection("ingestion_progress").document(run_id).set({
            "phase": phase,
            "percent": int(percent),
            "message": message,
            "processed": int(processed),
            "total": int(total),
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, merge=True)
    except Exception as exc:
        logger.debug("progress write failed (non-fatal): %s", exc)


async def _run_v21_ingestion(
    df: pd.DataFrame,
    section_type: str,
    brand_id: str,
    user_id: str,
    run_id_override: str | None = None,
    remarks: str = "",
) -> TrainingUploadResponse:
    """Adapter → score → embed → BigQuery, all in-process. Returns a
    TrainingUploadResponse with the deterministic stats baked into the
    directive_preview AND populates Sessions-table fields (cost_inr,
    time_seconds, input_tokens, model_used, created_at) so the run shows
    up cleanly in the existing Sessions UI."""
    from backend.app.services.ingestion.csv_validator import validate_csv
    from backend.app.services.ingestion.adapters import parse_google_ads, parse_moengage
    from backend.app.services.analytics.quality_scorer import (
        score_records, quality_report_from_records,
    )
    from backend.app.services.embedding.vertex_embedder import embed_records
    from backend.app.services.analytics.bq_writer import write_normalized_records

    training_run_id = run_id_override or str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    start_time = time.time()

    _update_progress(training_run_id, "validating", 5, "Validating CSV schema...", total=len(df))
    report = validate_csv(df, section_type)
    if not report.passed:
        _update_progress(
            training_run_id, "failed", 0, f"Validation failed: {report.rejection_reason}",
            status="failed",
        )
        raise HTTPException(400, f"Validation failed: {report.rejection_reason}")

    _update_progress(training_run_id, "parsing", 15, f"Parsing {section_type} schema...", total=len(df))
    if section_type == "google_ads_export":
        records = parse_google_ads(df)
    else:
        records = parse_moengage(df)

    if not records:
        elapsed = round(time.time() - start_time, 2)
        directive_preview = {
            "format": section_type,
            "source_rows": int(len(df)),
            "normalized_records": 0,
            "embedded": 0,
            "skipped_low_volume": 0,
            "quality_score": 0.0,
            "warning": "Adapter produced 0 records — input may be empty or all rows had zero impressions.",
        }
        _persist_session(
            training_run_id, section_type, brand_id, user_id,
            directive_preview, started_at, elapsed,
            input_tokens=0, cost_inr=0.0, remarks=remarks,
        )
        _update_progress(
            training_run_id, "completed", 100,
            "No usable records — input was empty or all rows had zero impressions.",
            status="completed",
        )
        return TrainingUploadResponse(
            session_id=training_run_id,
            status="completed",
            questions=[],
            directive_preview=directive_preview,
        )

    _update_progress(
        training_run_id, "scoring", 25,
        f"Scoring {len(records)} records (recency × impressions × CTR)...",
        total=len(records),
    )
    score_records(records)
    quality = quality_report_from_records(records, section_type)

    _update_progress(
        training_run_id, "writing_bq", 30,
        "Writing performance data to BigQuery...",
        total=len(records),
    )
    try:
        await write_normalized_records(records, brand_id=brand_id, training_run_id=training_run_id)
    except Exception as exc:
        logger.warning("BQ write failed for run %s: %s", training_run_id, exc)

    embedded_count = 0
    embed_errors: list[str] = []
    total_chars = 0
    eligible = [r for r in records if r.performance_score > 0]
    BATCH = 50
    total_eligible = len(eligible)
    n_batches = max(1, (total_eligible + BATCH - 1) // BATCH)
    _update_progress(
        training_run_id, "embedding", 35,
        f"Embedding {total_eligible} records in {n_batches} batches...",
        total=total_eligible,
    )
    for i in range(0, total_eligible, BATCH):
        chunk = eligible[i:i + BATCH]
        chunk_chars = sum(len(r.as_embedding_text()) for r in chunk)
        try:
            docs = await embed_records(
                chunk,
                brand_id=brand_id,
                training_run_id=training_run_id,
                section_type=section_type,
            )
            embedded_count += len(docs)
            total_chars += chunk_chars
        except Exception as exc:
            logger.warning("Embed batch %d failed for run %s: %s", i // BATCH, training_run_id, exc)
            embed_errors.append(str(exc)[:200])

        # 35% to 95% scaled by batch progress
        pct = 35 + int(60 * (i + len(chunk)) / max(total_eligible, 1))
        _update_progress(
            training_run_id, "embedding", min(95, pct),
            f"Embedded {embedded_count}/{total_eligible} records...",
            processed=embedded_count, total=total_eligible,
        )

    elapsed = round(time.time() - start_time, 2)
    input_tokens = total_chars // 4 if total_chars else 0
    cost_inr = _embed_cost_inr(input_tokens)

    directive_preview = {
        "format": section_type,
        "source_rows": int(len(df)),
        "normalized_records": len(records),
        "embedded": embedded_count,
        "skipped_low_volume": len(records) - len(eligible),
        "quality_score": quality.quality_score,
        "quality_passed": quality.passed,
        "avg_performance_score": quality.avg_performance_score,
        "records_above_floor": quality.records_above_floor,
        "warnings": quality.warnings,
        "embed_errors": embed_errors[:5],
    }

    _persist_session(
        training_run_id, section_type, brand_id, user_id,
        directive_preview, started_at, elapsed,
        input_tokens=input_tokens, cost_inr=cost_inr, remarks=remarks,
    )

    _update_progress(
        training_run_id, "completed", 100,
        f"Training complete — {embedded_count} records embedded, {len(records) - len(eligible)} below floor. Cost: ₹{cost_inr:.4f}, time: {elapsed}s.",
        processed=embedded_count, total=total_eligible, status="completed",
    )

    return TrainingUploadResponse(
        session_id=training_run_id,
        status="approved",
        questions=[],
        directive_preview=directive_preview,
    )


def _persist_session(
    training_run_id: str,
    section_type: str,
    brand_id: str,
    user_id: str,
    directive_preview: dict,
    started_at: datetime,
    elapsed_seconds: float,
    input_tokens: int,
    cost_inr: float,
    remarks: str = "",
) -> None:
    """Write a Sessions-row-shaped doc to Firestore so the v2.1 ingestion run
    appears in the Training → Sessions table with cost, time, tokens, etc."""
    completed_at = datetime.now(timezone.utc)
    try:
        db = get_firestore()
        db.collection("training_state").document(training_run_id).set({
            "session_id": training_run_id,
            "section_type": section_type,
            "training_mode": "csv_only",
            "status": "approved",  # Deterministic ingestion is auto-approved
            "directive_preview": directive_preview,
            "questions": [],
            "answers": [],
            "brand_id": brand_id,
            "user_id": user_id,
            "save_mode": "append",
            "input_tokens": int(input_tokens),
            "output_tokens": 0,
            "time_seconds": float(elapsed_seconds),
            "cost_inr": float(cost_inr),
            "model_used": _EMBED_MODEL,
            "remarks": (remarks or "")[:1000],
            "created_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
        }, merge=True)
    except Exception as exc:
        logger.debug("training_state write failed (non-fatal): %s", exc)


@router.delete("/sessions/{session_id}")
async def delete_training_session(session_id: str, _user=Depends(require_admin)):
    """Delete a training session record + its progress doc + the BigQuery
    rows it produced. Embeddings in Firestore embedding_cache are kept
    (content-hash deduped, will be reused or overwritten by future runs)."""
    db = get_firestore()
    deleted = {"training_state": False, "ingestion_progress": False, "bq_rows": 0}

    # 1. training_state
    try:
        ref = db.collection("training_state").document(session_id)
        if ref.get().exists:
            ref.delete()
            deleted["training_state"] = True
    except Exception as exc:
        logger.warning("Failed deleting training_state/%s: %s", session_id, exc)

    # 2. ingestion_progress
    try:
        ref = db.collection("ingestion_progress").document(session_id)
        if ref.get().exists:
            ref.delete()
            deleted["ingestion_progress"] = True
    except Exception as exc:
        logger.debug("ingestion_progress delete failed: %s", exc)

    # 3. BQ rows where training_run_id = session_id
    try:
        import os as _os
        from google.cloud import bigquery
        client = bigquery.Client(project=_os.environ.get("GCP_PROJECT_ID", "supple-moon-495404-b0"))
        dataset = _os.environ.get("BQ_DATASET", "vantage")
        sql = f"""
            DELETE FROM `{client.project}.{dataset}.ad_performance_events`
            WHERE training_run_id = @run_id
        """
        job = client.query(
            sql,
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("run_id", "STRING", session_id),
            ]),
        )
        job.result()
        deleted["bq_rows"] = int(job.num_dml_affected_rows or 0)
    except Exception as exc:
        logger.warning("BQ delete failed for run %s: %s", session_id, exc)

    if not deleted["training_state"]:
        raise HTTPException(404, "Session not found.")
    return {"deleted": True, **deleted}


@router.post("/answer", response_model=TrainingUploadResponse)
async def submit_training_answers(
    request: TrainingAnswerRequest,
    _user=Depends(require_admin),
):
    """Submit answers and optionally approve with append/replace mode."""
    result = answer_training_questions(
        session_id=request.session_id,
        answers=request.answers,
        approve=request.approve,
        save_mode=request.save_mode,
    )
    return result


@router.get("/sessions")
async def list_training_sessions(
    limit: int = 20,
    _user=Depends(require_admin),
):
    """List recent training sessions."""
    return get_training_sessions(limit=limit)


@router.get("/sessions/export")
async def export_training_sessions_csv(_user=Depends(require_admin)):
    """Export all training sessions as CSV."""
    csv_data = export_sessions_csv(limit=500)
    return StreamingResponse(
        io.StringIO(csv_data),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=training_sessions.csv"},
    )


@router.get("/directives")
async def list_all_directives(_user=Depends(require_admin)):
    """List all approved training directives (global)."""
    return get_training_directives()


@router.get("/directives/{section_type}")
async def list_directives_by_type(
    section_type: str,
    _user=Depends(require_admin),
):
    """List approved directives filtered by section type."""
    return get_training_directives(section_type=section_type)


@router.delete("/directives/{directive_id}")
async def delete_directive(
    directive_id: str,
    _user=Depends(require_admin),
):
    """Delete a training directive by document ID."""
    db = get_firestore()
    doc_ref = db.collection("training_directives").document(directive_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(404, "Directive not found.")
    doc_ref.delete()
    return {"deleted": 1, "id": directive_id}


@router.get("/knowledge-base")
async def search_knowledge_base(
    q: str = "",
    section_type: str = "",
    _user=Depends(require_admin),
):
    """Search accumulated training insights (knowledge base)."""
    directives = get_training_directives(section_type=section_type or None)
    if q:
        q_lower = q.lower()
        directives = [
            d for d in directives
            if q_lower in json.dumps(d.get("content", {})).lower()
        ]
    return directives
