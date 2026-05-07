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
    _get_user_assignments,
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
    Returns (None, None) for admin (= unlimited)."""
    if current_user.get("role") == ROLE_ADMIN:
        return None, None
    assignments = _get_user_assignments(current_user.get("uid", ""))
    hotel_ids = [a.get("hotel_id") for a in assignments if a.get("scope") == "hotel" and a.get("hotel_id")]
    brand_ids = [a.get("brand_id") for a in assignments if a.get("scope") == "brand" and a.get("brand_id")]
    return hotel_ids or [], brand_ids or []


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
async def scope_search(q: str = "", limit: int = 20, current_user: dict = Depends(get_current_user)):
    """Free-flow brand/hotel search for the PropertySwitcher.
    Non-admin callers only see entities they have access to."""
    rows = catalog.search_scope(q, limit=limit)
    role = current_user.get("role", "")
    if role == ROLE_ADMIN:
        return {"results": rows}

    assignments = _get_user_assignments(current_user.get("uid", ""))
    allowed_brand = {a.get("brand_id") for a in assignments if a.get("scope") == "brand"}
    allowed_hotel = {a.get("hotel_id") for a in assignments if a.get("scope") == "hotel"}

    filtered = []
    for r in rows:
        if r["type"] == "brand" and r["id"] in allowed_brand:
            filtered.append(r)
        elif r["type"] == "hotel" and (r["id"] in allowed_hotel or r.get("brand_id") in allowed_brand):
            filtered.append(r)
    return {"results": filtered}


@router.get("/{hotel_id}")
async def get_hotel(hotel_id: str, current_user: dict = Depends(get_current_user)):
    from backend.app.core.auth import user_can_access_hotel
    if not user_can_access_hotel(current_user, hotel_id):
        raise HTTPException(403, "Access denied for this hotel.")
    h = catalog.get_hotel(hotel_id)
    if not h:
        raise HTTPException(404, "Hotel not found.")
    return h


@router.get("/brands/{brand_id}")
async def get_brand(brand_id: str, current_user: dict = Depends(get_current_user)):
    from backend.app.core.auth import user_can_access_brand
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
