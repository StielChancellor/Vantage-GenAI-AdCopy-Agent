"""CRM campaign generation API endpoints."""
import io
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.core.auth import get_current_user
from backend.app.models.schemas import (
    CRMGenerateRequest, CRMGenerateResponse,
    CRMRefineRequest,
)
from backend.app.services.crm_generator import (
    generate_crm_content,
    refine_crm_content,
    export_calendar_csv,
)

logger = logging.getLogger("vantage.crm")
router = APIRouter(prefix="/crm", tags=["crm"])


@router.post("/generate", response_model=CRMGenerateResponse)
async def generate_crm(
    request: CRMGenerateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate CRM campaign content for WhatsApp, Email, and/or App Push.

    Returns channel-specific messages with a campaign calendar.
    WhatsApp has strict character limits; Email and App Push have soft guidance.

    v2.5 — wrapped in try/except so any backend hiccup surfaces as a readable
    HTTP error rather than a bare 500 with no detail."""
    try:
        result = await generate_crm_content(request)
        return result
    except Exception as exc:
        msg = str(exc)
        logger.error(
            "crm_generate_failed",
            extra={"json_fields": {
                "user_email": current_user.get("sub"),
                "hotel_name": getattr(request, "hotel_name", ""),
                "channels": getattr(request, "channels", []),
                "exc_type": type(exc).__name__,
                "exc": msg[:500],
            }},
            exc_info=True,
        )
        if "429" in msg or "quota" in msg.lower():
            raise HTTPException(429, "Gemini API quota exceeded. Try again shortly.")
        raise HTTPException(500, f"CRM generation failed: {msg[:200]}")


@router.post("/refine", response_model=CRMGenerateResponse)
async def refine_crm(
    request: CRMRefineRequest,
    _user=Depends(get_current_user),
):
    """Refine CRM content based on user feedback."""
    result = await refine_crm_content(request)
    return result


@router.post("/export-calendar")
async def export_calendar(
    calendar: list[dict],
    _user=Depends(get_current_user),
):
    """Export CRM campaign calendar as CSV file."""
    csv_content = export_calendar_csv(calendar)
    return StreamingResponse(
        io.BytesIO(csv_content.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=crm_calendar.csv"},
    )
