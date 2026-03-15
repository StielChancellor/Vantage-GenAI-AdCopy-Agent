"""Event search API endpoints for CRM campaign timing."""
from fastapi import APIRouter, Depends

from backend.app.core.auth import get_current_user
from backend.app.models.schemas import EventSearchRequest, EventResult
from backend.app.services.event_search import search_events

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/search", response_model=list[EventResult])
async def search_upcoming_events(
    request: EventSearchRequest,
    _user=Depends(get_current_user),
):
    """Search for upcoming events across specified markets.

    Uses Google Custom Search API to find festivals, holidays, sports events,
    and conferences relevant to hotel marketing campaigns. Falls back to
    Gemini knowledge if Custom Search is not configured.
    """
    results = await search_events(
        markets=request.markets,
        date_range_start=request.date_range_start,
        date_range_end=request.date_range_end,
        categories=request.categories,
    )
    return results
