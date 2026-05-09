"""Ad copy generation and refinement endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.core.auth import (
    get_current_user, user_can_access_hotel, user_can_access_brand,
    has_group_scope, _get_user_assignments,
)
from backend.app.core.database import get_firestore
from backend.app.models.schemas import (
    AdGenerationRequest, AdGenerationResponse,
    AdRefinementRequest, AdRefinementResponse,
)
from backend.app.services.ad_generator import generate_ad_copy, refine_ad_copy

# Cost calculation: USD per 1M tokens
MODEL_PRICING = {
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
}
USD_TO_INR = 85.0


def calculate_cost_inr(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in INR for a generation."""
    pricing = MODEL_PRICING.get(model, {"input": 0.15, "output": 0.60})
    cost_usd = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return round(cost_usd * USD_TO_INR, 4)


router = APIRouter()


@router.get("/generate/recent")
async def get_recent_generations(
    limit: int = 10,
    hotel_id: str = "",
    brand_id: str = "",
    current_user: dict = Depends(get_current_user),
):
    """v2.4 — current user's last N generations, optionally filtered to a
    specific hotel or brand. Used by the 'Last 10 generations' panel below
    the Ad Copy form so the user can re-use a brief in one click."""
    db = get_firestore()
    user_email = current_user.get("sub", "")
    if not user_email:
        return {"generations": []}

    # Resolve hotel_id → hotel_name (audit_logs is keyed by hotel_name today).
    hotel_name = ""
    if hotel_id:
        try:
            d = db.collection("hotels").document(hotel_id).get()
            if d.exists:
                hotel_name = (d.to_dict() or {}).get("hotel_name", "")
        except Exception:
            pass

    try:
        coll = db.collection("audit_logs").where("user_email", "==", user_email)
        if hotel_name:
            coll = coll.where("hotel_name", "==", hotel_name)
        if brand_id:
            coll = coll.where("brand_id", "==", brand_id)
        try:
            stream = coll.order_by("timestamp", direction="DESCENDING").limit(max(limit * 3, 30)).stream()
            docs = list(stream)
        except Exception:
            docs = list(coll.limit(200).stream())
            docs.sort(key=lambda d: (d.to_dict() or {}).get("timestamp", ""), reverse=True)
    except Exception:
        docs = []

    out: list[dict] = []
    seen_offers = set()
    for d in docs:
        data = d.to_dict() or {}
        if data.get("action") != "generate":
            continue
        # De-dupe by (hotel_name, offer_name) keeping only the most recent.
        key = (data.get("hotel_name", ""), data.get("offer_name", ""))
        if key in seen_offers:
            continue
        seen_offers.add(key)
        out.append({
            "id": d.id,
            "generation_id": data.get("generation_id", ""),
            "hotel_name": data.get("hotel_name", ""),
            "brand_id": data.get("brand_id", ""),
            "offer_name": data.get("offer_name", ""),
            "platforms": data.get("platforms", []),
            "inclusions": data.get("inclusions", ""),
            "reference_urls": data.get("reference_urls", []),
            "google_listing_urls": data.get("google_listing_urls", []),
            "campaign_objective": data.get("campaign_objective", ""),
            "timestamp": data.get("timestamp", ""),
            "tokens_used": int(data.get("tokens_consumed", 0)),
            "model_used": data.get("model_used", ""),
        })
        if len(out) >= limit:
            break
    return {"generations": out}


@router.get("/generate/url-suggestions")
async def get_url_suggestions(
    query: str = Query("", min_length=0),
    current_user: dict = Depends(get_current_user),
):
    """Return previously used reference URLs matching the query.

    v2.4 — tolerant of the missing `audit_logs (action ==, timestamp DESC)`
    composite index (which 500s today). Falls back to an unordered scan."""
    db = get_firestore()
    try:
        try:
            logs = list(
                db.collection("audit_logs")
                .where("action", "==", "generate")
                .order_by("timestamp", direction="DESCENDING")
                .limit(50)
                .stream()
            )
        except Exception:
            logs = list(
                db.collection("audit_logs")
                .where("action", "==", "generate")
                .limit(150)
                .stream()
            )
            logs.sort(key=lambda d: (d.to_dict() or {}).get("timestamp", ""), reverse=True)
            logs = logs[:50]
    except Exception:
        # Final guard: never 500 an autocomplete call.
        return {"suggestions": []}

    seen = set()
    suggestions = []
    query_lower = query.lower()
    for log in logs:
        data = log.to_dict() or {}
        for url in data.get("reference_urls", []) or []:
            if url not in seen and (not query_lower or query_lower in url.lower()):
                seen.add(url)
                suggestions.append(url)
            if len(suggestions) >= 10:
                break
        if len(suggestions) >= 10:
            break

    return {"suggestions": suggestions}


def _enforce_selection_access(body: AdGenerationRequest, current_user: dict) -> None:
    """v2.4 — gate generation on the user's role/assignments. Raises 403 on miss.

    Rules:
      - admin or 'group' grant → unrestricted
      - selection.scope='hotel'  → user_can_access_hotel must pass on hotel_id
      - selection.scope='brand'  → user_can_access_brand must pass on brand_id;
        when ANY of the matching brand grants is brand_only=True, hotel-level
        generation is rejected (i.e., the user can only do brand-level ads)
      - selection.scope='multi'/'city' → every hotel in hotel_ids must pass user_can_access_hotel
      - selection.scope='loyalty' → access to the loyalty brand_id required (brand check)
    """
    sel = body.selection
    if sel is None:
        return
    if has_group_scope(current_user):
        return
    scope = sel.scope
    if scope == "hotel" and sel.hotel_id:
        if not user_can_access_hotel(current_user, sel.hotel_id):
            raise HTTPException(403, "You don't have access to this hotel.")
        # If only brand grants matched and they're all brand_only=True, the
        # access helper already returned False — covered.
        return
    if scope == "brand" and sel.brand_id:
        if not user_can_access_brand(current_user, sel.brand_id):
            raise HTTPException(403, "You don't have access to this brand.")
        return
    if scope == "loyalty" and sel.brand_id:
        if not user_can_access_brand(current_user, sel.brand_id):
            raise HTTPException(403, "You don't have access to this loyalty programme.")
        return
    if scope in ("multi", "city"):
        for hid in (sel.hotel_ids or []):
            if not user_can_access_hotel(current_user, hid):
                raise HTTPException(403, "You don't have access to one of the selected hotels.")
        return


def _explode_selection_for_fanout(body: AdGenerationRequest) -> list[dict]:
    """v2.4 — when the user picks multiple entities AND chose `generation_mode='per_entity'`,
    return a list of single-entity sub-selections so the caller can fan out one
    generation per brand and per hotel. Returns [] when no fan-out is needed."""
    sel = body.selection
    if sel is None:
        return []
    if (sel.generation_mode or "") != "per_entity":
        return []
    n = (len(sel.hotel_ids or []) + len(sel.brand_ids or []) + len(sel.cities or []))
    if n <= 1:
        return []
    sub: list[dict] = []
    for bid in (sel.brand_ids or []):
        sub.append({"scope": "brand", "brand_id": bid, "is_loyalty": False})
    for hid in (sel.hotel_ids or []):
        sub.append({"scope": "hotel", "hotel_id": hid})
    # Cities are expanded server-side as one ad per city (treated as `multi` in retrieval).
    for city in (sel.cities or []):
        sub.append({"scope": "city", "cities": [city]})
    return sub


async def _generate_with_subselection(body: AdGenerationRequest, sub: dict, label: str):
    """Clone the body, override selection to a single-entity sub-selection, generate."""
    from copy import deepcopy
    from backend.app.models.schemas import PropertySelection
    cloned = deepcopy(body)
    cloned.selection = PropertySelection(
        scope=sub.get("scope", "hotel"),
        hotel_id=sub.get("hotel_id", ""),
        brand_id=sub.get("brand_id", ""),
        hotel_ids=sub.get("hotel_ids", []),
        brand_ids=sub.get("brand_ids", []),
        cities=sub.get("cities", []),
        is_loyalty=sub.get("is_loyalty", False),
    )
    cloned.hotel_name = label or cloned.hotel_name
    return await generate_ad_copy(cloned)


@router.post("/generate", response_model=AdGenerationResponse)
async def generate_ads(
    body: AdGenerationRequest,
    current_user: dict = Depends(get_current_user),
):
    import logging as _logging
    _gen_log = _logging.getLogger("vantage.generate")

    # v2.4 — gate access before doing any work.
    _enforce_selection_access(body, current_user)

    try:
        # v2.4 — fan-out path: when the user picked multiple entities and chose
        # 'per_entity' mode, generate once per entity and merge the variants.
        sub_selections = _explode_selection_for_fanout(body)
        if sub_selections:
            from backend.app.core.database import get_firestore as _gfs
            db_for_labels = _gfs()
            label_for = {}
            try:
                for sub in sub_selections:
                    if sub.get("scope") == "brand" and sub.get("brand_id"):
                        d = db_for_labels.collection("brands").document(sub["brand_id"]).get()
                        if d.exists:
                            label_for[id(sub)] = (d.to_dict() or {}).get("brand_name", "")
                    elif sub.get("scope") == "hotel" and sub.get("hotel_id"):
                        d = db_for_labels.collection("hotels").document(sub["hotel_id"]).get()
                        if d.exists:
                            label_for[id(sub)] = (d.to_dict() or {}).get("hotel_name", "")
                    elif sub.get("scope") == "city" and sub.get("cities"):
                        label_for[id(sub)] = sub["cities"][0]
            except Exception:
                pass

            sub_results = []
            for sub in sub_selections:
                lbl = label_for.get(id(sub), body.hotel_name)
                try:
                    r = await _generate_with_subselection(body, sub, lbl)
                    # Tag every variant with which entity it belongs to.
                    for v in r.variants:
                        v.platform = f"{v.platform} | {lbl}"
                    sub_results.append(r)
                except Exception as exc:
                    _gen_log.error(
                        "generate_subselection_failed",
                        extra={"json_fields": {
                            "label": lbl,
                            "sub_scope": sub.get("scope"),
                            "exc": str(exc)[:300],
                        }},
                        exc_info=True,
                    )

            if not sub_results:
                raise RuntimeError("All per-entity generations failed.")

            # Merge — sum tokens, take latest model/version, concatenate variants.
            from backend.app.models.schemas import AdGenerationResponse as _Resp
            from backend.app.core.version import APP_VERSION as _VER
            merged_variants = []
            tin = tout = ttot = 0
            tsec = 0.0
            for r in sub_results:
                merged_variants.extend(r.variants)
                tin += r.input_tokens
                tout += r.output_tokens
                ttot += r.tokens_used
                tsec += r.time_seconds
            result = _Resp(
                hotel_name=body.hotel_name,
                variants=merged_variants,
                tokens_used=ttot,
                input_tokens=tin,
                output_tokens=tout,
                model_used=sub_results[-1].model_used,
                time_seconds=round(tsec, 2),
                generated_at=sub_results[-1].generated_at,
                generation_id=sub_results[-1].generation_id,
                app_version=_VER,
            )
        else:
            result = await generate_ad_copy(body)
    except Exception as e:
        error_msg = str(e)
        # v2.2: structured error log so it shows up grouped in Cloud Run by user/hotel.
        _gen_log.error(
            "generate_failed",
            extra={"json_fields": {
                "user_email": current_user.get("sub"),
                "hotel_name": body.hotel_name,
                "platforms": body.platforms,
                "exc_type": type(e).__name__,
                "exc": error_msg[:500],
            }},
            exc_info=True,
        )
        # Best-effort BQ row for failed generation
        try:
            from backend.app.services.analytics import audit_logger
            from backend.app.core.version import APP_VERSION
            await audit_logger.log_generation(
                brand_id=str(body.hotel_name),
                user_id=current_user.get("uid", ""),
                platform=",".join(body.platforms or []),
                model="",
                tokens_in=0, tokens_out=0, latency_ms=0,
                generation_id="",
                app_version=APP_VERSION,
                scope=getattr(getattr(body, "selection", None), "scope", "hotel") or "hotel",
                request_type="ad_copy",
                status="error",
                error_message=error_msg,
            )
        except Exception:
            pass
        if "429" in error_msg or "quota" in error_msg.lower():
            raise HTTPException(
                status_code=429,
                detail="Gemini API quota exceeded. Please try again later or upgrade your plan.",
            )
        raise HTTPException(status_code=500, detail=f"Generation failed: {error_msg[:200]}")

    # Calculate cost in INR
    cost_inr = calculate_cost_inr(result.model_used, result.input_tokens, result.output_tokens)

    # Audit log with full details (Firestore — kept for backwards compat with legacy admin views)
    # Wrapped so any Firestore hiccup never fails a successful generation.
    db = get_firestore()
    sel = body.selection
    try:
        db.collection("audit_logs").add(
            {
            "user_email": current_user["sub"],
            "user_id": current_user.get("uid", ""),
            "action": "generate",
            "hotel_name": body.hotel_name,
            "hotel_id": (sel.hotel_id if sel else "") or "",
            "brand_id": (sel.brand_id if sel else "") or "",
            "scope": (sel.scope if sel else "hotel"),
            "offer_name": body.offer_name,
            "platforms": body.platforms,
            "inclusions": body.inclusions,
            "reference_urls": body.reference_urls,
            "google_listing_urls": body.google_listing_urls,
            "campaign_objective": body.campaign_objective or "Auto-detect",
            "carousel_mode": body.carousel_mode if "fb_carousel" in body.platforms else None,
            "carousel_cards": body.carousel_cards if "fb_carousel" in body.platforms and body.carousel_mode == "manual" else None,
            "tokens_consumed": result.tokens_used,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "model_used": result.model_used,
            "cost_inr": cost_inr,
            "time_seconds": result.time_seconds,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": current_user.get("session_id"),
            "generation_id": result.generation_id,
            "app_version": result.app_version,
            }
        )
    except Exception as exc:
        _gen_log.warning(
            "audit_log_write_failed",
            extra={"json_fields": {"exc": str(exc)[:300]}},
        )

    return result


@router.post("/generate/refine", response_model=AdRefinementResponse)
async def refine_ads(
    body: AdRefinementRequest,
    current_user: dict = Depends(get_current_user),
):
    """Refine previously generated ad copy based on user feedback."""
    try:
        result = await refine_ad_copy(body)
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower():
            raise HTTPException(
                status_code=429,
                detail="Gemini API quota exceeded. Please try again later.",
            )
        raise HTTPException(status_code=500, detail=f"Refinement failed: {error_msg[:200]}")

    # Accumulate tokens and time
    total_tokens = body.accumulated_tokens + result["tokens_used"]
    total_time = round(body.accumulated_time + result["time_seconds"], 2)

    cost_inr = calculate_cost_inr(result["model_used"], result["input_tokens"], result["output_tokens"])

    # Audit log for refinement
    db = get_firestore()
    db.collection("audit_logs").add(
        {
            "user_email": current_user["sub"],
            "action": "refine",
            "hotel_name": body.hotel_name,
            "offer_name": body.offer_name,
            "platforms": body.platforms,
            "feedback": body.feedback,
            "tokens_consumed": result["tokens_used"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "accumulated_tokens": total_tokens,
            "model_used": result["model_used"],
            "cost_inr": cost_inr,
            "time_seconds": result["time_seconds"],
            "accumulated_time": total_time,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": current_user.get("session_id"),
        }
    )

    return AdRefinementResponse(
        hotel_name=body.hotel_name,
        variants=result["variants"],
        tokens_used=total_tokens,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        model_used=result["model_used"],
        time_seconds=total_time,
        generated_at=datetime.now(timezone.utc).isoformat(),
        refinement_count=1 + (1 if body.accumulated_tokens > 0 else 0),
    )
