"""Ad copy generation and refinement endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.core.auth import get_current_user
from backend.app.core.database import get_firestore
from backend.app.models.schemas import (
    AdGenerationRequest, AdGenerationResponse,
    AdRefinementRequest, AdRefinementResponse,
)
from backend.app.services.ad_generator import generate_ad_copy, refine_ad_copy

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


@router.get("/generate/url-suggestions")
async def get_url_suggestions(
    query: str = Query("", min_length=0),
    current_user: dict = Depends(get_current_user),
):
    """Return previously used reference URLs matching the query."""
    db = get_firestore()
    logs = (
        db.collection("audit_logs")
        .where("action", "==", "generate")
        .order_by("timestamp", direction="DESCENDING")
        .limit(50)
        .stream()
    )

    seen = set()
    suggestions = []
    query_lower = query.lower()
    for log in logs:
        data = log.to_dict()
        for url in data.get("reference_urls", []):
            if url not in seen and (not query_lower or query_lower in url.lower()):
                seen.add(url)
                suggestions.append(url)
            if len(suggestions) >= 10:
                break
        if len(suggestions) >= 10:
            break

    return {"suggestions": suggestions}


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
            "google_listing_urls": body.google_listing_urls,
            "campaign_objective": body.campaign_objective or "Auto-detect",
            "carousel_mode": body.carousel_mode if "fb_carousel" in body.platforms else None,
            "carousel_cards": body.carousel_cards if "fb_carousel" in body.platforms and body.carousel_mode == "manual" else None,
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


@router.post("/generate/refine", response_model=AdRefinementResponse)
async def refine_ads(
    body: AdRefinementRequest,
    current_user: dict = Depends(get_current_user),
):
    """Refine previously generated ad copy based on user feedback."""
    try:
        result = await refine_ad_copy(body)
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower():
            raise HTTPException(
                status_code=429,
                detail="Gemini API quota exceeded. Please try again later.",
            )
        raise HTTPException(status_code=500, detail=f"Refinement failed: {error_msg[:200]}")

    # Accumulate tokens and time
    total_tokens = body.accumulated_tokens + result["tokens_used"]
    total_time = round(body.accumulated_time + result["time_seconds"], 2)

    cost_inr = calculate_cost_inr(result["model_used"], result["input_tokens"], result["output_tokens"])

    # Audit log for refinement
    db = get_firestore()
    db.collection("audit_logs").add(
        {
            "user_email": current_user["sub"],
            "action": "refine",
            "hotel_name": body.hotel_name,
            "offer_name": body.offer_name,
            "platforms": body.platforms,
            "feedback": body.feedback,
            "tokens_consumed": result["tokens_used"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "accumulated_tokens": total_tokens,
            "model_used": result["model_used"],
            "cost_inr": cost_inr,
            "time_seconds": result["time_seconds"],
            "accumulated_time": total_time,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": current_user.get("session_id"),
        }
    )

    return AdRefinementResponse(
        hotel_name=body.hotel_name,
        variants=result["variants"],
        tokens_used=total_tokens,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        model_used=result["model_used"],
        time_seconds=total_time,
        generated_at=datetime.now(timezone.utc).isoformat(),
        refinement_count=1 + (1 if body.accumulated_tokens > 0 else 0),
    )
