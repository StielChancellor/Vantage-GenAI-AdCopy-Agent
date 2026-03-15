"""Event search service using Google Custom Search API.

Discovers upcoming events (festivals, holidays, sports, conferences) across
user-specified markets for CRM campaign timing.
"""
import json
from datetime import datetime

import httpx
import google.generativeai as genai

from backend.app.core.config import get_settings
from backend.app.core.database import get_firestore
from backend.app.models.schemas import EventResult

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


async def search_events(
    markets: list[str] | None = None,
    date_range_start: str = "",
    date_range_end: str = "",
    categories: list[str] | None = None,
) -> list[EventResult]:
    """Search for upcoming events across specified markets.

    Args:
        markets: List of markets/regions (default: ["India"])
        date_range_start: ISO date string for range start
        date_range_end: ISO date string for range end
        categories: Event categories to search (festivals, sports, conferences, holidays)

    Returns:
        List of EventResult objects sorted by relevance
    """
    markets = markets or ["India"]
    categories = categories or ["festivals", "holidays", "sports", "conferences"]

    if not settings.GOOGLE_CUSTOM_SEARCH_API_KEY or not settings.GOOGLE_CUSTOM_SEARCH_CX:
        # Fallback: use Gemini knowledge for events
        return await _fallback_gemini_events(markets, date_range_start, date_range_end, categories)

    # Build search queries
    all_results = []
    date_context = ""
    if date_range_start:
        date_context = f" {date_range_start}"
    if date_range_end:
        date_context += f" to {date_range_end}"
    if not date_context:
        # Default to upcoming 3 months
        now = datetime.now()
        date_context = f" {now.strftime('%B %Y')} upcoming"

    async with httpx.AsyncClient(timeout=30) as client:
        for market in markets:
            for category in categories:
                query = f"upcoming {category} events {market}{date_context}"

                try:
                    resp = await client.get(
                        "https://www.googleapis.com/customsearch/v1",
                        params={
                            "key": settings.GOOGLE_CUSTOM_SEARCH_API_KEY,
                            "cx": settings.GOOGLE_CUSTOM_SEARCH_CX,
                            "q": query,
                            "num": 5,  # 5 results per query
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for item in data.get("items", []):
                        all_results.append({
                            "title": item.get("title", ""),
                            "snippet": item.get("snippet", ""),
                            "link": item.get("link", ""),
                            "market": market,
                            "category": category,
                        })
                except Exception:
                    continue

    if not all_results:
        return await _fallback_gemini_events(markets, date_range_start, date_range_end, categories)

    # Use Gemini to extract structured event data from search results
    return await _parse_search_results(all_results, date_range_start, date_range_end)


async def _parse_search_results(
    raw_results: list[dict],
    date_range_start: str,
    date_range_end: str,
) -> list[EventResult]:
    """Use Gemini to extract structured events from search snippets."""
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model_name = _get_admin_model()

    results_text = "\n".join(
        [
            f"- [{r['market']}/{r['category']}] {r['title']}: {r['snippet']} (Source: {r['link']})"
            for r in raw_results[:30]  # Limit to 30 results
        ]
    )

    date_filter = ""
    if date_range_start or date_range_end:
        date_filter = f"\nOnly include events between {date_range_start or 'now'} and {date_range_end or 'next 3 months'}."

    prompt = f"""Extract upcoming events from these search results. Deduplicate and rank by relevance
for hotel marketing campaigns (events that drive travel demand).{date_filter}

Search Results:
{results_text}

Return ONLY a JSON array of events:
[
  {{
    "title": "Event Name",
    "date": "YYYY-MM-DD or date range string",
    "description": "1-2 sentence description relevant to hotel marketing",
    "source": "URL source",
    "market": "Market/Region",
    "relevance_score": 0.0-1.0
  }}
]

Sort by relevance_score descending. Max 15 events."""

    try:
        model = genai.GenerativeModel(
            model_name,
            system_instruction="Extract structured event data from search results. Return ONLY valid JSON array.",
        )
        response = model.generate_content(prompt)

        json_str = response.text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        events_data = json.loads(json_str.strip())

        return [
            EventResult(
                title=e.get("title", ""),
                date=e.get("date", ""),
                description=e.get("description", ""),
                source=e.get("source", ""),
                market=e.get("market", ""),
                relevance_score=float(e.get("relevance_score", 0)),
            )
            for e in events_data
        ]
    except Exception:
        return []


async def _fallback_gemini_events(
    markets: list[str],
    date_range_start: str,
    date_range_end: str,
    categories: list[str],
) -> list[EventResult]:
    """Fallback: use Gemini's knowledge to suggest relevant events when Custom Search is unavailable."""
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model_name = _get_admin_model()

    date_context = ""
    if date_range_start:
        date_context = f"between {date_range_start}"
    if date_range_end:
        date_context += f" and {date_range_end}"
    if not date_context:
        now = datetime.now()
        date_context = f"in the upcoming 3 months from {now.strftime('%B %Y')}"

    prompt = f"""List upcoming events {date_context} for these markets: {', '.join(markets)}.
Focus on categories: {', '.join(categories)}.

These events should be relevant for hotel marketing campaigns — events that drive hotel bookings
and travel demand (festivals, national holidays, major sports events, conferences, etc.).

Return ONLY a JSON array:
[
  {{
    "title": "Event Name",
    "date": "YYYY-MM-DD or approximate date",
    "description": "1-2 sentence description for hotel marketing context",
    "source": "general knowledge",
    "market": "Market name",
    "relevance_score": 0.0-1.0
  }}
]

Max 15 events, sorted by relevance_score descending."""

    try:
        model = genai.GenerativeModel(
            model_name,
            system_instruction="You are a travel industry event expert. Return ONLY valid JSON array.",
        )
        response = model.generate_content(prompt)

        json_str = response.text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        events_data = json.loads(json_str.strip())

        return [
            EventResult(
                title=e.get("title", ""),
                date=e.get("date", ""),
                description=e.get("description", ""),
                source=e.get("source", "general knowledge"),
                market=e.get("market", ""),
                relevance_score=float(e.get("relevance_score", 0)),
            )
            for e in events_data
        ]
    except Exception:
        return []
