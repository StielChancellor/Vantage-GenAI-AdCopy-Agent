"""Campaign brief structurer (v2.6).

Turns the user's messy free-form brief into a structured JSON object
matching `StructuredCampaign`. Best-effort: prefers a Gemini call with a
strict JSON schema prompt; falls back to a regex/heuristic pass when the
LLM call fails or returns un-parseable output.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Iterable

logger = logging.getLogger("vantage.campaigns.structurer")


_SYSTEM_PROMPT = (
    "You are an expert hotel-marketing analyst. Your job is to read a free-form "
    "campaign brief and extract a clean structured JSON. Output ONLY valid JSON "
    "with no commentary, no markdown fences. Use empty strings or empty arrays for "
    "fields the brief does not mention. Dates must be ISO YYYY-MM-DD. Hotels list "
    "entries are objects with `hotel_name`.\n\n"
    "campaign_name MUST be a SHORT memorable name (≤ 60 chars). If the user did "
    "not state an explicit name, GENERATE a catchy 3-6 word marketing name from "
    "the brief's hooks (e.g. theme + year, or property + occasion). Examples: "
    "'Diwali Sparkle 2026', '20th Anniversary Stay', 'Monsoon Reset Mumbai', "
    "'Festive Family Escape'. NEVER copy the whole brief into campaign_name."
)

_JSON_SHAPE = """{
  "campaign_name": "",
  "start_date": "",
  "end_date": "",
  "booking_window_start": "",
  "booking_window_end": "",
  "cancellation_policy": "",
  "inclusions": "",
  "promo_code": "",
  "landing_page_url": "",
  "participating_hotels": [{"hotel_name": ""}],
  "brand_ids": [],
  "cities": [],
  "target_audience": "",
  "summary": ""
}"""


async def structure_brief(raw_brief: str, reference_urls: Iterable[str] | None = None) -> dict:
    """Best-effort structure of a free-form brief. Always returns a dict
    that fits StructuredCampaign (campaign_name will fall back to a
    truncated slice of raw_brief if extraction fails)."""
    raw_brief = (raw_brief or "").strip()
    if not raw_brief:
        return _heuristic_fallback("", reference_urls)

    prompt = (
        "Extract the following JSON from the brief below. Return ONLY the JSON "
        "object — nothing else.\n\n"
        f"JSON SHAPE:\n{_JSON_SHAPE}\n\n"
        f"REFERENCE URLs:\n{', '.join(reference_urls or [])}\n\n"
        f"BRIEF:\n{raw_brief}"
    )

    try:
        from backend.app.core.vertex_client import get_generative_model
        model = get_generative_model("gemini-2.5-flash", system_instruction=_SYSTEM_PROMPT)
        response = model.generate_content(prompt)
        text = (response.text or "").strip()
        # Defensive: strip code fences if Gemini ignores instructions.
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                # take the largest fenced block
                text = max((p for p in parts), key=len)
        text = text.strip().lstrip("json").strip()
        data = json.loads(text)
        return _normalize(data, raw_brief)
    except Exception as exc:  # noqa: BLE001
        logger.warning("structurer LLM path failed: %s", exc)
        return _heuristic_fallback(raw_brief, reference_urls)


# ── helpers ──────────────────────────────────────────────

def _normalize(data: dict, raw: str) -> dict:
    """Ensure required keys + sensible defaults regardless of model output."""
    out = {
        "campaign_name": _short_name(data.get("campaign_name") or "", raw),
        "start_date": data.get("start_date") or "",
        "end_date": data.get("end_date") or "",
        "booking_window_start": data.get("booking_window_start") or "",
        "booking_window_end": data.get("booking_window_end") or "",
        "cancellation_policy": data.get("cancellation_policy") or "",
        "inclusions": data.get("inclusions") or "",
        "promo_code": (data.get("promo_code") or "").upper(),
        "landing_page_url": data.get("landing_page_url") or "",
        "participating_hotels": [
            {"hotel_name": h.get("hotel_name", "") if isinstance(h, dict) else str(h)}
            for h in (data.get("participating_hotels") or [])
            if (isinstance(h, dict) and h.get("hotel_name")) or isinstance(h, str)
        ],
        "brand_ids": list(data.get("brand_ids") or []),
        "cities": list(data.get("cities") or []),
        "target_audience": data.get("target_audience") or "",
        "summary": data.get("summary") or "",
    }
    return out


_PROMO_RE = re.compile(r"\b(?:promo(?:\s*code)?|code)[\s:]+([A-Z0-9_-]{3,20})\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s)]+")
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{2,4})\b", re.IGNORECASE)


def _heuristic_fallback(raw: str, reference_urls: Iterable[str] | None = None) -> dict:
    """Keyword-grep fallback when the LLM call is unavailable."""
    promo_match = _PROMO_RE.search(raw or "")
    url_match = _URL_RE.search(raw or "")
    dates = _DATE_RE.findall(raw or "")
    return {
        "campaign_name": _short_name("", raw) or "Untitled campaign",
        "start_date": dates[0] if dates else "",
        "end_date": dates[1] if len(dates) > 1 else "",
        "booking_window_start": "",
        "booking_window_end": "",
        "cancellation_policy": "",
        "inclusions": "",
        "promo_code": (promo_match.group(1).upper() if promo_match else ""),
        "landing_page_url": (url_match.group(0) if url_match else (next(iter(reference_urls or []), ""))),
        "participating_hotels": [],
        "brand_ids": [],
        "cities": [],
        "target_audience": "",
        "summary": (raw or "")[:400],
    }


def _first_line(text: str) -> str:
    if not text:
        return ""
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s
    return text.strip()


_KEYWORD_HINTS = [
    "diwali", "holi", "christmas", "new year", "anniversary", "summer",
    "monsoon", "winter", "spring", "festive", "loyalty", "weekend",
    "honeymoon", "wedding", "easter", "ramadan", "republic day",
    "independence", "puja", "navratri", "onam", "pongal", "eid",
]


def _short_name(candidate: str, raw: str) -> str:
    """Coerce a model-supplied or raw-derived name to ≤ 60 chars and ≤ 8 words.

    If the candidate is too long (the model echoed the brief), build a
    catchy fallback from the first promising keyword + a 4-digit year if
    present in the raw brief.
    """
    text = (candidate or "").strip()
    if text:
        words = text.split()
        # If the model returned a sentence-like blob, trim aggressively.
        if len(text) <= 60 and len(words) <= 8:
            return text
    # Fallback: pull a marketing-flavoured keyword + the year.
    raw_l = (raw or "").lower()
    year_match = re.search(r"\b(20\d{2})\b", raw or "")
    year = year_match.group(1) if year_match else ""
    hit = next((k for k in _KEYWORD_HINTS if k in raw_l), "")
    if hit:
        base = hit.title()
        if year:
            return f"{base} {year}"
        return f"{base} Stay"
    # Last resort: a couple of clean tokens from the first line.
    line = _first_line(raw or candidate)
    tokens = re.findall(r"[A-Za-z0-9]+", line)
    tokens = [t for t in tokens if len(t) > 2][:5]
    if year and year not in tokens:
        tokens.append(year)
    name = " ".join(t.capitalize() if t.islower() else t for t in tokens)[:60]
    return name or "Untitled campaign"
