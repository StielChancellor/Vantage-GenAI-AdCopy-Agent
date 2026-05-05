"""Indian hospitality seasonal awareness engine.

Given a campaign flight date, returns the active seasonal context and
estimated demand uplift. Injects this into generation prompts automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class SeasonalContext:
    name: str
    description: str
    demand_uplift_pct: float = 0.0  # estimated % uplift (positive = peak demand)
    keywords: list[str] = field(default_factory=list)
    tone_hint: str = ""


# Indian hospitality calendar — (month, day_start, day_end, context)
# Approximate date ranges; for precise dates use a holidays library
_CALENDAR: list[dict] = [
    # Q1 — New Year, Republic Day, Valentine's
    {"months": [1], "days": (1, 5), "context": SeasonalContext(
        "New Year Celebrations", "New Year parties, staycations, and celebrations",
        demand_uplift_pct=35, keywords=["New Year", "celebrate", "ring in", "new beginnings"],
        tone_hint="festive, exciting, celebratory",
    )},
    {"months": [1], "days": (24, 27), "context": SeasonalContext(
        "Republic Day Long Weekend", "Republic Day weekend getaway",
        demand_uplift_pct=15, keywords=["long weekend", "getaway", "explore", "patriotic"],
        tone_hint="patriotic, adventurous",
    )},
    {"months": [2], "days": (12, 16), "context": SeasonalContext(
        "Valentine's Day", "Romantic getaway packages, couples dining",
        demand_uplift_pct=40, keywords=["romantic", "couples", "love", "anniversary", "intimate"],
        tone_hint="romantic, warm, intimate",
    )},
    # Q2 — Holi, summer, IPL
    {"months": [3], "days": (1, 31), "context": SeasonalContext(
        "Holi Festival", "Holi celebrations, festive dining, color events",
        demand_uplift_pct=20, keywords=["Holi", "festive", "colors", "celebrations", "spring"],
        tone_hint="vibrant, festive, fun",
    )},
    {"months": [4, 5, 6], "days": (1, 31), "context": SeasonalContext(
        "IPL Season & Summer Holidays", "IPL viewing packages, summer staycation, kids activities",
        demand_uplift_pct=25, keywords=["summer", "staycation", "IPL", "family", "kids", "pool", "escape the heat"],
        tone_hint="fun, family-friendly, exciting",
    )},
    # Q3 — Monsoon, Independence Day
    {"months": [7, 8, 9], "days": (1, 31), "context": SeasonalContext(
        "Monsoon Season", "Monsoon spa retreats, couples packages, cozy staycations",
        demand_uplift_pct=-10, keywords=["monsoon", "cozy", "spa", "retreat", "romance", "refresh"],
        tone_hint="calm, indulgent, rejuvenating",
    )},
    {"months": [8], "days": (13, 17), "context": SeasonalContext(
        "Independence Day Long Weekend", "Patriotic staycation, family getaway",
        demand_uplift_pct=20, keywords=["Independence Day", "long weekend", "family", "celebrate India"],
        tone_hint="patriotic, festive, family",
    )},
    # Q4 — Navratri, Diwali, Christmas, NYE
    {"months": [10], "days": (1, 31), "context": SeasonalContext(
        "Navratri & Festive Season Begins", "Navratri events, garba nights, festive dining",
        demand_uplift_pct=30, keywords=["Navratri", "festive", "garba", "celebration", "tradition"],
        tone_hint="festive, cultural, vibrant",
    )},
    {"months": [10, 11], "days": (20, 10), "context": SeasonalContext(
        "Diwali Season", "Diwali staycation, festive dining, gifting packages, family reunions",
        demand_uplift_pct=55, keywords=["Diwali", "festive", "celebration", "lights", "family", "gifting", "luxury"],
        tone_hint="warm, festive, luxurious, celebratory",
    )},
    {"months": [12], "days": (20, 31), "context": SeasonalContext(
        "Christmas & New Year Eve", "Christmas celebrations, NYE parties, family gatherings",
        demand_uplift_pct=60, keywords=["Christmas", "New Year", "festive", "celebrations", "holiday season", "family"],
        tone_hint="festive, warm, celebratory, luxurious",
    )},
    # Wedding season (Nov-Feb)
    {"months": [11, 12, 1, 2], "days": (1, 28), "context": SeasonalContext(
        "Indian Wedding Season", "Wedding venue, honeymoon packages, social events",
        demand_uplift_pct=45, keywords=["wedding", "banquet", "honeymoon", "reception", "celebration", "venue"],
        tone_hint="elegant, grand, celebratory",
    )},
]


def get_seasonal_context(flight_date: date | str | None = None) -> list[SeasonalContext]:
    """Return active seasonal contexts for a given flight date.

    Args:
        flight_date: Target date (date object, ISO string, or None for today).

    Returns:
        List of active SeasonalContext objects (may be multiple overlapping seasons).
    """
    if flight_date is None:
        target = date.today()
    elif isinstance(flight_date, str):
        try:
            target = datetime.fromisoformat(flight_date).date()
        except ValueError:
            target = date.today()
    else:
        target = flight_date

    active = []
    for entry in _CALENDAR:
        if target.month in entry["months"]:
            active.append(entry["context"])

    # Deduplicate by name
    seen = set()
    result = []
    for ctx in active:
        if ctx.name not in seen:
            seen.add(ctx.name)
            result.append(ctx)

    return result


def build_seasonal_prompt_context(flight_date: date | str | None = None) -> str:
    """Build a prompt injection string describing the current seasonal context."""
    contexts = get_seasonal_context(flight_date)
    if not contexts:
        return ""

    lines = ["\n## SEASONAL MARKET CONTEXT (inject into campaign):"]
    for ctx in contexts:
        lines.append(f"\n### {ctx.name}")
        lines.append(f"- Demand uplift: {'▲' if ctx.demand_uplift_pct > 0 else '▼'} {abs(ctx.demand_uplift_pct)}% vs off-season")
        lines.append(f"- Description: {ctx.description}")
        if ctx.keywords:
            lines.append(f"- Recommended keywords: {', '.join(ctx.keywords[:6])}")
        if ctx.tone_hint:
            lines.append(f"- Tone: {ctx.tone_hint}")
    lines.append("\nUse the seasonal context above to make ads timely and relevant.")
    return "\n".join(lines)
