"""Knowledge Base — admin-only hierarchical view of brands → hotels → USPs + notes.

Aggregates from:
  - brands collection                (brand metadata, voice)
  - hotels collection                (hotel metadata, attributes)
  - embedding_cache (filter campaign_type='brand_usp') (USPs)
  - training_state (training notes / remarks per training run, filtered to relevant entity)

Editing is intentionally not supported here — the spec calls for editing
through the training module so updates flow through the normal pipeline.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.app.core.auth import require_admin
from backend.app.core.database import get_firestore
from backend.app.services.hotels import catalog as hotel_catalog

logger = logging.getLogger("vantage.kb")
router = APIRouter(prefix="/kb", tags=["KnowledgeBase"])


def _collect_usps_for_brand(db, brand_id: str, brand_name: str, hotel_id: str | None = None) -> list[dict]:
    """Pull brand-level (or hotel-level when hotel_id provided) USP records from
    the embedding_cache. We tagged scope+brand_id+hotel_id as `raw_ad_type` in
    the brand_usp adapter, but in the Firestore embedding_cache doc we have
    `campaign_type`, `headline` (the USP text), and metadata.
    """
    usps: list[dict] = []
    coll = (
        db.collection("embedding_cache")
        .where("campaign_type", "==", "brand_usp")
    )
    for d in coll.stream():
        data = d.to_dict() or {}
        # The adapter encodes brand context in the description; we also persisted brand_id via metadata
        if data.get("brand_id") and data["brand_id"] != brand_id:
            continue
        # If we have business_name (brand_name) we can use it as a fallback filter
        bn = data.get("business_name") or ""
        if bn and brand_name and bn.strip().lower() != brand_name.strip().lower():
            continue
        # Determine scope by looking at the description content (adapter used a stable suffix)
        desc = data.get("description") or ""
        is_brand_level = "(brand-level)" in desc
        if hotel_id is not None and is_brand_level:
            continue
        if hotel_id is None and not is_brand_level:
            continue
        usps.append({
            "usp": data.get("headline", ""),
            "added_at": data.get("ingested_at") or data.get("updated_at") or "",
        })
    # Dedupe by lowercase usp text
    seen = set()
    out = []
    for u in usps:
        key = u["usp"].strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(u)
    return out


def _collect_training_notes(db, brand_id: str | None = None, hotel_id: str | None = None) -> list[dict]:
    """Return the remarks / status from training_state runs that touched this entity.
    Best-effort: training_state stores brand_id (the user-supplied display name)
    so we filter loosely.
    """
    notes: list[dict] = []
    try:
        for d in db.collection("training_state").order_by("created_at", direction="DESCENDING").limit(200).stream():
            data = d.to_dict() or {}
            if brand_id and data.get("brand_id") and brand_id and brand_id not in str(data.get("brand_id", "")):
                continue
            remark = (data.get("remarks") or "").strip()
            if not remark:
                continue
            notes.append({
                "remark": remark,
                "section_type": data.get("section_type", ""),
                "created_at": data.get("created_at", ""),
                "session_id": data.get("session_id", ""),
            })
    except Exception as exc:
        logger.debug("training_state scan failed: %s", exc)
    return notes


@router.get("/tree")
async def kb_tree(brand_id: str | None = None, _admin=Depends(require_admin)):
    """Hierarchical KB. Pass brand_id to drill into a single brand for performance."""
    db = get_firestore()

    # Decide which brands to render
    if brand_id:
        b = hotel_catalog.get_brand(brand_id)
        if not b:
            raise HTTPException(404, "Brand not found")
        brands = [b]
    else:
        brands = hotel_catalog.list_brands()

    out_brands: list[dict] = []
    for b in brands:
        bid = b["brand_id"]
        bname = b.get("brand_name", "")
        brand_block = {
            "brand_id": bid,
            "brand_name": bname,
            "voice": b.get("voice", ""),
            "hotel_count": int(b.get("hotel_count", 0)),
            "usps": _collect_usps_for_brand(db, bid, bname, hotel_id=None),
            "training_notes": _collect_training_notes(db, brand_id=bname),
            "hotels": [],
        }
        for h in hotel_catalog.hotels_for_brand(bid):
            hid = h["hotel_id"]
            hname = h.get("hotel_name", "")
            brand_block["hotels"].append({
                "hotel_id": hid,
                "hotel_name": hname,
                "hotel_code": h.get("hotel_code", ""),
                "rooms_count": h.get("rooms_count"),
                "fnb_count": h.get("fnb_count"),
                "website_url": h.get("website_url", ""),
                "gmb_url": h.get("gmb_url", ""),
                "gmb_place_id": h.get("gmb_place_id", ""),
                "usps": _collect_usps_for_brand(db, bid, bname, hotel_id=hid),
                "training_notes": _collect_training_notes(db, brand_id=hname),
            })
        out_brands.append(brand_block)

    return {"brands": out_brands}
