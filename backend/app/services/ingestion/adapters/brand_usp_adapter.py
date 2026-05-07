"""Brand & Hotel USP CSV adapter (v2.2).

Schema:
    brand_name, hotel_name, usps

  • Both columns filled  → hotel-level USP record (scope='hotel')
  • brand_name only      → brand-level USP record (scope='brand')
  • Unknown brand        → row rejected with a useful error message

`usps` is a comma-separated list. Each comma-separated USP becomes a separate
record so each one is independently embedded.

The adapter resolves brand_name + hotel_name against the catalog populated by
the Hotels Ingestion module — there is no fuzzy matching. Either the entity
exists or the row is rejected. This is deliberate: the user explicitly asked
for clean brand/hotel hierarchy, and silent fuzzy matching defeats that.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from backend.app.services.ingestion.normalized_record import (
    NormalizedAdRecord, season_for_month,
)

logger = logging.getLogger("vantage.ingestion.brand_usp")

_SIGNATURE_COLUMNS = {"brand_name", "usps"}    # hotel_name optional


def detect_brand_usp(df: pd.DataFrame) -> bool:
    cols = {c.strip().lower().replace(" ", "_") for c in df.columns}
    return _SIGNATURE_COLUMNS.issubset(cols)


def parse_brand_usp(df: pd.DataFrame) -> tuple[list[NormalizedAdRecord], list[str]]:
    """Returns (records, errors). One record per individual USP token."""
    from backend.app.services.hotels import catalog as hotel_catalog

    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    if "brand_name" not in df.columns or "usps" not in df.columns:
        return [], ["Required columns missing: brand_name, usps"]

    if "hotel_name" not in df.columns:
        df["hotel_name"] = ""

    today = date.today()
    records: list[NormalizedAdRecord] = []
    errors: list[str] = []

    # Cache catalog lookups within this run
    brand_id_cache: dict[str, str] = {}
    hotel_id_cache: dict[tuple[str, str], str] = {}   # (brand_name, hotel_name) -> hotel_id

    def _resolve_brand(name: str) -> str | None:
        if name in brand_id_cache:
            return brand_id_cache[name]
        # Exact slug match — same logic as catalog.upsert_brand
        from backend.app.services.hotels.catalog import slugify
        try:
            from backend.app.core.database import get_firestore
            db = get_firestore()
            slug = slugify(name)
            existing = list(db.collection("brands").where("slug", "==", slug).limit(1).stream())
            if existing:
                brand_id_cache[name] = existing[0].id
                return existing[0].id
        except Exception as exc:
            logger.debug("brand resolve failed: %s", exc)
        return None

    def _resolve_hotel(brand_name: str, hotel_name: str) -> str | None:
        key = (brand_name, hotel_name)
        if key in hotel_id_cache:
            return hotel_id_cache[key]
        try:
            from backend.app.core.database import get_firestore
            db = get_firestore()
            # Try by hotel_name + brand_name match
            for d in (
                db.collection("hotels")
                .where("brand_name", "==", brand_name)
                .stream()
            ):
                data = d.to_dict() or {}
                if data.get("hotel_name", "").strip().lower() == hotel_name.strip().lower():
                    hotel_id_cache[key] = d.id
                    return d.id
        except Exception as exc:
            logger.debug("hotel resolve failed: %s", exc)
        return None

    for idx, raw in df.iterrows():
        brand_name = str(raw.get("brand_name") or "").strip()
        hotel_name = str(raw.get("hotel_name") or "").strip()
        usps_blob = str(raw.get("usps") or "").strip()

        if not brand_name or not usps_blob:
            errors.append(f"Row {idx}: missing brand_name or usps")
            continue

        brand_id = _resolve_brand(brand_name)
        if not brand_id:
            errors.append(f"Row {idx}: unknown brand '{brand_name}'. Ingest the brand via Hotels Ingestion first.")
            continue

        hotel_id = None
        scope = "brand"
        if hotel_name:
            hotel_id = _resolve_hotel(brand_name, hotel_name)
            if not hotel_id:
                errors.append(f"Row {idx}: unknown hotel '{hotel_name}' under brand '{brand_name}'.")
                continue
            scope = "hotel"

        # Each comma-separated USP becomes a separate record so it's independently embedded.
        usps = [u.strip() for u in usps_blob.split(",") if u.strip()]
        if not usps:
            errors.append(f"Row {idx}: usps column is empty after parsing.")
            continue

        for usp in usps:
            rec = NormalizedAdRecord(
                headline=usp,
                description=f"USP for {brand_name}" + (f" — {hotel_name}" if hotel_name else " (brand-level)"),
                campaign_type="brand_usp",
                impressions=1000,           # synthetic — USPs always pass the impression floor
                ctr=0.0,
                flight_date=today,
                month=today.month,
                season=season_for_month(today.month),
                business_name=brand_name,
            )
            # Stash the entity references on the record so embedder can route metadata
            rec.long_headlines = [brand_name, hotel_name]   # quick channel for downstream
            # We use raw_ad_type as an out-of-band carrier for scope+id resolution.
            rec.raw_ad_type = f"scope={scope}|brand_id={brand_id}|hotel_id={hotel_id or ''}"
            records.append(rec)

    logger.info(
        "brand_usp_adapter: %d input rows → %d records (errors=%d)",
        len(df), len(records), len(errors),
    )
    return records, errors
