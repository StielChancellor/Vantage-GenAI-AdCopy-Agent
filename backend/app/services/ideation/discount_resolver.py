"""Discount resolver (v2.9 — mirrors hotels resolver).

Takes a free-text phrase like "flat 3000 off plus free spa credit" and
returns a structured discount object:
  { kind, value, notes }

`kind` is constrained to the IdeationDiscount enum:
  percent_off | flat_amount | bogo | free_upgrade | no_discount

`value` is a short string that downstream prompts can splice into the
brief (e.g. "25", "3000", "2+1", "suite + breakfast").

`notes` is a one-line human-readable rephrasing that the UI shows as a
chip and exporters surface in the CSV/HTML output.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("vantage.ideation.discount_resolver")


_SYSTEM_PROMPT = """You normalise hospitality discount phrases into a structured object.

KIND ENUM (pick ONE):
- "percent_off"   — any percentage off ("25% off", "10 percent on weekday rates")
- "flat_amount"   — a flat currency value off ("flat 3000 off", "Rs.5000 reduction")
- "bogo"          — buy-N-get-M ("buy 2 nights get 1 free", "BOGO weekend")
- "free_upgrade"  — a complimentary upgrade or value-add ("free upgrade to suite", "complimentary breakfast included")
- "no_discount"   — no monetary discount mentioned, or phrase is empty / "none"

VALUE FIELD:
- For percent_off  → the numeric percent ("25").
- For flat_amount  → the numeric amount, no currency symbol ("3000").
- For bogo         → "N+M" notation ("2+1", "3+1").
- For free_upgrade → short description of what's upgraded ("suite + breakfast", "club lounge access").
- For no_discount  → empty string.

NOTES FIELD:
A one-line human-readable rephrasing of the user's phrase that downstream
copy can quote ("Rs.3000 off + complimentary spa credit"). Use Rs. for
rupees (no special characters). Keep under 110 chars.

OUTPUT — return ONLY valid JSON in exactly this schema:
{
  "kind": "percent_off | flat_amount | bogo | free_upgrade | no_discount",
  "value": "...",
  "notes": "..."
}
"""


async def resolve_discount(phrase: str) -> dict:
    """Resolve a free-text discount phrase to the structured shape.
    Returns a dict ready for the IdeationDiscount Pydantic model."""
    phrase = (phrase or "").strip()
    if not phrase or phrase.lower() in {"none", "no discount", "n/a"}:
        return {"kind": "no_discount", "value": "", "notes": ""}

    from backend.app.core.vertex_client import get_generative_model

    user_prompt = f'USER PHRASE:\n"{phrase}"\n\nReturn JSON only.'

    try:
        model = get_generative_model(system_instruction=_SYSTEM_PROMPT)
        response = model.generate_content(user_prompt)
        raw = getattr(response, "text", "") or ""
    except Exception as exc:
        logger.warning("discount_resolver LLM call failed: %s", exc)
        return {"kind": "no_discount", "value": "", "notes": phrase[:110]}

    parsed = _parse_json(raw)
    if not parsed:
        return {"kind": "no_discount", "value": "", "notes": phrase[:110]}

    kind = str(parsed.get("kind") or "").strip().lower()
    valid_kinds = {"percent_off", "flat_amount", "bogo", "free_upgrade", "no_discount"}
    if kind not in valid_kinds:
        kind = "no_discount"

    return {
        "kind": kind,
        "value": str(parsed.get("value") or "").strip()[:80],
        "notes": str(parsed.get("notes") or phrase).strip()[:200],
    }


def _parse_json(text: str) -> dict:
    if not text:
        return {}
    raw = text.strip()
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in raw:
        raw = raw.split("```", 1)[1].split("```", 1)[0]
    try:
        data = json.loads(raw.strip())
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        logger.debug("discount_resolver JSON parse failed; raw=%s", raw[:300])
    return {}
