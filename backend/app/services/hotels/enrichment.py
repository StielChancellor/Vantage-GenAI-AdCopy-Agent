"""Hotel enrichment — resolve gmb_place_id and attach a review snapshot.

Best-effort, fire-and-forget. Errors are logged and never propagate.
Called after CSV ingestion or manual single-hotel form submission.

The Google Places autocomplete + Place Details flow is wrapped here rather
than in `places.py` directly so we can dedupe by hotel_code and avoid
unnecessary GMB lookups.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("vantage.hotels.enrichment")


async def enrich_hotel(hotel_id: str) -> dict:
    """Resolve gmb_place_id for a single hotel, store on the doc.

    Returns a status dict for the caller. Designed for asyncio.gather() across
    a freshly-ingested batch.
    """
    from backend.app.core.database import get_firestore
    from backend.app.services.hotels.catalog import get_hotel

    hotel = get_hotel(hotel_id)
    if not hotel:
        return {"hotel_id": hotel_id, "status": "missing"}

    if hotel.get("gmb_place_id"):
        return {"hotel_id": hotel_id, "status": "already_enriched"}

    gmb_url = hotel.get("gmb_url", "")
    hotel_name = hotel.get("hotel_name", "")
    place_id = ""

    # 1. If gmb_url already contains a place_id, just extract it
    if gmb_url:
        place_id = _extract_place_id(gmb_url)

    # 2. Otherwise, do a Places Find Place lookup by name
    if not place_id and hotel_name:
        try:
            place_id = await _find_place_by_text(hotel_name)
        except Exception as exc:
            logger.warning("Find Place failed for %s: %s", hotel_name, exc)

    if place_id:
        try:
            db = get_firestore()
            db.collection("hotels").document(hotel_id).set({
                "gmb_place_id": place_id,
                "last_enriched_at": datetime.now(timezone.utc).isoformat(),
            }, merge=True)
            return {"hotel_id": hotel_id, "status": "enriched", "place_id": place_id}
        except Exception as exc:
            logger.warning("Enrichment write failed for %s: %s", hotel_id, exc)
            return {"hotel_id": hotel_id, "status": "write_failed", "error": str(exc)[:120]}

    return {"hotel_id": hotel_id, "status": "no_place_id_resolved"}


async def enrich_batch(hotel_ids: list[str], concurrency: int = 4) -> list[dict]:
    """Enrich many hotels in parallel with bounded concurrency."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(hid: str) -> dict:
        async with sem:
            return await enrich_hotel(hid)

    return await asyncio.gather(*[_one(h) for h in hotel_ids])


# ──────────────────────────────────────────────────────────────────


def _extract_place_id(gmb_url: str) -> str:
    """Best-effort parse of a Maps URL for ChIJ-style place IDs."""
    import re
    if not gmb_url:
        return ""
    # ChIJ... or 0x...
    m = re.search(r"(ChIJ[\w-]{20,}|0x[0-9a-fA-F:]{16,})", gmb_url)
    if m:
        return m.group(1)
    # placeid query param
    m = re.search(r"[?&]placeid=([^&]+)", gmb_url)
    if m:
        return m.group(1)
    return ""


async def _find_place_by_text(query: str) -> str:
    """Call the existing places service if available, return place_id or empty."""
    try:
        # Use the same client the rest of the app uses for Find Place.
        import os
        import httpx
        from backend.app.core.config import get_settings

        settings = get_settings()
        api_key = settings.get_places_api_key() if settings.ENVIRONMENT == "production" else os.environ.get("GOOGLE_PLACES_API_KEY", "")
        if not api_key:
            return ""

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
                params={
                    "input": query,
                    "inputtype": "textquery",
                    "fields": "place_id,name",
                    "key": api_key,
                },
            )
            if r.status_code != 200:
                return ""
            data = r.json()
            candidates = data.get("candidates", [])
            if candidates:
                return candidates[0].get("place_id", "")
    except Exception:
        return ""
    return ""
