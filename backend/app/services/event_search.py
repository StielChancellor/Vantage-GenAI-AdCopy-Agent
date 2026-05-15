"""Event search service using Vertex AI Grounding with Google Search.

Discovers upcoming events (festivals, holidays, sports, conferences) across
user-specified markets for CRM campaign timing. Uses Gemini's built-in
Google Search grounding — no Custom Search CX required.
"""
import json
import logging
from datetime import datetime

from backend.app.core.vertex_client import get_generative_model
from backend.app.core.database import get_firestore
from backend.app.models.schemas import EventResult

logger = logging.getLogger("vantage.event_search")


def _get_admin_model() -> str:
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
    """Search for upcoming events using Vertex AI Google Search grounding.

    Args:
        markets: List of markets/regions (default: ["India"])
        date_range_start: ISO date string for range start
        date_range_end: ISO date string for range end
        categories: Event categories (festivals, sports, conferences, holidays)

    Returns:
        List of EventResult objects sorted by relevance
    """
    markets = markets or ["India"]
    categories = categories or ["festivals", "holidays", "sports", "conferences"]

    date_context = ""
    if date_range_start and date_range_end:
        date_context = f"between {date_range_start} and {date_range_end}"
    elif date_range_start:
        date_context = f"from {date_range_start} onwards"
    else:
        now = datetime.now()
        date_context = f"in the upcoming 3 months from {now.strftime('%B %Y')}"

    markets_str = ", ".join(markets)
    categories_str = ", ".join(categories)

    prompt = f"""Search the web and find upcoming events {date_context} for these markets: {markets_str}.

Focus on categories: {categories_str}.

Find events that drive hotel bookings and travel demand — major festivals, national holidays,
large sports tournaments, business conferences, cultural events, and music/entertainment events.

Return ONLY a JSON array of the top 15 most relevant events, sorted by relevance_score descending:
[
  {{
    "title": "Event Name",
    "date": "YYYY-MM-DD or date range string",
    "description": "1-2 sentence description relevant to hotel marketing",
    "source": "URL or source name",
    "market": "Market/Region name",
    "relevance_score": 0.0-1.0
  }}
]

Use your web search results to provide accurate dates and current information. Return ONLY the JSON array."""

    try:
        from vertexai.generative_models import Tool, grounding

        search_tool = Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())
        # Google Search grounding is a Vertex/Gemini-only tool. Pin to Gemini
        # regardless of the admin-selected default (Claude adapter doesn't
        # support Vertex tools).
        model = get_generative_model(
            "gemini-2.5-flash",
            system_instruction="You are a travel industry event expert. Use Google Search to find real upcoming events. Return ONLY valid JSON array, no markdown.",
            tools=[search_tool],
        )
        response = model.generate_content(prompt)

        json_str = response.text.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        events_data = json.loads(json_str.strip())
        logger.info("Retrieved %d events via Google Search grounding", len(events_data))

        return [
            EventResult(
                title=e.get("title", ""),
                date=e.get("date", ""),
                description=e.get("description", ""),
                source=e.get("source", "Google Search"),
                market=e.get("market", markets[0]),
                relevance_score=float(e.get("relevance_score", 0.5)),
            )
            for e in events_data
            if e.get("title")
        ]

    except Exception as exc:
        logger.warning("Google Search grounding failed: %s — falling back to Gemini knowledge", exc)
        return await _fallback_gemini_events(markets, date_context, categories)


async def _fallback_gemini_events(
    markets: list[str],
    date_context: str,
    categories: list[str],
) -> list[EventResult]:
    """Fallback to Gemini knowledge when grounding is unavailable."""
    prompt = f"""List upcoming events {date_context} for these markets: {', '.join(markets)}.
Focus on categories: {', '.join(categories)}.
Events should drive hotel bookings (festivals, holidays, sports, conferences).

Return ONLY a JSON array, max 15 events, sorted by relevance_score descending:
[{{"title":"","date":"","description":"","source":"general knowledge","market":"","relevance_score":0.0}}]"""

    try:
        model = get_generative_model(
            _get_admin_model(),
            system_instruction="Return ONLY valid JSON array, no markdown.",
        )
        response = model.generate_content(prompt)

        json_str = response.text.strip()
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
            if e.get("title")
        ]
    except Exception:
        return []
