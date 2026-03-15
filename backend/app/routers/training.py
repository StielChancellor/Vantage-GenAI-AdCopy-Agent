"""Training API endpoints — Phase 2.1 overhaul.

Supports 3 modes (CSV, Text, CSV+Text), 3 section types, hero/KPI columns,
append/replace, session export, and knowledge base search.
"""
import io
import json

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

router = APIRouter(prefix="/training", tags=["training"])


@router.post("/upload", response_model=TrainingUploadResponse)
async def upload_training_data(
    file: UploadFile = File(None),
    section_type: str = Form("ad_performance"),
    training_mode: str = Form("csv_only"),
    text_input: str = Form(""),
    kpi_columns: str = Form("[]"),
    hero_columns: str = Form("[]"),
    _user=Depends(require_admin),
):
    """Upload CSV/text and start AI training session."""
    # Parse JSON-encoded form fields
    try:
        kpi_list = json.loads(kpi_columns) if kpi_columns else []
    except (json.JSONDecodeError, TypeError):
        kpi_list = []

    try:
        hero_list = json.loads(hero_columns) if hero_columns else []
    except (json.JSONDecodeError, TypeError):
        hero_list = []

    # Validate mode + file
    df = None
    if training_mode in ("csv_only", "csv_and_text"):
        if not file or not file.filename:
            raise HTTPException(400, "CSV file required for this training mode.")
        if not file.filename.endswith(".csv"):
            raise HTTPException(400, "Only CSV files are supported.")
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
        if df.empty:
            raise HTTPException(400, "CSV file is empty.")

    if training_mode == "text_only" and not text_input.strip():
        raise HTTPException(400, "Text input required for text-only training mode.")

    result = start_training_session(
        section_type=section_type,
        training_mode=training_mode,
        df=df,
        text_input=text_input,
        kpi_columns=kpi_list,
        hero_columns=hero_list,
    )
    return result


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
