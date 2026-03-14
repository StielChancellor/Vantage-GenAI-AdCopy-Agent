"""Ad copy generation endpoint."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.app.core.auth import get_current_user
from backend.app.core.database import get_firestore
from backend.app.models.schemas import AdGenerationRequest, AdGenerationResponse
from backend.app.services.ad_generator import generate_ad_copy

# Cost calculation: USD per 1M tokens
MODEL_PRICING = {
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
}
USD_TO_INR = 85.0


def calculate_cost_inr(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in INR for a generation."""
    pricing = MODEL_PRICING.get(model, {"input": 0.15, "output": 0.60})
    cost_usd = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return round(cost_usd * USD_TO_INR, 4)


router = APIRouter()


@router.post("/generate", response_model=AdGenerationResponse)
async def generate_ads(
    body: AdGenerationRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        result = await generate_ad_copy(body)
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower():
            raise HTTPException(
                status_code=429,
                detail="Gemini API quota exceeded. Please try again later or upgrade your plan.",
            )
        raise HTTPException(status_code=500, detail=f"Generation failed: {error_msg[:200]}")

    # Calculate cost in INR
    cost_inr = calculate_cost_inr(result.model_used, result.input_tokens, result.output_tokens)

    # Audit log with full details
    db = get_firestore()
    db.collection("audit_logs").add(
        {
            "user_email": current_user["sub"],
            "action": "generate",
            "hotel_name": body.hotel_name,
            "offer_name": body.offer_name,
            "platforms": body.platforms,
            "inclusions": body.inclusions,
            "reference_urls": body.reference_urls,
            "campaign_objective": body.campaign_objective or "Auto-detect",
            "tokens_consumed": result.tokens_used,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "model_used": result.model_used,
            "cost_inr": cost_inr,
            "time_seconds": result.time_seconds,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": current_user.get("session_id"),
        }
    )

    return result
