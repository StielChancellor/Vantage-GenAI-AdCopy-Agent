"""Hotel & Brand catalog API (v2.2).

All write endpoints (ingest / create / patch / delete) are admin-only.
Read endpoints (list, get, search) are role-aware: non-admin callers see
only hotels/brands inside their property_assignments allowlist.
"""
from __future__ import annotations

import asyncio
import io
import logging

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.app.core.auth import (
    get_current_user, require_admin, ROLE_ADMIN,
    _get_user_assignments, has_group_scope, resolve_user_hotel_ids,
    resolve_user_brand_ids, user_can_access_hotel, user_can_access_brand,
)
from backend.app.models.schemas import (
    HotelOut, BrandOut, HotelIngestResponse,
)
from backend.app.services.hotels import catalog, enrichment

logger = logging.getLogger("vantage.routers.hotels")
router = APIRouter(prefix="/hotels", tags=["Hotels"])


# ──────────────────────────────────────────────────────
# Read endpoints — role-scoped
# ──────────────────────────────────────────────────────


def _allowed_scopes(current_user: dict) -> tuple[list[str] | None, list[str] | None]:
    """Return (allowed_hotel_ids, allowed_brand_ids).

    Returns (None, None) for admin or any user holding a 'group' assignment
    (= unlimited). Otherwise expands brand + city + hotel grants to a flat
    hotel-id allowlist."""
    if current_user.get("role") == ROLE_ADMIN or has_group_scope(current_user):
        return None, None
    hotel_ids = resolve_user_hotel_ids(current_user) or []
    brand_ids = resolve_user_brand_ids(current_user) or []
    return hotel_ids, brand_ids


@router.get("")
async def list_hotels(
    brand_id: str | None = None,
    q: str | None = None,
    page: int = 1,
    current_user: dict = Depends(get_current_user),
):
    allowed_hotel_ids, allowed_brand_ids = _allowed_scopes(current_user)
    rows = catalog.list_hotels(
        brand_id=brand_id, q=q, page=page,
        allowed_hotel_ids=allowed_hotel_ids,
        allowed_brand_ids=allowed_brand_ids,
    )
    return {"hotels": rows, "count": len(rows)}


@router.get("/brands")
async def list_brands(current_user: dict = Depends(get_current_user)):
    _allowed_hotel_ids, allowed_brand_ids = _allowed_scopes(current_user)
    rows = catalog.list_brands(allowed_brand_ids=allowed_brand_ids)
    return {"brands": rows, "count": len(rows)}


@router.get("/scope-search")
async def scope_search(
    q: str = "",
    limit: int = 30,
    include_empty: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Free-flow brand/hotel/city search for the IntelligentPropertyPicker.

    v2.4 — non-admin callers see entities they have access to. include_empty=True
    lets the picker pre-populate the dropdown with the user's whole accessible
    set (no typing required) — used for the "show me what I can pick" initial
    render."""
    rows = catalog.search_scope(q, limit=limit, include_empty=include_empty)
    role = current_user.get("role", "")
    if role == ROLE_ADMIN or has_group_scope(current_user):
        return {"results": rows}

    assignments = _get_user_assignments(current_user.get("uid", ""))
    allowed_brand = {a.get("brand_id") for a in assignments if a.get("scope") == "brand" and a.get("brand_id")}
    allowed_hotel = {a.get("hotel_id") for a in assignments if a.get("scope") == "hotel" and a.get("hotel_id")}
    allowed_city = {(a.get("city") or "").strip() for a in assignments if a.get("scope") == "city"}
    allowed_city.discard("")

    filtered = []
    for r in rows:
        t = r.get("type")
        if t == "brand" and r["id"] in allowed_brand:
            filtered.append(r)
        elif t == "city" and r["label"] in allowed_city:
            filtered.append(r)
        elif t == "hotel" and (
            r["id"] in allowed_hotel
            or r.get("brand_id") in allowed_brand
            or (r.get("city") or "").strip() in allowed_city
        ):
            filtered.append(r)
    return {"results": filtered}


@router.get("/cities")
async def list_cities(current_user: dict = Depends(get_current_user)):
    """Return distinct hotel cities (with hotel counts) the user can see.

    Admin/group sees every city. Other users see only the cities containing
    at least one hotel they can access via brand/hotel/city grants."""
    rows = catalog.list_cities()
    if current_user.get("role") == ROLE_ADMIN or has_group_scope(current_user):
        return {"cities": rows}
    allowed_hotel_ids = set(resolve_user_hotel_ids(current_user) or [])
    if not allowed_hotel_ids:
        return {"cities": []}
    # Build a city → set of accessible hotel_ids map.
    from backend.app.core.database import get_firestore
    db = get_firestore()
    accessible: dict[str, int] = {}
    for hid in allowed_hotel_ids:
        d = db.collection("hotels").document(hid).get()
        if not d.exists:
            continue
        city = ((d.to_dict() or {}).get("city") or "").strip()
        if city:
            accessible[city] = accessible.get(city, 0) + 1
    return {"cities": [{"city": c, "hotel_count": n} for c, n in sorted(accessible.items())]}


@router.get("/{hotel_id}")
async def get_hotel(hotel_id: str, current_user: dict = Depends(get_current_user)):
    if not user_can_access_hotel(current_user, hotel_id):
        raise HTTPException(403, "Access denied for this hotel.")
    h = catalog.get_hotel(hotel_id)
    if not h:
        raise HTTPException(404, "Hotel not found.")
    return h


@router.get("/{hotel_id}/context")
async def get_hotel_context(hotel_id: str, current_user: dict = Depends(get_current_user)):
    """One-shot bundle the Ad Copy form needs to auto-fill itself: the hotel
    record, its brand, brand+hotel USPs, and the caller's most recent
    generations for THIS hotel. Single round-trip."""
    if not user_can_access_hotel(current_user, hotel_id):
        raise HTTPException(403, "Access denied for this hotel.")
    h = catalog.get_hotel(hotel_id)
    if not h:
        raise HTTPException(404, "Hotel not found.")

    brand = catalog.get_brand(h.get("brand_id", "")) or {}

    # Pull USPs from the embedding cache (brand-level + hotel-level matches).
    usps: list[dict] = []
    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
        # Brand-level USPs (campaign_type='brand_usp', brand_id matches, no hotel attached)
        for d in db.collection("embedding_cache") \
                   .where("campaign_type", "==", "brand_usp") \
                   .where("brand_id", "==", h.get("brand_id", "")) \
                   .limit(50).stream():
            data = d.to_dict() or {}
            level = "hotel" if (data.get("hotel_id") == hotel_id) else "brand"
            if data.get("hotel_id") and data.get("hotel_id") != hotel_id:
                continue   # USP for a different hotel
            usp_text = data.get("description") or data.get("usp") or ""
            if usp_text:
                usps.append({"usp": usp_text, "level": level, "added_at": data.get("created_at", "")})
    except Exception as exc:
        logger.debug("USP fetch failed for hotel %s: %s", hotel_id, exc)

    # Last 5 generations BY THIS USER FOR THIS HOTEL.
    recent: list[dict] = []
    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
        # Tolerant query — drop order_by if a composite index isn't present.
        try:
            stream = (
                db.collection("audit_logs")
                .where("user_email", "==", current_user.get("sub", ""))
                .where("hotel_name", "==", h.get("hotel_name", ""))
                .order_by("timestamp", direction="DESCENDING")
                .limit(5).stream()
            )
            docs = list(stream)
        except Exception:
            docs = list(
                db.collection("audit_logs")
                .where("user_email", "==", current_user.get("sub", ""))
                .where("hotel_name", "==", h.get("hotel_name", ""))
                .limit(50).stream()
            )
            docs.sort(key=lambda d: (d.to_dict() or {}).get("timestamp", ""), reverse=True)
            docs = docs[:5]
        for d in docs:
            data = d.to_dict() or {}
            if data.get("action") != "generate":
                continue
            recent.append({
                "generation_id": data.get("generation_id", ""),
                "offer_name": data.get("offer_name", ""),
                "platforms": data.get("platforms", []),
                "timestamp": data.get("timestamp", ""),
            })
    except Exception as exc:
        logger.debug("Recent-generations fetch failed: %s", exc)

    return {
        "hotel": h,
        "brand": brand,
        "usps": usps,
        "recent_generations": recent,
    }


@router.get("/brands/{brand_id}")
async def get_brand(brand_id: str, current_user: dict = Depends(get_current_user)):
    role = current_user.get("role", "")
    if role != ROLE_ADMIN and not user_can_access_brand(current_user, brand_id):
        # Allow read if user has any hotel under this brand
        assignments = _get_user_assignments(current_user.get("uid", ""))
        hotels = catalog.hotels_for_brand(brand_id)
        hotel_ids = {h["hotel_id"] for h in hotels}
        own = [a.get("hotel_id") for a in assignments if a.get("scope") == "hotel"]
        if not (set(own) & hotel_ids):
            raise HTTPException(403, "Access denied for this brand.")
    b = catalog.get_brand(brand_id)
    if not b:
        raise HTTPException(404, "Brand not found.")
    b["hotels"] = catalog.hotels_for_brand(brand_id)
    return b


@router.get("/brands/{brand_id}/context")
async def get_brand_context(brand_id: str, current_user: dict = Depends(get_current_user)):
    """One-shot context bundle for brand-level ad generation. For loyalty
    brands (kind='loyalty') also reports the cross-chain partner pool size."""
    role = current_user.get("role", "")
    if role != ROLE_ADMIN and not user_can_access_brand(current_user, brand_id):
        raise HTTPException(403, "Access denied for this brand.")
    b = catalog.get_brand(brand_id)
    if not b:
        raise HTTPException(404, "Brand not found.")
    hotels = catalog.hotels_for_brand(brand_id)

    # Brand-level USPs.
    usps: list[dict] = []
    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
        for d in db.collection("embedding_cache") \
                   .where("campaign_type", "==", "brand_usp") \
                   .where("brand_id", "==", brand_id) \
                   .limit(50).stream():
            data = d.to_dict() or {}
            if data.get("hotel_id"):  # skip hotel-level USPs in the brand context
                continue
            usp_text = data.get("description") or data.get("usp") or ""
            if usp_text:
                usps.append({"usp": usp_text, "level": "brand", "added_at": data.get("created_at", "")})
    except Exception as exc:
        logger.debug("Brand USP fetch failed for %s: %s", brand_id, exc)

    # Loyalty-mode cross-chain pool stats.
    loyalty_pool: dict = {}
    if b.get("kind") == "loyalty":
        try:
            from backend.app.core.database import get_firestore
            db = get_firestore()
            partner_brand_ids = []
            partner_hotel_ids = []
            for d in db.collection("brands").stream():
                if d.id == brand_id:
                    continue
                if (d.to_dict() or {}).get("kind", "hotel") == "loyalty":
                    continue
                partner_brand_ids.append(d.id)
            for d in db.collection("hotels").where("status", "==", "active").stream():
                if (d.to_dict() or {}).get("brand_id") in partner_brand_ids:
                    partner_hotel_ids.append(d.id)
            loyalty_pool = {
                "partner_brand_count": len(partner_brand_ids),
                "partner_hotel_count": len(partner_hotel_ids),
            }
        except Exception as exc:
            logger.debug("Loyalty pool fetch failed: %s", exc)

    # Last 5 generations BY THIS USER FOR THIS BRAND.
    recent: list[dict] = []
    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
        try:
            docs = list(
                db.collection("audit_logs")
                .where("user_email", "==", current_user.get("sub", ""))
                .where("brand_id", "==", brand_id)
                .order_by("timestamp", direction="DESCENDING")
                .limit(5).stream()
            )
        except Exception:
            docs = list(
                db.collection("audit_logs")
                .where("user_email", "==", current_user.get("sub", ""))
                .where("brand_id", "==", brand_id)
                .limit(50).stream()
            )
            docs.sort(key=lambda d: (d.to_dict() or {}).get("timestamp", ""), reverse=True)
            docs = docs[:5]
        for d in docs:
            data = d.to_dict() or {}
            if data.get("action") != "generate":
                continue
            recent.append({
                "generation_id": data.get("generation_id", ""),
                "offer_name": data.get("offer_name", ""),
                "platforms": data.get("platforms", []),
                "timestamp": data.get("timestamp", ""),
            })
    except Exception as exc:
        logger.debug("Brand recent-generations fetch failed: %s", exc)

    return {
        "brand": b,
        "hotels": hotels,
        "usps": usps,
        "loyalty_pool": loyalty_pool,
        "recent_generations": recent,
    }


# ──────────────────────────────────────────────────────
# Admin-only write endpoints
# ──────────────────────────────────────────────────────


@router.post("/ingest", response_model=HotelIngestResponse)
async def ingest_hotels_csv(
    file: UploadFile = File(...),
    _admin=Depends(require_admin),
):
    """Bulk-create hotels + auto-create brands from the 7-column CSV.
    Required cols: hotel_name, hotel_code, brand_name.
    Optional cols: rooms_count, fnb_count, website_url, gmb_url.
    """
    if not (file.filename or "").lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(400, "Upload a CSV or Excel file.")
    raw = await file.read()
    try:
        if file.filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw))
        else:
            df = pd.read_excel(io.BytesIO(raw))
    except Exception as exc:
        # Try alt encodings for CSV
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding="cp1252")
        except Exception:
            raise HTTPException(400, f"Could not parse file: {exc}")

    if df.empty:
        raise HTTPException(400, "Uploaded file is empty.")

    summary = catalog.ingest_csv(df)

    # Kick off enrichment in the background — do NOT block the response on it
    try:
        new_hotel_ids: list[str] = []
        # Re-list hotels to find IDs of those just created/updated
        hotels = catalog.list_hotels(page=1, page_size=1000)
        seen = {(b["brand_name"], h["hotel_code"]) for b in summary.get("brand_tree", []) for h in b["hotels"]}
        for h in hotels:
            if (h.get("brand_name", ""), h.get("hotel_code", "")) in seen and not h.get("gmb_place_id"):
                new_hotel_ids.append(h["hotel_id"])
        if new_hotel_ids:
            asyncio.create_task(enrichment.enrich_batch(new_hotel_ids))
    except Exception as exc:
        logger.debug("Could not schedule enrichment: %s", exc)

    return HotelIngestResponse(**summary)


@router.post("")
async def create_hotel_manual(
    hotel_name: str = Form(...),
    hotel_code: str = Form(...),
    brand_name: str = Form(...),
    city: str = Form(""),
    rooms_count: int | None = Form(None),
    fnb_count: int | None = Form(None),
    website_url: str = Form(""),
    gmb_url: str = Form(""),
    _admin=Depends(require_admin),
):
    """Single-hotel manual form."""
    brand_id, _created_brand = catalog.upsert_brand(brand_name)
    row = {
        "hotel_name": hotel_name, "hotel_code": hotel_code,
        "city": city,
        "rooms_count": rooms_count, "fnb_count": fnb_count,
        "website_url": website_url, "gmb_url": gmb_url,
    }
    hotel_id, action = catalog.upsert_hotel(row, brand_id, brand_name)
    catalog.recount_brand_hotels(brand_id)
    asyncio.create_task(enrichment.enrich_hotel(hotel_id))
    return {"hotel_id": hotel_id, "brand_id": brand_id, "action": action}


@router.patch("/{hotel_id}")
async def patch_hotel(
    hotel_id: str,
    city: str | None = Form(None),
    rooms_count: int | None = Form(None),
    fnb_count: int | None = Form(None),
    website_url: str | None = Form(None),
    gmb_url: str | None = Form(None),
    _admin=Depends(require_admin),
):
    from backend.app.core.database import get_firestore
    db = get_firestore()
    ref = db.collection("hotels").document(hotel_id)
    if not ref.get().exists:
        raise HTTPException(404, "Hotel not found.")
    update: dict = {}
    if city is not None:
        update["city"] = city
    if rooms_count is not None:
        update["rooms_count"] = int(rooms_count)
    if fnb_count is not None:
        update["fnb_count"] = int(fnb_count)
    if website_url is not None:
        update["website_url"] = website_url
    if gmb_url is not None:
        update["gmb_url"] = gmb_url
        update["gmb_place_id"] = ""   # force re-enrichment
        asyncio.create_task(enrichment.enrich_hotel(hotel_id))
    if update:
        ref.set(update, merge=True)
    return {"updated": True, **update}


@router.delete("/{hotel_id}")
async def delete_hotel(hotel_id: str, _admin=Depends(require_admin)):
    if not catalog.soft_delete_hotel(hotel_id):
        raise HTTPException(404, "Hotel not found.")
    return {"deleted": True, "hotel_id": hotel_id}
