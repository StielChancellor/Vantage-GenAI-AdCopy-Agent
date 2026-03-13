"""Ad copy generation endpoint."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from backend.app.core.auth import get_current_user
from backend.app.core.database import get_firestore
from backend.app.models.schemas import AdGenerationRequest, AdGenerationResponse
from backend.app.services.ad_generator import generate_ad_copy

router = APIRouter()


@router.post("/generate", response_model=AdGenerationResponse)
async def generate_ads(
    body: AdGenerationRequest,
    current_user: dict = Depends(get_current_user),
):
    result = await generate_ad_copy(body)

    # Audit log
    db = get_firestore()
    db.collection("audit_logs").add(
        {
            "user_email": current_user["sub"],
            "action": "generate",
            "inputs": body.model_dump(),
            "tokens_consumed": result.tokens_used,
            "model_used": result.model_used,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": current_user.get("session_id"),
        }
    )

    return result
