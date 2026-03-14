"""Google Reviews integration with caching and insight extraction."""
import re
from datetime import datetime, timezone, timedelta

import httpx
import google.generativeai as genai

from backend.app.core.database import get_firestore
from backend.app.core.config import get_settings

settings = get_settings()


def _extract_place_id(google_url: str) -> str:
    """Extract Place ID from a Google Maps/Listing URL.

    Supports formats:
    - https://www.google.com/maps/place/.../@lat,lng,.../data=!...!1s<PLACE_ID>
    - https://maps.google.com/?cid=<CID>
    - Direct place ID strings
    """
    if google_url.startswith("ChI") or google_url.startswith("place_id:"):
        return google_url.replace("place_id:", "")

    # Try to extract from URL patterns
    match = re.search(r"!1s(ChI[^\!]+)", google_url)
    if match:
        return match.group(1)

    # Fallback: use the URL as a text search query
    return google_url


async def fetch_google_reviews(google_listing_url: str, hotel_name: str) -> dict:
    """Fetch and process Google reviews. Uses cache if fresh enough."""
    db = get_firestore()

    # Check cache
    cache_ref = db.collection("review_cache").where("hotel_name", "==", hotel_name).limit(1)
    cached = list(cache_ref.stream())

    if cached:
        cache_data = cached[0].to_dict()
        cached_at = datetime.fromisoformat(cache_data["cached_at"])
        if datetime.now(timezone.utc) - cached_at < timedelta(days=settings.REVIEW_CACHE_DAYS):
            return cache_data

    # Fetch fresh reviews via Google Places API
    place_id = _extract_place_id(google_listing_url)

    async with httpx.AsyncClient(timeout=30) as client:
        # First, resolve place ID if we have a URL
        if not place_id.startswith("ChI"):
            # Use Find Place to get the place ID
            find_resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
                params={
                    "input": hotel_name,
                    "inputtype": "textquery",
                    "fields": "place_id",
                    "key": settings.GOOGLE_PLACES_API_KEY,
                },
            )
            find_data = find_resp.json()
            candidates = find_data.get("candidates", [])
            if not candidates:
                return {"hotel_name": hotel_name, "insights": "No reviews found.", "review_count": 0}
            place_id = candidates[0]["place_id"]

        # Get place details with reviews
        detail_resp = await client.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields": "reviews,rating,user_ratings_total",
                "key": settings.GOOGLE_PLACES_API_KEY,
            },
        )
        detail_data = detail_resp.json().get("result", {})

    reviews = detail_data.get("reviews", [])
    # Filter for 4 and 5 star reviews only
    positive_reviews = [r for r in reviews if r.get("rating", 0) >= 4]

    if not positive_reviews:
        result = {
            "hotel_name": hotel_name,
            "insights": "No positive reviews available.",
            "review_count": 0,
            "overall_rating": detail_data.get("rating", 0),
        }
    else:
        # Extract insights using lightweight LLM
        review_texts = "\n---\n".join(
            [f"({r['rating']}★) {r.get('text', '')}" for r in positive_reviews]
        )
        insights = await _extract_review_insights(review_texts, hotel_name)

        result = {
            "hotel_name": hotel_name,
            "insights": insights,
            "review_count": len(positive_reviews),
            "overall_rating": detail_data.get("rating", 0),
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }

    # Update cache
    for doc in cached:
        doc.reference.delete()
    db.collection("review_cache").add(result)

    return result


async def _extract_review_insights(review_text: str, hotel_name: str) -> str:
    """Use Gemini Flash to extract key insights from reviews."""
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = f"""Analyze these guest reviews for {hotel_name} and extract:
1. Top 5 positive themes/highlights guests mention
2. Key amenities/features praised
3. Emotional keywords guests use (e.g., "stunning", "peaceful", "world-class")
4. Unique selling points mentioned by guests

Reviews:
{review_text[:4000]}

Return a concise summary (max 300 words) of insights and positive keywords."""

    response = model.generate_content(prompt)
    return response.text
