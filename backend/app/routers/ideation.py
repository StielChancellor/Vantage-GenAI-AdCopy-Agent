"""Campaign Ideation endpoints (v2.7).

Upstream tool that produces a 10-concept shortlist from a free-text theme
and a critique chat, grounded in past static-creative assets. Selecting a
shortlist item creates a draft `unified_campaigns` doc so the user
continues into lock → fan-out via the existing Unified Campaign flow.

Lifecycle on `campaign_ideations/{id}`:
  critique → shortlist → chosen | archived
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
    IdeationStartRequest, IdeationStartResponse,
    IdeationAnswerRequest, IdeationAnswerResponse,
    IdeationShortlistResponse, ShortlistItem,
    IdeationChooseRequest, IdeationChooseResponse,
    IdeationState, CritiqueTurn, PropertySelection,
)
from backend.app.services.ideation.critique_engine import next_critique_turn
from backend.app.services.ideation.shortlist_generator import generate_shortlist
from backend.app.services.rag_engine import retrieve_visual_inspiration

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


@router.post("/start", response_model=IdeationStartResponse)
async def start_ideation(
    body: IdeationStartRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a new ideation doc and return the first critique question."""
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

    _audit_safe("ideation_start", current_user, {
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
async def choose_shortlist(
    ideation_id: str,
    body: IdeationChooseRequest,
    current_user: dict = Depends(get_current_user),
):
    """Promote a shortlist item to a draft `unified_campaigns` document and
    record the link on the ideation."""
    db = get_firestore()
    ref = db.collection(_COLL).document(ideation_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)

    shortlist = data.get("shortlist") or []
    if not shortlist:
        raise HTTPException(409, "No shortlist yet — POST /shortlist first.")
    if body.index < 0 or body.index >= len(shortlist):
        raise HTTPException(400, f"index out of range (0..{len(shortlist)-1}).")

    item = shortlist[body.index]
    selection = data.get("selection") or {}

    raw_brief = _compose_raw_brief(
        item=item,
        theme_text=data.get("theme_text", ""),
        date_start=data.get("date_start", ""),
        date_end=data.get("date_end", ""),
        captured=data.get("captured", {}),
    )

    cid = uuid.uuid4().hex[:16]
    db.collection(_CAMPAIGNS_COLL).document(cid).set({
        "user_id": current_user.get("uid", ""),
        "user_email": current_user.get("sub", ""),
        "status": "draft",
        "raw_brief": raw_brief,
        "reference_urls": [],
        "structured": None,
        "events": [],
        "selection": selection,
        "generated": [],
        "ideation_id": ideation_id,
        "ideation_index": body.index,
        "created_at": _now(),
        "updated_at": _now(),
        "locked_at": None,
    })

    ref.set({
        "chosen_index": body.index,
        "linked_campaign_id": cid,
        "phase": "chosen",
        "updated_at": _now(),
    }, merge=True)

    _audit_safe("ideation_choose", current_user, {
        "ideation_id": ideation_id,
        "chosen_index": body.index,
        "unified_campaign_id": cid,
    })

    return IdeationChooseResponse(
        ideation_id=ideation_id,
        chosen_index=body.index,
        unified_campaign_id=cid,
    )


@router.get("/{ideation_id}", response_model=IdeationState)
async def get_ideation(
    ideation_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = get_firestore()
    d = db.collection(_COLL).document(ideation_id).get()
    if not d.exists:
        raise HTTPException(404, "Ideation not found.")
    _require_owner_or_admin(d.to_dict() or {}, current_user)
    return _doc_to_state(d)


@router.get("", response_model=list[IdeationState])
async def list_ideations(
    limit: int = 30,
    current_user: dict = Depends(get_current_user),
):
    db = get_firestore()
    coll = db.collection(_COLL)
    if current_user.get("role") != "admin":
        coll = coll.where("user_id", "==", current_user.get("uid", ""))
    try:
        stream = coll.order_by("updated_at", direction="DESCENDING").limit(limit).stream()
        docs = list(stream)
    except Exception:
        docs = list(coll.limit(max(limit * 3, 30)).stream())
        docs.sort(key=lambda d: (d.to_dict() or {}).get("updated_at", ""), reverse=True)
        docs = docs[:limit]
    return [_doc_to_state(d) for d in docs]


@router.post("/{ideation_id}/archive", response_model=IdeationState)
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
    return _doc_to_state(ref.get())


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
