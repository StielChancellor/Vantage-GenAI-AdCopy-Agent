"""Hotel & brand catalog operations.

Two Firestore collections:
  brands/{brand_id}   {brand_name, slug, voice, hotel_count, created_at}
  hotels/{hotel_id}   {hotel_name, hotel_code, brand_id, brand_name (denorm),
                       rooms_count, fnb_count, website_url, gmb_url,
                       gmb_place_id, status, ingested_at, last_enriched_at}

CSV ingestion is the primary path; manual single-hotel form goes through the
same upsert helpers so behavior is consistent.
"""
from __future__ import annotations

import io
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

logger = logging.getLogger("vantage.hotels.catalog")

REQUIRED_COLUMNS = ["hotel_name", "hotel_code", "brand_name"]
OPTIONAL_COLUMNS = ["city", "rooms_count", "fnb_count", "website_url", "gmb_url"]
ALL_KNOWN_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# v2.4 — Club ITC bootstrap constants. Treat Club ITC as the apex loyalty brand.
CLUB_ITC_BRAND_ID = "club-itc"
CLUB_ITC_BRAND_NAME = "Club ITC"
CLUB_ITC_DEFAULT_VOICE = (
    "Club ITC is the loyalty programme spanning every ITC Hotel and brand. "
    "Voice: insider, member-first, gracious. Lean on belonging, accumulated benefits, "
    "tier progression, and the breadth of the chain — never a single property."
)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "unknown"


def _get_db():
    from backend.app.core.database import get_firestore
    return get_firestore()


def upsert_brand(brand_name: str, *, kind: str = "hotel", voice: str = "") -> tuple[str, bool]:
    """Return (brand_id, created_now). Idempotent — looks up by slug.

    v2.4 — `kind` defaults to 'hotel'. Pass 'loyalty' for programmes like Club ITC.
    Existing brands are not overwritten; use the dedicated `set_brand_kind` helper
    if you need to upgrade a brand in place."""
    if not brand_name:
        raise ValueError("brand_name is required")
    db = _get_db()
    slug = slugify(brand_name)
    coll = db.collection("brands")
    existing = list(coll.where("slug", "==", slug).limit(1).stream())
    if existing:
        return existing[0].id, False
    brand_id = slug if len(slug) <= 60 else uuid.uuid4().hex[:16]
    coll.document(brand_id).set({
        "brand_name": brand_name,
        "slug": slug,
        "hotel_count": 0,
        "voice": voice,
        "kind": kind,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return brand_id, True


def set_brand_kind(brand_id: str, kind: str) -> bool:
    """Promote/demote a brand's kind ('hotel' | 'loyalty'). Returns True if updated."""
    if not brand_id or kind not in ("hotel", "loyalty"):
        return False
    db = _get_db()
    ref = db.collection("brands").document(brand_id)
    if not ref.get().exists:
        return False
    ref.set({"kind": kind}, merge=True)
    return True


def ensure_club_itc() -> str:
    """Idempotent bootstrap. Creates Club ITC as a loyalty brand with default
    voice if it doesn't exist. Returns its brand_id. Safe to call on every boot."""
    db = _get_db()
    ref = db.collection("brands").document(CLUB_ITC_BRAND_ID)
    snap = ref.get()
    if snap.exists:
        # Make sure kind=loyalty even if the doc was created earlier without it.
        cur = snap.to_dict() or {}
        if cur.get("kind") != "loyalty":
            ref.set({"kind": "loyalty"}, merge=True)
        return CLUB_ITC_BRAND_ID
    ref.set({
        "brand_name": CLUB_ITC_BRAND_NAME,
        "slug": CLUB_ITC_BRAND_ID,
        "hotel_count": 0,
        "voice": CLUB_ITC_DEFAULT_VOICE,
        "kind": "loyalty",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    logger.info("Bootstrapped Club ITC loyalty brand")
    return CLUB_ITC_BRAND_ID


def upsert_hotel(row: dict, brand_id: str, brand_name: str) -> tuple[str, str]:
    """Insert or update a hotel by hotel_code. Returns (hotel_id, action)
    where action is one of 'created' | 'updated'."""
    db = _get_db()
    hotel_code = (row.get("hotel_code") or "").strip()
    if not hotel_code:
        raise ValueError("hotel_code is required and cannot be blank")

    coll = db.collection("hotels")
    existing = list(coll.where("hotel_code", "==", hotel_code).limit(1).stream())

    payload = {
        "hotel_name": (row.get("hotel_name") or "").strip(),
        "hotel_code": hotel_code,
        "brand_id": brand_id,
        "brand_name": brand_name,
        "city": (row.get("city") or "").strip(),
        "rooms_count": _safe_int(row.get("rooms_count")),
        "fnb_count": _safe_int(row.get("fnb_count")),
        "website_url": (row.get("website_url") or "").strip(),
        "gmb_url": (row.get("gmb_url") or "").strip(),
        "status": "active",
        "last_modified_at": datetime.now(timezone.utc).isoformat(),
    }

    if existing:
        hotel_id = existing[0].id
        # Preserve enrichment fields if already populated
        prev = existing[0].to_dict() or {}
        if prev.get("gmb_place_id"):
            payload["gmb_place_id"] = prev["gmb_place_id"]
        if prev.get("last_enriched_at"):
            payload["last_enriched_at"] = prev["last_enriched_at"]
        coll.document(hotel_id).set(payload, merge=True)
        return hotel_id, "updated"

    hotel_id = uuid.uuid4().hex[:16]
    payload["ingested_at"] = datetime.now(timezone.utc).isoformat()
    coll.document(hotel_id).set(payload)
    return hotel_id, "created"


def recount_brand_hotels(brand_id: str) -> None:
    """Recompute and store hotel_count for a brand. Cheap because brands are few."""
    db = _get_db()
    n = sum(
        1 for _ in db.collection("hotels")
        .where("brand_id", "==", brand_id)
        .where("status", "==", "active")
        .stream()
    )
    db.collection("brands").document(brand_id).set({"hotel_count": n}, merge=True)


def ingest_csv(df: pd.DataFrame) -> dict:
    """Upsert every row of an ingestion CSV. Returns a summary dict."""
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return {
            "created_brands": 0, "created_hotels": 0, "updated_hotels": 0,
            "skipped": 0, "errors": [f"Missing required columns: {missing}"],
            "brand_tree": [],
        }

    created_brands = set()
    created_hotels = 0
    updated_hotels = 0
    skipped = 0
    errors: list[str] = []
    brand_buckets: dict[str, list[dict]] = {}

    # Cache brand_id by name within this run to avoid repeated lookups
    brand_id_by_name: dict[str, str] = {}

    for idx, raw in df.iterrows():
        row = {k: (str(v).strip() if not pd.isna(v) else "") for k, v in raw.items()}
        hotel_name = row.get("hotel_name", "")
        hotel_code = row.get("hotel_code", "")
        brand_name = row.get("brand_name", "")

        if not (hotel_name and hotel_code and brand_name):
            skipped += 1
            errors.append(f"Row {idx}: missing one of hotel_name/hotel_code/brand_name")
            continue

        try:
            if brand_name not in brand_id_by_name:
                brand_id, created_brand = upsert_brand(brand_name)
                brand_id_by_name[brand_name] = brand_id
                if created_brand:
                    created_brands.add(brand_id)
            else:
                brand_id = brand_id_by_name[brand_name]

            _hotel_id, action = upsert_hotel(row, brand_id, brand_name)
            if action == "created":
                created_hotels += 1
            else:
                updated_hotels += 1

            brand_buckets.setdefault(brand_name, []).append({
                "hotel_name": hotel_name, "hotel_code": hotel_code,
            })
        except Exception as exc:
            skipped += 1
            errors.append(f"Row {idx}: {exc}")

    # Refresh hotel_count for affected brands
    for bid in set(brand_id_by_name.values()):
        try:
            recount_brand_hotels(bid)
        except Exception as exc:
            logger.debug("recount failed for %s: %s", bid, exc)

    brand_tree = [{"brand_name": b, "hotels": h} for b, h in brand_buckets.items()]

    return {
        "created_brands": len(created_brands),
        "created_hotels": created_hotels,
        "updated_hotels": updated_hotels,
        "skipped": skipped,
        "errors": errors[:20],
        "brand_tree": brand_tree,
    }


def list_hotels(
    *,
    brand_id: str | None = None,
    q: str | None = None,
    status: str = "active",
    page: int = 1,
    page_size: int = 200,
    allowed_hotel_ids: list[str] | None = None,
    allowed_brand_ids: list[str] | None = None,
) -> list[dict]:
    """Return hotel docs filtered for the caller. allowed_* lists scope the result
    for non-admin roles; admin passes both as None to see everything."""
    db = _get_db()
    coll = db.collection("hotels").where("status", "==", status)
    if brand_id:
        coll = coll.where("brand_id", "==", brand_id)
    docs = list(coll.stream())
    rows = []
    for d in docs:
        data = {"hotel_id": d.id, **(d.to_dict() or {})}
        if allowed_hotel_ids is not None and d.id not in allowed_hotel_ids:
            if not (allowed_brand_ids and data.get("brand_id") in allowed_brand_ids):
                continue
        if q:
            blob = (data.get("hotel_name", "") + " " + data.get("brand_name", "") + " " + data.get("hotel_code", "")).lower()
            if q.lower() not in blob:
                continue
        rows.append(data)

    rows.sort(key=lambda r: (r.get("brand_name", ""), r.get("hotel_name", "")))
    start = (page - 1) * page_size
    return rows[start:start + page_size]


def list_brands(*, allowed_brand_ids: list[str] | None = None) -> list[dict]:
    db = _get_db()
    docs = list(db.collection("brands").stream())
    rows = [{"brand_id": d.id, **(d.to_dict() or {})} for d in docs]
    if allowed_brand_ids is not None:
        rows = [r for r in rows if r["brand_id"] in allowed_brand_ids]
    rows.sort(key=lambda r: r.get("brand_name", ""))
    return rows


def search_scope(q: str, limit: int = 20, *, include_empty: bool = False) -> list[dict]:
    """Free-flowing typeahead — returns flat list of brand + hotel + city matches.

    Each row is one of:
      {type:'brand', id, label, kind, hotel_count}
      {type:'hotel', id, label, brand_id, brand_name, hotel_code, city}
      {type:'city',  id (=city slug), label (=city), hotel_count}

    Loyalty brands (kind='loyalty') always sort to the very top. When
    `include_empty=True`, an empty query still returns the loyalty brands +
    every brand alphabetically — used for the "show me everything I can pick"
    initial dropdown render."""
    q_lower = (q or "").lower()
    db = _get_db()
    out: list[dict] = []
    loyalty_rows: list[dict] = []
    brand_rows: list[dict] = []
    hotel_rows: list[dict] = []
    city_counts: dict[str, int] = {}

    # Brands — small collection, scan it
    for d in db.collection("brands").stream():
        data = d.to_dict() or {}
        kind = data.get("kind", "hotel")
        haystack = (data.get("brand_name", "") + " " + data.get("slug", "")).lower()
        if include_empty and not q_lower:
            matched = True
        else:
            matched = bool(q_lower) and (q_lower in haystack)
        if not matched:
            continue
        row = {
            "type": "brand",
            "id": d.id,
            "label": data.get("brand_name", ""),
            "kind": kind,
            "hotel_count": int(data.get("hotel_count", 0)),
        }
        if kind == "loyalty":
            loyalty_rows.append(row)
        else:
            brand_rows.append(row)

    # Hotels — also scan; small enough at this stage. Also accumulate city counts
    # so we can surface matching city rows in the same response.
    for d in db.collection("hotels").where("status", "==", "active").stream():
        data = d.to_dict() or {}
        city = (data.get("city") or "").strip()
        if city:
            city_counts[city] = city_counts.get(city, 0) + 1
        if not q_lower:
            continue
        haystack = (
            data.get("hotel_name", "") + " " + data.get("hotel_code", "") + " " + city
        ).lower()
        if q_lower in haystack:
            hotel_rows.append({
                "type": "hotel",
                "id": d.id,
                "label": data.get("hotel_name", ""),
                "brand_id": data.get("brand_id", ""),
                "brand_name": data.get("brand_name", ""),
                "hotel_code": data.get("hotel_code", ""),
                "city": city,
            })

    city_rows = []
    if q_lower:
        for city, count in sorted(city_counts.items()):
            if q_lower in city.lower():
                city_rows.append({
                    "type": "city",
                    "id": slugify(city),
                    "label": city,
                    "hotel_count": count,
                })

    # Final ordering: loyalty brands first, then matching cities, then hotel brands, then hotels.
    loyalty_rows.sort(key=lambda r: r["label"])
    brand_rows.sort(key=lambda r: r["label"])
    hotel_rows.sort(key=lambda r: r["label"])
    out = loyalty_rows + city_rows + brand_rows + hotel_rows
    return out[:limit]


def list_cities() -> list[dict]:
    """Return distinct hotel cities with hotel counts. Cheap O(N) scan since the
    hotel collection is small at this stage."""
    db = _get_db()
    counts: dict[str, int] = {}
    for d in db.collection("hotels").where("status", "==", "active").stream():
        city = ((d.to_dict() or {}).get("city") or "").strip()
        if not city:
            continue
        counts[city] = counts.get(city, 0) + 1
    return [{"city": c, "hotel_count": n} for c, n in sorted(counts.items())]


def hotels_for_city(city: str) -> list[dict]:
    if not city:
        return []
    db = _get_db()
    docs = list(
        db.collection("hotels")
        .where("status", "==", "active")
        .where("city", "==", city)
        .stream()
    )
    return [{"hotel_id": d.id, **(d.to_dict() or {})} for d in docs]


def soft_delete_hotel(hotel_id: str) -> bool:
    db = _get_db()
    ref = db.collection("hotels").document(hotel_id)
    if not ref.get().exists:
        return False
    ref.set({"status": "archived", "archived_at": datetime.now(timezone.utc).isoformat()}, merge=True)
    return True


def get_hotel(hotel_id: str) -> dict | None:
    if not hotel_id:
        return None
    db = _get_db()
    d = db.collection("hotels").document(hotel_id).get()
    if not d.exists:
        return None
    return {"hotel_id": d.id, **(d.to_dict() or {})}


def get_brand(brand_id: str) -> dict | None:
    if not brand_id:
        return None
    db = _get_db()
    d = db.collection("brands").document(brand_id).get()
    if not d.exists:
        return None
    return {"brand_id": d.id, **(d.to_dict() or {})}


def hotels_for_brand(brand_id: str) -> list[dict]:
    if not brand_id:
        return []
    db = _get_db()
    docs = list(
        db.collection("hotels")
        .where("brand_id", "==", brand_id)
        .where("status", "==", "active")
        .stream()
    )
    return [{"hotel_id": d.id, **(d.to_dict() or {})} for d in docs]


def _safe_int(val) -> int | None:
    try:
        if val in (None, "", "nan"):
            return None
        return int(float(val))
    except (TypeError, ValueError):
        return None
