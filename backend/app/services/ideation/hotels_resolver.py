"""Natural-language hotels resolver (v2.8 Campaign Ideation).

Takes a free-text phrase like "all hill hotels in north India" + the
project's `hotels` catalog and asks Gemini to return the matching
hotel_ids. Preview is rendered back to the user as chips; they can edit
before continuing. Loyalty flag is set when Club ITC matches.

The function NEVER hallucinates hotel_ids: the model is constrained to
pick ids from the catalog summary we send it.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("vantage.ideation.hotels_resolver")


_SYSTEM_PROMPT = """You are a hospitality data assistant. The user describes a set of properties in plain English. Your job is to pick the matching property ids (`hotel_id`) from the provided catalog.

RULES
1. Output ONLY hotel_ids that exist in the catalog. Never invent.
2. Match generously on intent — "hill hotels in north India" matches every property whose city sits in a hill region of North India, AND whose status='active'. Use the city + brand_name fields as your evidence.
3. When the phrase mentions "loyalty" or "Club ITC" or "members" — include the loyalty brand (`kind='loyalty'`) and set is_loyalty=true.
4. When the phrase says "all" with a region or brand qualifier, match liberally. When it names a specific city, match strictly to that city.
5. Add a short `notes` line explaining how you matched, so the user can sanity-check (≤ 25 words).

OUTPUT — return ONLY valid JSON in exactly this schema:
{
  "hotel_ids": ["..."],
  "brand_ids": ["..."],
  "is_loyalty": false,
  "notes": "Matched 6 properties in Shimla, Manali, Mussoorie, McLeodganj — all marked hill destinations."
}
"""


async def resolve_hotels(phrase: str) -> dict:
    """Resolve `phrase` to a concrete hotel list.

    Returns a dict ready to feed into ResolveHotelsResponse:
      {hotel_ids, brand_ids, is_loyalty, matched: [...full refs], notes}
    """
    phrase = (phrase or "").strip()
    if not phrase:
        return {"hotel_ids": [], "brand_ids": [], "is_loyalty": False, "matched": [], "notes": ""}

    from backend.app.services.hotels import catalog as hotel_catalog
    from backend.app.core.vertex_client import get_generative_model

    # Pull the full catalog once. Admin caller perspective (None scopes).
    try:
        hotels = hotel_catalog.list_hotels()
        brands = hotel_catalog.list_brands()
    except Exception as exc:
        logger.warning("hotels_resolver: catalog load failed: %s", exc)
        return {"hotel_ids": [], "brand_ids": [], "is_loyalty": False, "matched": [], "notes": "Catalog unavailable"}

    by_id = {h["hotel_id"]: h for h in hotels}
    brands_by_id = {b["brand_id"]: b for b in brands}

    catalog_summary = {
        "hotels": [
            {
                "hotel_id": h["hotel_id"],
                "name": h.get("hotel_name", ""),
                "brand_id": h.get("brand_id", ""),
                "brand_name": h.get("brand_name", ""),
                "city": h.get("city", ""),
            }
            for h in hotels
        ],
        "brands": [
            {
                "brand_id": b["brand_id"],
                "name": b.get("brand_name", ""),
                "kind": b.get("kind", "hotel"),
            }
            for b in brands
        ],
    }

    user_prompt = (
        f"USER PHRASE:\n{phrase}\n\n"
        f"CATALOG (filter to subset matching the phrase):\n{json.dumps(catalog_summary)}\n\n"
        "Return JSON only."
    )

    try:
        model = get_generative_model(system_instruction=_SYSTEM_PROMPT)
        response = model.generate_content(user_prompt)
        raw = getattr(response, "text", "") or ""
    except Exception as exc:
        logger.warning("hotels_resolver LLM call failed: %s", exc)
        return {"hotel_ids": [], "brand_ids": [], "is_loyalty": False, "matched": [], "notes": "Resolver call failed"}

    parsed = _parse_json(raw)
    if not parsed:
        return {"hotel_ids": [], "brand_ids": [], "is_loyalty": False, "matched": [], "notes": "Could not parse model response"}

    hotel_ids = [str(x) for x in (parsed.get("hotel_ids") or []) if str(x) in by_id]
    brand_ids = [str(x) for x in (parsed.get("brand_ids") or []) if str(x) in brands_by_id]

    # Derive is_loyalty from the brands_by_id, in case model missed it.
    is_loyalty = bool(parsed.get("is_loyalty"))
    for bid in brand_ids:
        if brands_by_id.get(bid, {}).get("kind") == "loyalty":
            is_loyalty = True
            break

    matched = []
    for hid in hotel_ids:
        h = by_id.get(hid) or {}
        matched.append({
            "hotel_id": hid,
            "name": h.get("hotel_name", ""),
            "brand": h.get("brand_name", ""),
            "brand_id": h.get("brand_id", ""),
            "city": h.get("city", ""),
        })

    return {
        "hotel_ids": hotel_ids,
        "brand_ids": brand_ids,
        "is_loyalty": is_loyalty,
        "matched": matched,
        "notes": (parsed.get("notes") or "").strip()[:250],
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
        logger.debug("hotels_resolver JSON parse failed; raw=%s", raw[:300])
    return {}
