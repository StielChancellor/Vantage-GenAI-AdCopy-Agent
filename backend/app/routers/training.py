"""Training API endpoints — admin-only CSV upload with AI-powered Q&A."""
import io

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException

from backend.app.core.auth import require_admin
from backend.app.models.schemas import TrainingUploadResponse, TrainingAnswerRequest
from backend.app.services.training_engine import (
    start_training_session,
    answer_training_questions,
    get_training_sessions,
    get_training_directives,
)

router = APIRouter(prefix="/training", tags=["training"])


@router.post("/upload", response_model=TrainingUploadResponse)
async def upload_training_csv(
    file: UploadFile = File(...),
    csv_type: str = Form("historical_ads"),  # "historical_ads" or "brand_usp"
    hotel_name: str = Form(""),
    _user=Depends(require_admin),
):
    """Upload CSV and start AI training session with auto-analysis."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported.")

    contents = await file.read()
    df = pd.read_csv(io.BytesIO(contents))

    if df.empty:
        raise HTTPException(400, "CSV file is empty.")

    # Try to extract hotel name from data if not provided
    if not hotel_name:
        # Check for hotel_name column
        name_cols = [c for c in df.columns if "hotel" in c.lower() and "name" in c.lower()]
        if name_cols:
            hotel_name = str(df[name_cols[0]].dropna().iloc[0]) if not df[name_cols[0]].dropna().empty else "Unknown"
        else:
            hotel_name = "Unknown"

    result = start_training_session(hotel_name, csv_type, df)
    return result


@router.post("/answer", response_model=TrainingUploadResponse)
async def submit_training_answers(
    request: TrainingAnswerRequest,
    _user=Depends(require_admin),
):
    """Submit answers to AI-generated questions and optionally approve the directive."""
    result = answer_training_questions(
        session_id=request.session_id,
        answers=request.answers,
        approve=request.approve,
    )
    return result


@router.get("/sessions")
async def list_training_sessions(
    limit: int = 20,
    _user=Depends(require_admin),
):
    """List recent training sessions."""
    sessions = get_training_sessions(limit=limit)
    return sessions


@router.get("/directives/{hotel_name}")
async def list_directives(
    hotel_name: str,
    _user=Depends(require_admin),
):
    """Get approved training directives for a hotel."""
    directives = get_training_directives(hotel_name)
    return directives


@router.delete("/directives/{hotel_name}/{directive_type}")
async def delete_directive(
    hotel_name: str,
    directive_type: str,
    _user=Depends(require_admin),
):
    """Delete training directives for a hotel by type."""
    from backend.app.core.database import get_firestore

    db = get_firestore()
    docs = list(
        db.collection("training_directives")
        .where("hotel_name", "==", hotel_name)
        .where("directive_type", "==", directive_type)
        .stream()
    )
    deleted = 0
    for doc in docs:
        doc.reference.delete()
        deleted += 1

    return {"deleted": deleted, "hotel_name": hotel_name, "directive_type": directive_type}
