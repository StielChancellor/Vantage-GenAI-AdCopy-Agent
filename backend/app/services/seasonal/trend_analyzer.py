"""Hospitality trend analyzer using Vertex AI Grounding with Google Search.

Retrieves trending keywords, competitor moves, and demand signals for the
current week to inject into generation prompts as live market intelligence.
"""
from __future__ import annotations

import json
import logging
from datetime import date

logger = logging.getLogger("vantage.trend_analyzer")


async def get_trending_keywords(
    market: str = "India",
    segment: str = "luxury hotels",
    flight_date: date | str | None = None,
) -> list[str]:
    """Fetch trending hospitality keywords for the current week via Google Search.

    Returns a list of up to 15 trending keywords/phrases to inject into ad prompts.
    Falls back to an empty list if grounding is unavailable.
    """
    from backend.app.core.vertex_client import get_generative_model

    date_hint = str(flight_date) if flight_date else date.today().isoformat()
    prompt = f"""Search Google and find the top trending keywords, topics, and phrases
in the {segment} sector in {market} for the week of {date_hint}.

Include: trending travel hashtags, popular hotel amenity keywords, seasonal demand drivers,
competitor campaign themes, and consumer sentiment signals.

Return ONLY a JSON array of strings (keyword phrases), max 15 items, most relevant first:
["keyword 1", "keyword 2", ...]"""

    try:
        from vertexai.generative_models import Tool, grounding

        search_tool = Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())
        model = get_generative_model(
            "gemini-2.5-flash",
            system_instruction="Return ONLY a valid JSON array of strings. No markdown, no explanation.",
            tools=[search_tool],
        )
        response = model.generate_content(prompt)

        json_str = response.text.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        keywords = json.loads(json_str.strip())
        if isinstance(keywords, list):
            result = [str(k) for k in keywords[:15]]
            logger.info("Fetched %d trending keywords for %s/%s", len(result), market, segment)
            return result
    except Exception as exc:
        logger.debug("Trend keyword fetch failed: %s", exc)

    return []


async def build_trend_prompt_context(
    market: str = "India",
    segment: str = "luxury hotels",
    flight_date: date | str | None = None,
) -> str:
    """Return a prompt injection string with live trending keywords."""
    keywords = await get_trending_keywords(market, segment, flight_date)
    if not keywords:
        return ""

    kw_str = ", ".join(f'"{k}"' for k in keywords)
    return (
        f"\n## LIVE TREND SIGNALS (Google Search — {date.today().isoformat()}):\n"
        f"Trending keywords in {segment} ({market}): {kw_str}\n"
        "Consider weaving relevant trend signals into your copy where natural.\n"
    )
