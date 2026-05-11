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


async def run_campaign(campaign: dict, override_selection: UnifiedCampaignSelection | None = None) -> dict:
    """Orchestrate the full fan-out for a saved campaign. Returns the dict
    payload that the route serialises into CampaignGenerateResponse."""
    structured = StructuredCampaign(**(campaign.get("structured") or {"campaign_name": "Untitled"}))
    selection = override_selection or UnifiedCampaignSelection(**(campaign.get("selection") or {}))
    if not selection.channels:
        selection.channels = ["search_ads"]
    if not selection.campaign_levels:
        selection.campaign_levels = ["single"]
    reference_urls = list(campaign.get("reference_urls") or [])

    entities = _expand_entities(selection)
    results: list[dict] = []
    total_tokens = 0
    total_seconds = 0.0
    overall_t0 = time.time()

    for entity in entities:
        entity_label = _resolve_label(entity)
        for level in selection.campaign_levels:
            # 'chain_plus_single' explodes into both 'chain' and 'single' for this entity
            sub_levels = ["chain", "single"] if level == "chain_plus_single" else [level]
            for sub in sub_levels:
                # 'single' makes no sense for brand-/loyalty-scoped entities — skip silently.
                if sub == "single" and entity.get("scope") in ("brand", "loyalty", "city"):
                    continue
                if sub == "chain" and entity.get("scope") == "hotel" and not entity.get("brand_id"):
                    continue
                for channel in selection.channels:
                    row = CampaignResultRow(
                        label=entity_label, scope=entity.get("scope", "hotel"),
                        channel=channel, level=sub,
                    )
                    try:
                        if channel == "app_push":
                            variants, tokens, model, seconds = await _gen_app_push(structured, entity, reference_urls)
                        else:
                            variants, tokens, model, seconds = await _gen_search_or_meta(
                                structured, entity, channel, sub, reference_urls,
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
                                "label": entity_label, "channel": channel, "level": sub,
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
