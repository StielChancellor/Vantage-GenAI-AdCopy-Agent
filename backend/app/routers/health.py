from fastapi import APIRouter

from backend.app.core.version import APP_VERSION, APP_VERSION_DATE

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "vantage-adcopy-agent",
        "version": APP_VERSION,
        "version_date": APP_VERSION_DATE,
    }


@router.get("/version")
async def version_info():
    """Cheap endpoint for the frontend to confirm what server it's talking to."""
    return {"version": APP_VERSION, "released": APP_VERSION_DATE}
