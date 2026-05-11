"""Unified Campaign orchestrator (v2.6).

Given a saved campaign + a selection (properties + channels + levels),
fan out one generation per (entity × channel × level), reusing the
existing ad_generator (Search + Meta) and crm_generator (App Push)
pipelines. Returns a flat list of result rows.
"""
from __future__ import annotations

import logging
import time
from typing import Iterable

from backend.app.models.schemas import (
    AdGenerationRequest, PropertySelection,
    CRMGenerateRequest,
    StructuredCampaign, UnifiedCampaignSelection,
    CampaignResultRow,
)

logger = logging.getLogger("vantage.campaigns.orchestrator")


def _channel_to_platforms(channel: str) -> list[str]:
    """Map a unified-channel id to the ad_generator platform list."""
    if channel == "search_ads":
        return ["google_search"]
    if channel == "meta_ads":
        return ["fb_single_image", "fb_carousel"]
    return []   # app_push uses CRM generator instead


def _expand_entities(selection: UnifiedCampaignSelection) -> list[dict]:
    """Flatten a selection into per-entity dicts the orchestrator can iterate.

    Each entity carries enough state to build a per-entity PropertySelection.
    Loyalty brand is treated as its own scope so the RAG branch picks it up.
    """
    out: list[dict] = []
    if selection.is_loyalty and (selection.brand_ids or [selection.brand_id]):
        bid = next((b for b in (selection.brand_ids or [selection.brand_id]) if b), None)
        if bid:
            out.append({"label": "Club ITC", "scope": "loyalty", "brand_id": bid, "is_loyalty": True})
    for hid in selection.hotel_ids or []:
        out.append({"label": hid, "scope": "hotel", "hotel_id": hid, "is_loyalty": False})
    for bid in selection.brand_ids or []:
        if selection.is_loyalty and bid in (out and [o.get("brand_id") for o in out]):
            continue
        out.append({"label": bid, "scope": "brand", "brand_id": bid, "is_loyalty": False})
    for city in selection.cities or []:
        out.append({"label": city, "scope": "city", "cities": [city], "is_loyalty": False})
    return out


def _resolve_label(entity: dict) -> str:
    """Replace IDs in the entity label with display names from Firestore."""
    try:
        from backend.app.services.hotels import catalog
        if entity.get("scope") == "hotel" and entity.get("hotel_id"):
            h = catalog.get_hotel(entity["hotel_id"]) or {}
            return h.get("hotel_name") or entity["label"]
        if entity.get("scope") == "brand" and entity.get("brand_id"):
            b = catalog.get_brand(entity["brand_id"]) or {}
            return b.get("brand_name") or entity["label"]
    except Exception:
        pass
    return entity.get("label") or "Unknown"


async def _gen_search_or_meta(campaign_structured: StructuredCampaign,
                              entity: dict,
                              channel: str,
                              level: str,
                              reference_urls: list[str]) -> tuple[list[dict], int, str, float]:
    """Run a single Search or Meta ad-copy generation. Returns
    (variants, tokens_used, model_used, time_seconds)."""
    from backend.app.services.ad_generator import generate_ad_copy
    platforms = _channel_to_platforms(channel)
    if not platforms:
        return ([], 0, "", 0.0)

    sel_scope = "hotel" if entity.get("scope") == "hotel" else "brand"
    if entity.get("is_loyalty"):
        sel_scope = "loyalty"

    sel = PropertySelection(
        scope=sel_scope,
        hotel_id=entity.get("hotel_id", "") or "",
        brand_id=entity.get("brand_id", "") or "",
        hotel_ids=[entity["hotel_id"]] if entity.get("hotel_id") else [],
        brand_ids=[entity["brand_id"]] if entity.get("brand_id") else [],
        cities=entity.get("cities") or [],
        is_loyalty=bool(entity.get("is_loyalty")),
    )
    # 'chain' level forces brand-scope retrieval even when the entity is a hotel.
    if level == "chain" and entity.get("brand_id"):
        sel.scope = "brand" if not entity.get("is_loyalty") else "loyalty"

    body = AdGenerationRequest(
        selection=sel,
        hotel_name=entity["label"],
        offer_name=campaign_structured.campaign_name or "Campaign",
        inclusions=(campaign_structured.inclusions or campaign_structured.summary or "")[:600],
        reference_urls=reference_urls or [],
        google_listing_urls=[],
        other_info=(
            f"Target audience: {campaign_structured.target_audience or 'general leisure travellers'}. "
            f"Booking window: {campaign_structured.booking_window_start or '?'} to {campaign_structured.booking_window_end or '?'}. "
            f"Cancellation: {campaign_structured.cancellation_policy or 'standard'}. "
            f"Promo code: {campaign_structured.promo_code or 'none'}."
        )[:600],
        campaign_objective="Conversion",
        platforms=platforms,
    )

    t0 = time.time()
    resp = await generate_ad_copy(body)
    return (
        [v.model_dump() if hasattr(v, "model_dump") else v.dict() for v in (resp.variants or [])],
        int(resp.tokens_used or 0),
        resp.model_used or "",
        round(time.time() - t0, 2),
    )


async def _gen_app_push(campaign_structured: StructuredCampaign,
                        entity: dict,
                        reference_urls: list[str]) -> tuple[list[dict], int, str, float]:
    from backend.app.services.crm_generator import generate_crm_content
    body = CRMGenerateRequest(
        hotel_name=entity["label"],
        channels=["app_push"],
        campaign_type="promotional",
        target_audience=campaign_structured.target_audience or "Existing members and past guests",
        offer_details=campaign_structured.summary or campaign_structured.inclusions or campaign_structured.campaign_name,
        tone="luxurious",
        inclusions=campaign_structured.inclusions or "",
        other_info=(
            f"Promo: {campaign_structured.promo_code or 'none'}. "
            f"Cancellation: {campaign_structured.cancellation_policy or 'standard'}. "
            f"Landing page: {campaign_structured.landing_page_url or 'app deep link'}."
        ),
        reference_urls=reference_urls or [],
        google_listing_urls=[],
        schedule_start=campaign_structured.start_date or "",
        schedule_end=campaign_structured.end_date or "",
    )
    t0 = time.time()
    resp = await generate_crm_content(body)
    flat: list[dict] = []
    for ch in (resp.content or []):
        msgs = ch.messages if hasattr(ch, "messages") else (ch.get("messages") or [])
        for m in msgs:
            flat.append({"platform": "app_push", **m})
    return (
        flat,
        int(resp.tokens_used or 0),
        resp.model_used or "",
        round(getattr(resp, "time_seconds", 0.0) or 0.0, 2),
    )


def _hotels_under_brand(brand_id: str) -> list[dict]:
    """Resolve a brand_id to the list of its active hotels (each as an
    entity dict the orchestrator can iterate)."""
    if not brand_id:
        return []
    try:
        from backend.app.services.hotels import catalog
        out: list[dict] = []
        for h in catalog.hotels_for_brand(brand_id) or []:
            out.append({
                "label": h.get("hotel_name") or h.get("hotel_id"),
                "scope": "hotel",
                "hotel_id": h.get("hotel_id"),
                "brand_id": brand_id,
                "is_loyalty": False,
            })
        return out
    except Exception as exc:
        logger.debug("hotels_for_brand failed for %s: %s", brand_id, exc)
        return []


async def run_campaign(campaign: dict, override_selection: UnifiedCampaignSelection | None = None) -> dict:
    """Orchestrate the full fan-out for a saved campaign. Returns the dict
    payload that the route serialises into CampaignGenerateResponse.

    v2.6.1 — when the selection contains brand_ids AND the user asked for
    'single' (or 'chain_plus_single'), this expands every brand into its
    member hotels so each property gets its own per-property generation
    (with that property's own GMB reviews, USPs, historic ad-copy
    exemplars and past campaigns — every signal the ad_generator already
    pulls when scope='hotel'). 'chain' level still produces ONE
    brand-scope ad per brand with anonymized cross-property exemplars.
    """
    structured = StructuredCampaign(**(campaign.get("structured") or {"campaign_name": "Untitled"}))
    selection = override_selection or UnifiedCampaignSelection(**(campaign.get("selection") or {}))
    if not selection.channels:
        selection.channels = ["search_ads"]
    if not selection.campaign_levels:
        selection.campaign_levels = ["single"]
    reference_urls = list(campaign.get("reference_urls") or [])

    # Effective level set (after expanding 'chain_plus_single').
    eff_levels: list[str] = []
    for lvl in selection.campaign_levels:
        if lvl == "chain_plus_single":
            eff_levels.extend(["chain", "single"])
        else:
            eff_levels.append(lvl)
    want_chain = "chain" in eff_levels
    want_single = "single" in eff_levels

    entities = _expand_entities(selection)

    # Decompose into per-(entity, level) work items.
    # Brand entities → 'chain' yields the brand entity itself; 'single'
    # explodes into hotels under that brand. Loyalty stays brand-shape.
    # City → 'chain' = city scope; 'single' = each hotel in city.
    work: list[tuple[dict, str]] = []
    seen_keys: set[tuple] = set()

    def _push(entity: dict, level: str):
        key = (
            entity.get("scope"),
            entity.get("hotel_id") or "",
            entity.get("brand_id") or "",
            entity.get("label") or "",
            level,
        )
        if key in seen_keys:
            return
        seen_keys.add(key)
        work.append((entity, level))

    for entity in entities:
        scope = entity.get("scope")
        if scope == "hotel":
            if want_single:
                _push(entity, "single")
            if want_chain and entity.get("brand_id"):
                brand_entity = {
                    "label": entity["brand_id"], "scope": "brand",
                    "brand_id": entity["brand_id"], "is_loyalty": False,
                }
                _push(brand_entity, "chain")
        elif scope == "brand":
            if want_chain:
                _push(entity, "chain")
            if want_single:
                for hotel_entity in _hotels_under_brand(entity.get("brand_id", "")):
                    _push(hotel_entity, "single")
        elif scope == "loyalty":
            # Loyalty programmes only make sense at chain level.
            _push(entity, "chain")
        elif scope == "city":
            if want_chain:
                _push(entity, "chain")
            if want_single:
                try:
                    from backend.app.services.hotels import catalog
                    city = (entity.get("cities") or [None])[0] or ""
                    for h in (catalog.hotels_for_city(city) or []):
                        _push({
                            "label": h.get("hotel_name") or h.get("hotel_id"),
                            "scope": "hotel", "hotel_id": h.get("hotel_id"),
                            "brand_id": h.get("brand_id"), "is_loyalty": False,
                        }, "single")
                except Exception:
                    pass

    results: list[dict] = []
    total_tokens = 0
    total_seconds = 0.0
    overall_t0 = time.time()

    for entity, level in work:
        entity_label = _resolve_label(entity)
        for channel in selection.channels:
            row = CampaignResultRow(
                label=entity_label, scope=entity.get("scope", "hotel"),
                channel=channel, level=level,
            )
            try:
                if channel == "app_push":
                    variants, tokens, model, seconds = await _gen_app_push(structured, entity, reference_urls)
                else:
                    variants, tokens, model, seconds = await _gen_search_or_meta(
                        structured, entity, channel, level, reference_urls,
                    )
                row.variants = variants
                row.tokens_used = tokens
                row.model_used = model
                row.time_seconds = seconds
                total_tokens += tokens
                total_seconds += seconds
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "campaign_subgen_failed",
                    extra={"json_fields": {
                        "label": entity_label, "channel": channel, "level": level,
                        "exc": str(exc)[:200],
                    }},
                )
                row.error = str(exc)[:300]
            results.append(row.model_dump())

    return {
        "campaign_id": campaign.get("id", ""),
        "results": results,
        "total_tokens": total_tokens,
        "total_cost_inr": 0.0,    # cost roll-up done in router via existing pricing helper
        "time_seconds": round(time.time() - overall_t0, 2),
    }
