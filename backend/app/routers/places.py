"""Google Places autocomplete and details endpoints."""
import asyncio

import httpx
from fastapi import APIRouter, Depends, Query

from backend.app.core.auth import get_current_user
from backend.app.core.config import get_settings

settings = get_settings()
router = APIRouter()

AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


@router.get("/places/autocomplete")
async def places_autocomplete(
    query: str = Query(..., min_length=2),
    current_user: dict = Depends(get_current_user),
):
    """Search Google Places and return suggestions with review counts."""
    async with httpx.AsyncClient(timeout=15) as client:
        # Step 1: Autocomplete
        ac_resp = await client.get(
            AUTOCOMPLETE_URL,
            params={
                "input": query,
                "types": "establishment",
                "key": settings.GOOGLE_PLACES_API_KEY,
            },
        )
        ac_data = ac_resp.json()
        predictions = ac_data.get("predictions", [])[:5]

        if not predictions:
            return {"suggestions": []}

        # Step 2: Fetch details for each prediction in parallel
        async def fetch_details(place_id: str, description: str) -> dict:
            try:
                resp = await client.get(
                    DETAILS_URL,
                    params={
                        "place_id": place_id,
                        "fields": "name,formatted_address,rating,user_ratings_total,url,place_id",
                        "key": settings.GOOGLE_PLACES_API_KEY,
                    },
                )
                result = resp.json().get("result", {})
                return {
                    "place_id": place_id,
                    "name": result.get("name", description),
                    "address": result.get("formatted_address", ""),
                    "rating": result.get("rating", 0),
                    "review_count": result.get("user_ratings_total", 0),
                    "google_url": result.get("url", ""),
                }
            except Exception:
                return {
                    "place_id": place_id,
                    "name": description,
                    "address": "",
                    "rating": 0,
                    "review_count": 0,
                    "google_url": "",
                }

        tasks = [
            fetch_details(p["place_id"], p.get("description", ""))
            for p in predictions
        ]
        suggestions = await asyncio.gather(*tasks)

    return {"suggestions": list(suggestions)}
