"""Hotel profile insights with 30-day Firestore caching.

Wraps scraper + reviews to build a structured hotel profile that persists
across Cloud Run restarts. Cache TTL is configurable via REVIEW_CACHE_DAYS.
"""
import json
from datetime import datetime, timezone, timedelta


from backend.app.core.vertex_client import get_generative_model, extract_token_counts, calculate_cost_inr
from backend.app.core.config import get_settings
from backend.app.core.vertex_client import get_generative_model, extract_token_counts, calculate_cost_inr
from backend.app.core.database import get_firestore
from backend.app.services.scraper import scrape_hotel_page
from backend.app.services.reviews import fetch_google_reviews

settings = get_settings()


def _get_admin_model() -> str:
    """Get the admin-configured default model from Firestore."""
    try:
        db = get_firestore()
        doc = db.collection("admin_settings").document("config").get()
        if doc.exists:
            return doc.to_dict().get("default_model", "gemini-2.5-flash")
    except Exception:
        pass
    return "gemini-2.5-flash"


async def get_or_create_profile(
    hotel_name: str,
    reference_urls: list[str] | None = None,
    google_listing_urls: list[str] | None = None,
) -> dict:
    """Get cached hotel profile or create a fresh one.

    Returns a structured profile dict with website summary, review insights,
    rating, key USPs, and amenities. Cached in Firestore for 30 days.
    """
    db = get_firestore()
    reference_urls = reference_urls or []
    google_listing_urls = google_listing_urls or []

    # Check cache
    cached_docs = list(
        db.collection("profile_insights")
        .where("hotel_name", "==", hotel_name)
        .limit(1)
        .stream()
    )

    if cached_docs:
        cached = cached_docs[0].to_dict()
        expires_at = cached.get("expires_at", "")
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at)
                if datetime.now(timezone.utc) < exp:
                    return cached  # Cache hit — still fresh
            except (ValueError, TypeError):
                pass

    # Cache miss or expired — build fresh profile
    # 1. Scrape reference URLs
    scraped_content = ""
    scraped_title = ""
    for url in reference_urls:
        url = url.strip()
        if not url:
            continue
        try:
            result = await scrape_hotel_page(url)
            scraped_content += result.get("content", "") + "\n\n"
            if result.get("title"):
                scraped_title += result["title"] + " | "
        except Exception:
            continue

    # 2. Fetch Google Reviews
    review_data = {}
    for listing_url in google_listing_urls:
        if not listing_url or not listing_url.strip():
            continue
        try:
            rd = await fetch_google_reviews(listing_url, hotel_name)
            if not review_data or rd.get("review_count", 0) > review_data.get("review_count", 0):
                review_data = rd
        except Exception:
            pass

    # 3. Summarize with Gemini into structured profile
    profile = await _build_profile(
        hotel_name, scraped_content.strip(), scraped_title.strip(" |"), review_data
    )

    # 4. Store in Firestore with TTL
    now = datetime.now(timezone.utc)
    profile["hotel_name"] = hotel_name
    profile["generated_at"] = now.isoformat()
    profile["expires_at"] = (now + timedelta(days=settings.REVIEW_CACHE_DAYS)).isoformat()

    # Upsert: remove old, add new
    for doc in cached_docs:
        doc.reference.delete()
    db.collection("profile_insights").add(profile)

    return profile


async def _build_profile(
    hotel_name: str,
    scraped_content: str,
    scraped_title: str,
    review_data: dict,
) -> dict:
    """Call Gemini to build a structured hotel profile from raw data."""
    if not scraped_content and not review_data:
        return {
            "website_summary": "",
            "review_summary": "",
            "rating": 0,
            "review_count": 0,
            "key_usps": [],
            "amenities": [],
        }
    model_name = _get_admin_model()

    context = f"Hotel: {hotel_name}\n"
    if scraped_title:
        context += f"Website Title: {scraped_title}\n"
    if scraped_content:
        context += f"\nWebsite Content:\n{scraped_content[:5000]}\n"
    if review_data.get("insights"):
        context += f"\nGuest Review Insights ({review_data.get('overall_rating', 'N/A')}★):\n{review_data['insights']}\n"

    prompt = f"""Analyze this hotel data and create a structured profile. Return ONLY valid JSON:

{context}

{{
  "website_summary": "2-3 sentence summary of the hotel's positioning and key offerings",
  "review_summary": "1-2 sentence summary of guest sentiment and highlights",
  "rating": <overall rating as number or 0>,
  "review_count": <number of reviews or 0>,
  "key_usps": ["up to 5 key unique selling points"],
  "amenities": ["list of key amenities/facilities mentioned"]
}}"""

    try:
        model = get_generative_model(
            model_name,
            system_instruction="Extract and structure hotel data. Output ONLY valid JSON.",
        )
        response = model.generate_content(prompt)

        json_str = response.text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        data = json.loads(json_str.strip())

        return {
            "website_summary": data.get("website_summary", ""),
            "review_summary": data.get("review_summary", ""),
            "rating": review_data.get("overall_rating", data.get("rating", 0)),
            "review_count": review_data.get("review_count", data.get("review_count", 0)),
            "key_usps": data.get("key_usps", []),
            "amenities": data.get("amenities", []),
        }
    except Exception:
        # Fallback: return raw data without AI summary
        return {
            "website_summary": scraped_content[:500] if scraped_content else "",
            "review_summary": review_data.get("insights", ""),
            "rating": review_data.get("overall_rating", 0),
            "review_count": review_data.get("review_count", 0),
            "key_usps": [],
            "amenities": [],
        }
