"""Campaign Ideation endpoints.

v2.8 — Form -> Directions -> Final 10 -> Unified Campaign handoff.
v2.7 — chat coach (still served for in-progress ideations on phase ∈ {critique, shortlist}).

Lifecycle on `campaign_ideations/{id}`:
  v2.8: inputs → directions → refining → final → chosen | archived
  v2.7: critique → shortlist → chosen | archived
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.app.core.auth import (
    get_current_user, has_group_scope,
    user_can_access_hotel, user_can_access_brand,
)
from backend.app.core.database import get_firestore
from backend.app.core.version import APP_VERSION
from backend.app.models.schemas import (
    # v2.7 (legacy)
    IdeationStartRequest, IdeationStartResponse,
    IdeationAnswerRequest, IdeationAnswerResponse,
    IdeationShortlistResponse, ShortlistItem,
    IdeationChooseRequest, IdeationChooseResponse,
    IdeationState, CritiqueTurn, PropertySelection,
    # v2.8
    IdeationInputs, IdeationStartV2Request, IdeationStartV2Response,
    ResolveHotelsRequest, ResolveHotelsResponse, ResolvedHotelRef,
    IdeationDirectionsResponse, IdeationDirection, IdeationDirectionConcept,
    IdeationVisualCue, IdeationRefineRequest,
    IdeationFinalConcept, IdeationFinalizeRequest, IdeationFinalResponse,
    IdeationStateV2, IdeationIterationRecord,
    # v2.9
    ResolveDiscountRequest, ResolveDiscountResponse,
)
from backend.app.services.ideation.critique_engine import next_critique_turn
from backend.app.services.ideation.shortlist_generator import generate_shortlist
from backend.app.services.ideation.hotels_resolver import resolve_hotels as _resolve_hotels
from backend.app.services.ideation.discount_resolver import resolve_discount as _resolve_discount
from backend.app.services.ideation.direction_generator import generate_directions as _generate_directions
from backend.app.services.ideation.finalizer import generate_final_concepts as _generate_final_concepts
from backend.app.services.ideation.campaign_id import (
    generate_campaign_id, ensure_campaign_id,
)
from backend.app.services.ideation import exporters as _exporters
from backend.app.services.rag_engine import retrieve_visual_inspiration

from fastapi.responses import Response, JSONResponse

logger = logging.getLogger("vantage.ideation")
router = APIRouter(prefix="/ideation", tags=["Ideation"])

_COLL = "campaign_ideations"
_CAMPAIGNS_COLL = "unified_campaigns"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enforce_selection_access(selection: PropertySelection, current_user: dict) -> None:
    """Mirror routers/generate._enforce_selection_access for ideation."""
    if selection is None:
        return
    if has_group_scope(current_user):
        return
    scope = selection.scope
    if scope == "hotel" and selection.hotel_id:
        if not user_can_access_hotel(current_user, selection.hotel_id):
            raise HTTPException(403, "You don't have access to this hotel.")
        return
    if scope == "brand" and selection.brand_id:
        if not user_can_access_brand(current_user, selection.brand_id):
            raise HTTPException(403, "You don't have access to this brand.")
        return
    if scope == "loyalty" and selection.brand_id:
        if not user_can_access_brand(current_user, selection.brand_id):
            raise HTTPException(403, "You don't have access to this loyalty programme.")
        return
    if scope in ("multi", "city"):
        for hid in (selection.hotel_ids or []):
            if not user_can_access_hotel(current_user, hid):
                raise HTTPException(403, "You don't have access to one of the selected hotels.")
        return


def _scope_summary(selection: PropertySelection) -> str:
    """One-line human label for prompts / logs."""
    if selection is None:
        return ""
    s = selection
    if s.scope == "loyalty" or s.is_loyalty:
        return "Loyalty programme (Club ITC) — chain-wide tone, partner brands anonymized."
    bits: list[str] = [f"scope={s.scope}"]
    if s.brand_id:
        bits.append(f"brand_id={s.brand_id}")
    if s.brand_ids:
        bits.append(f"brand_ids={','.join(s.brand_ids[:3])}")
    if s.hotel_ids:
        bits.append(f"hotels={len(s.hotel_ids)}")
    if s.cities:
        bits.append(f"cities={','.join(s.cities[:3])}")
    return " · ".join(bits)


def _audit_safe(action: str, current_user: dict, payload: dict) -> None:
    """Append a lightweight audit_logs row — wrapped so a Firestore hiccup
    never fails the user-visible response (per AGENT_HANDOFF rule)."""
    try:
        db = get_firestore()
        db.collection("audit_logs").add({
            "user_email": current_user.get("sub", ""),
            "user_id": current_user.get("uid", ""),
            "action": action,
            "timestamp": _now(),
            "app_version": APP_VERSION,
            **payload,
        })
    except Exception as exc:
        logger.debug("audit_logs write failed: %s", exc)


def _doc_to_state(doc) -> IdeationState:
    data = doc.to_dict() or {}
    sel_raw = data.get("selection") or None
    sel = PropertySelection(**sel_raw) if sel_raw else None
    turns_raw = data.get("critique_turns") or []
    turns = [CritiqueTurn(**t) if isinstance(t, dict) else t for t in turns_raw]
    sl_raw = data.get("shortlist") or []
    shortlist = [ShortlistItem(**i) for i in sl_raw if isinstance(i, dict)]
    return IdeationState(
        id=doc.id,
        user_id=data.get("user_id", ""),
        user_email=data.get("user_email", ""),
        selection=sel,
        theme_text=data.get("theme_text", ""),
        date_start=data.get("date_start", ""),
        date_end=data.get("date_end", ""),
        phase=data.get("phase", "critique"),
        critique_turns=turns,
        captured=data.get("captured", {}) or {},
        shortlist=shortlist,
        chosen_index=data.get("chosen_index"),
        linked_campaign_id=data.get("linked_campaign_id"),
        app_version=data.get("app_version", APP_VERSION),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def _require_owner_or_admin(doc_data: dict, current_user: dict) -> None:
    if current_user.get("role") == "admin":
        return
    if (doc_data or {}).get("user_id") == current_user.get("uid"):
        return
    raise HTTPException(403, "You don't have access to this ideation.")


# ──────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────
# v2.8 helpers — derive selection from the structured Inputs
# ──────────────────────────────────────────────────────────────────


def _selection_from_inputs(inputs: IdeationInputs) -> PropertySelection:
    """Synthesise a PropertySelection (the platform's shared shape) from the
    Step-1 inputs' hotels_resolution. This is what gets persisted, what the
    access-gate enforces against, and what fan-out reads at Unified Campaign
    handoff."""
    hr = inputs.hotels_resolution
    hotel_ids = list(hr.resolved_hotel_ids or [])
    brand_ids = list(hr.resolved_brand_ids or [])
    is_loyalty = bool(hr.is_loyalty)

    if is_loyalty and brand_ids:
        return PropertySelection(
            scope="loyalty",
            brand_id=brand_ids[0],
            brand_ids=brand_ids,
            hotel_ids=hotel_ids,
            is_loyalty=True,
        )
    if len(hotel_ids) == 1 and not brand_ids:
        return PropertySelection(scope="hotel", hotel_id=hotel_ids[0], hotel_ids=hotel_ids)
    if not hotel_ids and len(brand_ids) == 1:
        return PropertySelection(scope="brand", brand_id=brand_ids[0], brand_ids=brand_ids)
    return PropertySelection(
        scope="multi",
        hotel_ids=hotel_ids,
        brand_ids=brand_ids,
        is_loyalty=is_loyalty,
    )


def _hotel_context_from_inputs(inputs: dict) -> list[dict]:
    """Pull a slim brand/city context list for naming inspiration, derived from
    the resolved hotel ids on the inputs."""
    hr = (inputs or {}).get("hotels_resolution") or {}
    hotel_ids = hr.get("resolved_hotel_ids") or []
    if not hotel_ids:
        return []
    try:
        from backend.app.services.hotels import catalog as hc
        all_h = {h["hotel_id"]: h for h in hc.list_hotels()}
    except Exception:
        return []
    out: list[dict] = []
    for hid in hotel_ids[:30]:
        h = all_h.get(hid) or {}
        out.append({
            "hotel_id": hid,
            "name": h.get("hotel_name", ""),
            "brand": h.get("brand_name", ""),
            "city": h.get("city", ""),
        })
    return out


def _slim_iteration_record(it: dict) -> dict:
    """Keep only what the generators need: titles + names. Strip Firestore
    timestamp objects so JSON serialisation is safe."""
    out = {
        "idx": it.get("idx"),
        "kind": it.get("kind"),
        "directions": it.get("directions") or [],
        "final": it.get("final") or [],
    }
    return out


# ──────────────────────────────────────────────────────────────────
# v2.8 routes — Form → Directions → Iterate → Final 10 → Choose
# ──────────────────────────────────────────────────────────────────


@router.post("/start", response_model=IdeationStartV2Response)
async def start_ideation(
    body: IdeationStartV2Request,
    current_user: dict = Depends(get_current_user),
):
    """v2.8 — create a new ideation from the structured Step-1 inputs.

    Does NOT auto-run directions; the frontend explicitly calls
    POST /{id}/directions when the user clicks the CTA on Step 2.
    """
    selection = _selection_from_inputs(body.inputs)
    _enforce_selection_access(selection, current_user)

    cid = uuid.uuid4().hex[:16]
    campaign_id = generate_campaign_id()      # v2.9 — 5-char human-visible id
    inputs_dict = body.inputs.model_dump() if hasattr(body.inputs, "model_dump") else body.inputs.dict()
    sel_dict = selection.model_dump() if hasattr(selection, "model_dump") else selection.dict()

    db = get_firestore()
    db.collection(_COLL).document(cid).set({
        "user_id": current_user.get("uid", ""),
        "user_email": current_user.get("sub", ""),
        "schema_version": 2,
        "campaign_id": campaign_id,
        "phase": "inputs",
        "inputs": inputs_dict,
        "selection": sel_dict,
        "iterations": [],
        "chosen_final_index": None,
        "linked_campaign_id": None,
        "app_version": APP_VERSION,
        "created_at": _now(),
        "updated_at": _now(),
    })

    _audit_safe("ideation_start_v2", current_user, {
        "ideation_id": cid,
        "campaign_id": campaign_id,
        "offer_name": (body.inputs.offer_name or "")[:120],
        "audience_axis": body.inputs.audience_axis,
        "tone_axis": body.inputs.tone_axis,
        "is_loyalty": bool(body.inputs.hotels_resolution.is_loyalty),
        "hotel_count": len(body.inputs.hotels_resolution.resolved_hotel_ids or []),
    })

    return IdeationStartV2Response(ideation_id=cid, campaign_id=campaign_id)


@router.post("/resolve-hotels", response_model=ResolveHotelsResponse)
async def resolve_hotels_route(
    body: ResolveHotelsRequest,
    current_user: dict = Depends(get_current_user),
):
    """Resolve a natural-language phrase to concrete hotel_ids. Called from
    Step 1's 'Describe in words' mode. Does not persist anything — the
    frontend renders chips, the user may edit, then submits via /start."""
    if not (body.phrase or "").strip():
        raise HTTPException(400, "Empty phrase.")

    resolved = await _resolve_hotels(body.phrase.strip())

    matched = [ResolvedHotelRef(**m) for m in resolved.get("matched", [])]

    return ResolveHotelsResponse(
        matched=matched,
        resolved_hotel_ids=resolved.get("hotel_ids", []),
        resolved_brand_ids=resolved.get("brand_ids", []),
        is_loyalty=bool(resolved.get("is_loyalty")),
        notes=resolved.get("notes", ""),
    )


@router.post("/resolve-discount", response_model=ResolveDiscountResponse)
async def resolve_discount_route(
    body: ResolveDiscountRequest,
    current_user: dict = Depends(get_current_user),
):
    """v2.9 — normalise a free-text discount phrase into the structured
    {kind, value, notes} shape used by IdeationDiscount. Called from the
    Brief form's discount input."""
    resolved = await _resolve_discount((body.phrase or "").strip())
    return ResolveDiscountResponse(**resolved)


@router.post("/{ideation_id}/directions", response_model=IdeationDirectionsResponse)
async def directions_ideation(
    ideation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Generate the first batch (or regenerate) of 3-5 directions x 5 concepts."""
    db = get_firestore()
    ref = db.collection(_COLL).document(ideation_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)
    if data.get("schema_version", 1) < 2:
        raise HTTPException(409, "Legacy v2.7 ideation — use /answer + /shortlist.")

    inputs = data.get("inputs") or {}
    hotel_context = _hotel_context_from_inputs(inputs)
    iterations = data.get("iterations") or []
    iter_num = len(iterations) + 1

    result = await _generate_directions(
        inputs=inputs,
        iteration_seed=None,
        iteration_number=iter_num,
        hotel_context=hotel_context,
    )

    directions = [
        IdeationDirection(
            id=d.get("id"),
            title=d.get("title"),
            rationale=d.get("rationale"),
            visual_cue=IdeationVisualCue(**(d.get("visual_cue") or {})),
            concepts=[IdeationDirectionConcept(**c) for c in (d.get("concepts") or [])],
        )
        for d in result.get("directions", [])
    ]

    record = {
        "idx": iter_num,
        "kind": "directions",
        "directions": [
            dd.model_dump() if hasattr(dd, "model_dump") else dd.dict() for dd in directions
        ],
        "final": [],
        "seed_direction_id": None,
        "seed_concept_ids": [],
        "freetext_steer": "",
        "created_at": _now(),
    }

    iterations.append(record)
    ref.set({
        "iterations": iterations,
        "phase": "directions",
        "updated_at": _now(),
    }, merge=True)

    _audit_safe("ideation_directions", current_user, {
        "ideation_id": ideation_id,
        "iteration": iter_num,
        "tokens_consumed": int(result.get("tokens_used", 0)),
        "model_used": result.get("model_used", ""),
        "is_loyalty": bool((inputs.get("hotels_resolution") or {}).get("is_loyalty")),
    })

    return IdeationDirectionsResponse(
        iteration=iter_num,
        directions=directions,
        tokens_used=int(result.get("tokens_used", 0)),
        model_used=str(result.get("model_used", "")),
    )


@router.post("/{ideation_id}/refine", response_model=IdeationDirectionsResponse)
async def refine_ideation(
    ideation_id: str,
    body: IdeationRefineRequest,
    current_user: dict = Depends(get_current_user),
):
    """Refine the directions based on the user's selection + free-text steer."""
    db = get_firestore()
    ref = db.collection(_COLL).document(ideation_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)
    if data.get("schema_version", 1) < 2:
        raise HTTPException(409, "Legacy v2.7 ideation — use /answer + /shortlist.")

    inputs = data.get("inputs") or {}
    iterations = data.get("iterations") or []
    iter_num = len(iterations) + 1
    hotel_context = _hotel_context_from_inputs(inputs)

    # Build seed: titles + names from prior iterations are anti-examples.
    prior_titles: list[str] = []
    prior_names: list[str] = []
    for it in iterations:
        for d2 in (it.get("directions") or []):
            prior_titles.append(d2.get("title", ""))
            for cc in (d2.get("concepts") or []):
                prior_names.append(cc.get("name", ""))

    seed = {
        "selected_direction_id": body.selected_direction_id,
        "selected_concept_ids": body.selected_concept_ids or [],
        "freetext_steer": (body.freetext_steer or "").strip(),
        "prior_direction_titles": prior_titles,
        "prior_concept_names": prior_names,
    }

    result = await _generate_directions(
        inputs=inputs,
        iteration_seed=seed,
        iteration_number=iter_num,
        hotel_context=hotel_context,
    )

    directions = [
        IdeationDirection(
            id=d.get("id"),
            title=d.get("title"),
            rationale=d.get("rationale"),
            visual_cue=IdeationVisualCue(**(d.get("visual_cue") or {})),
            concepts=[IdeationDirectionConcept(**c) for c in (d.get("concepts") or [])],
        )
        for d in result.get("directions", [])
    ]

    record = {
        "idx": iter_num,
        "kind": "directions",
        "directions": [
            dd.model_dump() if hasattr(dd, "model_dump") else dd.dict() for dd in directions
        ],
        "final": [],
        "seed_direction_id": body.selected_direction_id,
        "seed_concept_ids": list(body.selected_concept_ids or []),
        "freetext_steer": (body.freetext_steer or "").strip()[:500],
        "created_at": _now(),
    }
    iterations.append(record)
    ref.set({
        "iterations": iterations,
        "phase": "refining",
        "updated_at": _now(),
    }, merge=True)

    _audit_safe("ideation_refine", current_user, {
        "ideation_id": ideation_id,
        "iteration": iter_num,
        "tokens_consumed": int(result.get("tokens_used", 0)),
        "model_used": result.get("model_used", ""),
        "seed_count": len(body.selected_concept_ids or []),
    })

    return IdeationDirectionsResponse(
        iteration=iter_num,
        directions=directions,
        tokens_used=int(result.get("tokens_used", 0)),
        model_used=str(result.get("model_used", "")),
    )


@router.post("/{ideation_id}/finalize", response_model=IdeationFinalResponse)
async def finalize_ideation(
    ideation_id: str,
    body: IdeationFinalizeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate (or regenerate) the Final 10 polished concepts. With
    seed_concept_ids + freetext_steer, replaces the prior Final 10 with a
    fresh batch (merge semantic)."""
    db = get_firestore()
    ref = db.collection(_COLL).document(ideation_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)
    if data.get("schema_version", 1) < 2:
        raise HTTPException(409, "Legacy v2.7 ideation — use /shortlist + /choose.")

    inputs = data.get("inputs") or {}
    iterations = data.get("iterations") or []
    iter_num = len(iterations) + 1
    hotel_context = _hotel_context_from_inputs(inputs)

    result = await _generate_final_concepts(
        inputs=inputs,
        iterations=[_slim_iteration_record(it) for it in iterations],
        seed_concept_ids=list(body.seed_concept_ids or []),
        freetext_steer=(body.freetext_steer or "").strip(),
        hotel_context=hotel_context,
    )

    concepts = [IdeationFinalConcept(
        id=c.get("id"),
        name=c.get("name"),
        justification=c.get("justification"),
        visual_cue=IdeationVisualCue(**(c.get("visual_cue") or {})),
        inspiration_asset_ids=list(c.get("inspiration_asset_ids") or []),
    ) for c in result.get("concepts", [])]

    record = {
        "idx": iter_num,
        "kind": "final",
        "directions": [],
        "final": [
            cc.model_dump() if hasattr(cc, "model_dump") else cc.dict() for cc in concepts
        ],
        "seed_direction_id": None,
        "seed_concept_ids": list(body.seed_concept_ids or []),
        "freetext_steer": (body.freetext_steer or "").strip()[:500],
        "created_at": _now(),
    }
    iterations.append(record)
    ref.set({
        "iterations": iterations,
        "phase": "final",
        "updated_at": _now(),
    }, merge=True)

    _audit_safe("ideation_finalize", current_user, {
        "ideation_id": ideation_id,
        "iteration": iter_num,
        "tokens_consumed": int(result.get("tokens_used", 0)),
        "model_used": result.get("model_used", ""),
        "seed_count": len(body.seed_concept_ids or []),
    })

    return IdeationFinalResponse(
        iteration=iter_num,
        concepts=concepts,
        tokens_used=int(result.get("tokens_used", 0)),
        model_used=str(result.get("model_used", "")),
    )


# ──────────────────────────────────────────────────────────────────
# Legacy v2.7 — kept for in-progress ideations on phase ∈ {critique, shortlist}.
# ──────────────────────────────────────────────────────────────────


@router.post("/start-legacy", response_model=IdeationStartResponse)
async def start_ideation_legacy(
    body: IdeationStartRequest,
    current_user: dict = Depends(get_current_user),
):
    """Legacy v2.7 entry point. The current frontend no longer calls this —
    kept only for debugging old data or rolling back the UI."""
    _enforce_selection_access(body.selection, current_user)

    scope_summary = _scope_summary(body.selection)
    turn = await next_critique_turn(
        theme_text=body.theme_text,
        date_start=body.date_start,
        date_end=body.date_end,
        scope_summary=scope_summary,
        turns=[],
        captured={},
    )

    cid = uuid.uuid4().hex[:16]
    first_q = (turn.get("next_question") or "").strip()
    ready = bool(turn.get("ready_for_shortlist"))
    captured = turn.get("captured") or {}

    turns_payload: list[dict] = []
    if first_q:
        turns_payload.append({"q": first_q, "a": "", "ts": _now()})

    db = get_firestore()
    db.collection(_COLL).document(cid).set({
        "user_id": current_user.get("uid", ""),
        "user_email": current_user.get("sub", ""),
        "schema_version": 1,
        "selection": body.selection.model_dump() if hasattr(body.selection, "model_dump") else body.selection.dict(),
        "theme_text": body.theme_text,
        "date_start": body.date_start or "",
        "date_end": body.date_end or "",
        "phase": "shortlist" if ready else "critique",
        "critique_turns": turns_payload,
        "captured": captured,
        "shortlist": [],
        "chosen_index": None,
        "linked_campaign_id": None,
        "app_version": APP_VERSION,
        "created_at": _now(),
        "updated_at": _now(),
    })

    _audit_safe("ideation_start_legacy", current_user, {
        "ideation_id": cid,
        "theme_text": (body.theme_text or "")[:200],
        "scope": body.selection.scope if body.selection else "",
        "is_loyalty": bool(getattr(body.selection, "is_loyalty", False)),
    })

    return IdeationStartResponse(
        ideation_id=cid,
        next_question=first_q,
        ready_for_shortlist=ready,
    )


@router.post("/{ideation_id}/answer", response_model=IdeationAnswerResponse)
async def answer_ideation(
    ideation_id: str,
    body: IdeationAnswerRequest,
    current_user: dict = Depends(get_current_user),
):
    db = get_firestore()
    ref = db.collection(_COLL).document(ideation_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)
    if data.get("phase") not in ("critique", "shortlist"):
        raise HTTPException(409, f"Cannot answer in phase '{data.get('phase')}'.")

    turns: list[dict] = list(data.get("critique_turns") or [])
    if not turns or (turns[-1].get("a") or "").strip():
        # No outstanding question — silently append a synthetic turn so the model has a target.
        turns.append({"q": "(user added context)", "a": "", "ts": _now()})

    turns[-1]["a"] = (body.answer_text or "").strip()
    turns[-1].setdefault("ts", _now())

    selection = PropertySelection(**data["selection"]) if data.get("selection") else None
    scope_summary = _scope_summary(selection)

    next_turn = await next_critique_turn(
        theme_text=data.get("theme_text", ""),
        date_start=data.get("date_start", ""),
        date_end=data.get("date_end", ""),
        scope_summary=scope_summary,
        turns=turns,
        captured=data.get("captured", {}),
    )
    captured = next_turn.get("captured") or data.get("captured", {})
    ready = bool(next_turn.get("ready_for_shortlist"))
    next_q = (next_turn.get("next_question") or "").strip()

    if not ready and next_q:
        turns.append({"q": next_q, "a": "", "ts": _now()})

    ref.set({
        "critique_turns": turns,
        "captured": captured,
        "phase": "shortlist" if ready else "critique",
        "updated_at": _now(),
    }, merge=True)

    return IdeationAnswerResponse(
        next_question=None if ready else next_q,
        ready_for_shortlist=ready,
        captured=captured,
    )


@router.post("/{ideation_id}/shortlist", response_model=IdeationShortlistResponse)
async def shortlist_ideation(
    ideation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Generate (or regenerate) the 10-item shortlist. Idempotent — overwrites
    any prior shortlist on the doc."""
    db = get_firestore()
    ref = db.collection(_COLL).document(ideation_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)

    selection = PropertySelection(**data["selection"]) if data.get("selection") else None
    is_loyalty = bool(selection and (selection.is_loyalty or selection.scope == "loyalty"))
    sel_dict = data.get("selection") or {}

    try:
        inspiration = await retrieve_visual_inspiration(
            theme_text=data.get("theme_text", ""),
            selection=sel_dict,
            top_k=8,
        )
    except Exception as exc:
        logger.warning("retrieve_visual_inspiration failed: %s", exc)
        inspiration = {"assets": [], "loyalty_mode": is_loyalty, "anonymized": False}

    result = await generate_shortlist(
        theme_text=data.get("theme_text", ""),
        date_start=data.get("date_start", "") or "",
        date_end=data.get("date_end", "") or "",
        scope_summary=_scope_summary(selection),
        captured=data.get("captured", {}),
        is_loyalty=is_loyalty,
        inspiration=inspiration,
    )

    items = [ShortlistItem(**i) for i in result.get("items", [])]
    ref.set({
        "shortlist": [i.model_dump() if hasattr(i, "model_dump") else i.dict() for i in items],
        "phase": "shortlist",
        "updated_at": _now(),
    }, merge=True)

    _audit_safe("ideation_shortlist", current_user, {
        "ideation_id": ideation_id,
        "tokens_consumed": int(result.get("tokens_used", 0)),
        "model_used": result.get("model_used", ""),
        "scope": (selection.scope if selection else ""),
        "is_loyalty": is_loyalty,
        "asset_refs": len(inspiration.get("assets") or []),
    })

    return IdeationShortlistResponse(
        shortlist=items,
        tokens_used=int(result.get("tokens_used", 0)),
        model_used=str(result.get("model_used", "")),
    )


@router.post("/{ideation_id}/choose", response_model=IdeationChooseResponse)
async def choose_concept(
    ideation_id: str,
    body: IdeationChooseRequest,
    current_user: dict = Depends(get_current_user),
):
    """Promote a chosen concept (v2.8 final concept OR v2.7 shortlist item)
    to a draft `unified_campaigns` document."""
    db = get_firestore()
    ref = db.collection(_COLL).document(ideation_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)

    schema_version = int(data.get("schema_version") or 1)
    selection = data.get("selection") or {}

    if schema_version >= 2:
        # v2.8 — read the most recent final iteration.
        iterations = data.get("iterations") or []
        latest_final = None
        for it in reversed(iterations):
            if it.get("kind") == "final" and it.get("final"):
                latest_final = it
                break
        if not latest_final:
            raise HTTPException(409, "No final concepts yet — POST /finalize first.")
        concepts = latest_final.get("final") or []
        if body.index < 0 or body.index >= len(concepts):
            raise HTTPException(400, f"index out of range (0..{len(concepts)-1}).")
        item = concepts[body.index]
        raw_brief = _compose_raw_brief_v2(item, data.get("inputs") or {})
        campaign_name = (item.get("name") or "").strip()[:60]
    else:
        # v2.7 legacy — read shortlist field.
        shortlist = data.get("shortlist") or []
        if not shortlist:
            raise HTTPException(409, "No shortlist yet — POST /shortlist first.")
        if body.index < 0 or body.index >= len(shortlist):
            raise HTTPException(400, f"index out of range (0..{len(shortlist)-1}).")
        item = shortlist[body.index]
        raw_brief = _compose_raw_brief(
            item=item,
            theme_text=data.get("theme_text", ""),
            date_start=data.get("date_start", ""),
            date_end=data.get("date_end", ""),
            captured=data.get("captured", {}),
        )
        campaign_name = (item.get("name") or "").strip()[:60]

    # v2.9 — carry the human-visible campaign_id from the ideation onto the
    # promoted unified_campaigns doc. If the ideation has none (legacy), mint one.
    inherited_campaign_id = data.get("campaign_id") or ensure_campaign_id(ref, data)

    cid = uuid.uuid4().hex[:16]
    db.collection(_CAMPAIGNS_COLL).document(cid).set({
        "user_id": current_user.get("uid", ""),
        "user_email": current_user.get("sub", ""),
        "campaign_id": inherited_campaign_id,
        "status": "draft",
        "raw_brief": raw_brief,
        "reference_urls": [],
        "structured": {"campaign_name": campaign_name} if campaign_name else None,
        "events": [],
        "selection": selection,
        "generated": [],
        "ideation_id": ideation_id,
        "ideation_index": body.index,
        "created_at": _now(),
        "updated_at": _now(),
        "locked_at": None,
    })

    if schema_version >= 2:
        ref.set({
            "chosen_final_index": body.index,
            "linked_campaign_id": cid,
            "phase": "chosen",
            "updated_at": _now(),
        }, merge=True)
    else:
        ref.set({
            "chosen_index": body.index,
            "linked_campaign_id": cid,
            "phase": "chosen",
            "updated_at": _now(),
        }, merge=True)

    _audit_safe("ideation_choose", current_user, {
        "ideation_id": ideation_id,
        "schema_version": schema_version,
        "chosen_index": body.index,
        "unified_campaign_id": cid,
    })

    return IdeationChooseResponse(
        ideation_id=ideation_id,
        chosen_index=body.index,
        unified_campaign_id=cid,
    )


def _compose_raw_brief_v2(concept: dict, inputs: dict) -> str:
    """Compose a Unified-Campaign raw_brief from a v2.8 final concept + inputs."""
    lines: list[str] = []
    name = (concept.get("name") or "").strip()
    if name:
        lines.append(f"Campaign: {name}")
    if concept.get("justification"):
        lines.append(f"Why: {concept['justification']}")
    offer = inputs.get("offer_name") or ""
    inclusions = inputs.get("inclusions") or ""
    if offer:
        lines.append(f"Offer: {offer}")
    if inclusions:
        lines.append(f"Inclusions: {inclusions}")
    discount = inputs.get("discount") or {}
    if discount.get("kind") and discount.get("kind") != "no_discount":
        lines.append(f"Discount: {discount.get('kind')} = {discount.get('value', '')}")
    if inputs.get("audience_axis"):
        lines.append(f"Audience: {inputs['audience_axis'].replace('_', ' ')}")
    if inputs.get("tone_axis"):
        lines.append(f"Tone: {inputs['tone_axis']}")
    vc = concept.get("visual_cue") or {}
    if vc:
        lines.append("")
        lines.append("Visual direction:")
        if vc.get("palette"):
            lines.append(f"  Palette: {', '.join(vc['palette'])}")
        if vc.get("motifs"):
            lines.append(f"  Motifs: {', '.join(vc['motifs'])}")
        if vc.get("photography_style"):
            lines.append(f"  Photography: {vc['photography_style']}")
        if vc.get("mood"):
            lines.append(f"  Mood: {vc['mood']}")
        if vc.get("logo_placement"):
            lines.append(f"  Logo: {vc['logo_placement']}")
    return "\n".join(lines).strip()


def _doc_to_payload(doc) -> dict:
    """Return the raw doc as a JSON-safe dict so both v2.7 and v2.8 shapes
    flow through the GET endpoints unchanged. The frontend keys off
    `schema_version` to pick the right renderer."""
    data = doc.to_dict() or {}
    return {"id": doc.id, **data}


_IN_PROGRESS_PHASES = {"inputs", "directions", "refining", "final", "critique", "shortlist"}


@router.get("/{ideation_id}")
async def get_ideation(
    ideation_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = get_firestore()
    ref = db.collection(_COLL).document(ideation_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)
    # v2.9 — lazy-backfill campaign_id on legacy docs.
    if not data.get("campaign_id"):
        cid = ensure_campaign_id(ref, data)
        data["campaign_id"] = cid
    return {"id": d.id, **data}


@router.get("")
async def list_ideations(
    limit: int = 30,
    status: str = "",
    current_user: dict = Depends(get_current_user),
):
    """List ideations, newest first. v2.9 adds the `status=in_progress`
    filter — used by the Unified Campaign landing page to surface
    ideations not yet promoted to a campaign."""
    db = get_firestore()
    coll = db.collection(_COLL)
    if current_user.get("role") != "admin":
        coll = coll.where("user_id", "==", current_user.get("uid", ""))
    try:
        stream = coll.order_by("updated_at", direction="DESCENDING").limit(limit * 2).stream()
        docs = list(stream)
    except Exception:
        docs = list(coll.limit(max(limit * 3, 30)).stream())
        docs.sort(key=lambda d: (d.to_dict() or {}).get("updated_at", ""), reverse=True)

    if status == "in_progress":
        docs = [d for d in docs if (d.to_dict() or {}).get("phase") in _IN_PROGRESS_PHASES]

    return [_doc_to_payload(d) for d in docs[:limit]]


@router.get("/{ideation_id}/export.csv")
async def export_csv(
    ideation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """v2.9 — CSV export of the Final 10. One row per concept; columns include
    campaign_id, name, justification, story_line, palette, motifs, mood,
    photography_style, logo_placement."""
    db = get_firestore()
    ref = db.collection(_COLL).document(ideation_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)
    if not data.get("campaign_id"):
        data["campaign_id"] = ensure_campaign_id(ref, data)
    csv_text = _exporters.to_csv({"id": d.id, **data})
    fname = f"campaign-{data.get('campaign_id') or ideation_id}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{ideation_id}/export.html")
async def export_html(
    ideation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """v2.9 — Single-page printable HTML deck for the Final 10. Renders
    palette swatches as coloured boxes; print to PDF via the browser."""
    db = get_firestore()
    ref = db.collection(_COLL).document(ideation_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)
    if not data.get("campaign_id"):
        data["campaign_id"] = ensure_campaign_id(ref, data)
    html_text = _exporters.to_html({"id": d.id, **data})
    return Response(content=html_text, media_type="text/html; charset=utf-8")


@router.get("/{ideation_id}/export.json")
async def export_json(
    ideation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """v2.9 — Raw concepts blob with metadata, downloadable."""
    db = get_firestore()
    ref = db.collection(_COLL).document(ideation_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)
    if not data.get("campaign_id"):
        data["campaign_id"] = ensure_campaign_id(ref, data)
    payload = _exporters.to_json({"id": d.id, **data})
    fname = f"campaign-{data.get('campaign_id') or ideation_id}.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/{ideation_id}/archive")
async def archive_ideation(
    ideation_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = get_firestore()
    ref = db.collection(_COLL).document(ideation_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    _require_owner_or_admin(d.to_dict() or {}, current_user)
    ref.set({"phase": "archived", "updated_at": _now()}, merge=True)
    return _doc_to_payload(ref.get())


def _compose_raw_brief(
    item: dict,
    theme_text: str,
    date_start: str,
    date_end: str,
    captured: dict,
) -> str:
    """Build a Unified-Campaign-compatible raw_brief from a chosen shortlist item."""
    lines: list[str] = []
    name = (item.get("name") or "").strip()
    if name:
        lines.append(f"Campaign: {name}")
    tagline = (item.get("tagline") or "").strip()
    if tagline:
        lines.append(f"Tagline: {tagline}")
    if theme_text:
        lines.append(f"Theme: {theme_text}")
    if date_start or date_end:
        lines.append(f"Dates: {date_start or '?'} to {date_end or '?'}")
    captured = captured or {}
    for k in ("audience", "hero_offer", "tone", "must_mention", "must_avoid"):
        v = (captured.get(k) or "").strip() if isinstance(captured.get(k), str) else ""
        if v:
            lines.append(f"{k.replace('_', ' ').title()}: {v}")
    story = (item.get("story_line") or "").strip()
    if story:
        lines.append(f"\nStory line:\n{story}")
    visual = (item.get("visual_direction") or "").strip()
    if visual:
        lines.append(f"\nVisual direction:\n{visual}")
    return "\n".join(lines).strip()
