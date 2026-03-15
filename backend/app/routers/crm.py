"""CRM campaign generation API endpoints."""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
import io

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

router = APIRouter(prefix="/crm", tags=["crm"])


@router.post("/generate", response_model=CRMGenerateResponse)
async def generate_crm(
    request: CRMGenerateRequest,
    _user=Depends(get_current_user),
):
    """Generate CRM campaign content for WhatsApp, Email, and/or App Push.

    Returns channel-specific messages with a campaign calendar.
    WhatsApp has strict character limits; Email and App Push have soft guidance.
    """
    result = await generate_crm_content(request)
    return result


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
