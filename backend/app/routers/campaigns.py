"""Unified Campaign endpoints (v2.6).

Lifecycle:
  draft → POST /campaigns/{id}/lock → locked → POST /unlock → draft
  PATCH only valid while draft. POST /generate runs the orchestrator and
  appends results to the doc; it works for both draft and locked campaigns.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.app.core.auth import get_current_user
from backend.app.core.database import get_firestore
from backend.app.models.schemas import (
    UnifiedCampaignBrief, UnifiedCampaign, StructuredCampaign,
    UnifiedCampaignSelection, CampaignPatchRequest,
    CampaignGenerateRequest, CampaignGenerateResponse,
    PastBrief,
    # v3.0 streaming
    StartAsyncRequest, StartAsyncResponse, JobState, JobStateResponse,
    GenerationRow, GenerationsListResponse,
    SteerRequest, SteerResponse, RegenStaleResponse,
)
from backend.app.services.campaigns.structurer import structure_brief
from backend.app.services.campaigns.orchestrator import run_campaign
from backend.app.services.campaigns import streaming as _streaming
from backend.app.services.ideation.campaign_id import (
    generate_campaign_id, ensure_campaign_id,
)

logger = logging.getLogger("vantage.campaigns")
router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

_COLL = "unified_campaigns"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_to_campaign(doc) -> UnifiedCampaign:
    data = doc.to_dict() or {}
    return UnifiedCampaign(
        id=doc.id,
        user_id=data.get("user_id", ""),
        user_email=data.get("user_email", ""),
        campaign_id=data.get("campaign_id"),
        ideation_id=data.get("ideation_id"),
        status=data.get("status", "draft"),
        raw_brief=data.get("raw_brief", ""),
        reference_urls=list(data.get("reference_urls") or []),
        structured=(StructuredCampaign(**data["structured"]) if data.get("structured") else None),
        events=list(data.get("events") or []),
        selection=(UnifiedCampaignSelection(**data["selection"]) if data.get("selection") else None),
        generated=list(data.get("generated") or []),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        locked_at=data.get("locked_at"),
    )


def _require_owner_or_admin(doc_data: dict, current_user: dict) -> None:
    """Owners and admins may read/write. Everyone else: 403."""
    if current_user.get("role") == "admin":
        return
    if (doc_data or {}).get("user_id") == current_user.get("uid"):
        return
    raise HTTPException(403, "You don't have access to this campaign.")


# ──────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────


@router.post("/structure", response_model=StructuredCampaign)
async def structure_only(body: UnifiedCampaignBrief, _user=Depends(get_current_user)):
    """Step-1 hot path: structure a brief without persisting anything.
    Useful when the frontend wants a 'preview' before saving."""
    data = await structure_brief(body.raw_brief, body.reference_urls)
    return StructuredCampaign(**data)


@router.post("", response_model=UnifiedCampaign)
async def create_campaign(body: UnifiedCampaignBrief, current_user: dict = Depends(get_current_user)):
    """Step-1 → step-2: structure the brief and persist as a draft.
    v2.9 — mints a 5-char human-visible campaign_id."""
    structured_data = await structure_brief(body.raw_brief, body.reference_urls)
    db = get_firestore()
    cid = uuid.uuid4().hex[:16]
    payload = {
        "user_id": current_user.get("uid", ""),
        "user_email": current_user.get("sub", ""),
        "campaign_id": generate_campaign_id(),
        "status": "draft",
        "raw_brief": body.raw_brief,
        "reference_urls": list(body.reference_urls or []),
        "structured": structured_data,
        "events": [],
        "selection": None,
        "generated": [],
        "created_at": _now(),
        "updated_at": _now(),
        "locked_at": None,
    }
    db.collection(_COLL).document(cid).set(payload)
    doc = db.collection(_COLL).document(cid).get()
    return _doc_to_campaign(doc)


@router.get("", response_model=list[UnifiedCampaign])
async def list_campaigns(
    status: str | None = None,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """List the caller's campaigns, newest first. Admins see everyone's."""
    db = get_firestore()
    coll = db.collection(_COLL)
    if current_user.get("role") != "admin":
        coll = coll.where("user_id", "==", current_user.get("uid", ""))
    if status:
        coll = coll.where("status", "==", status)
    try:
        stream = coll.order_by("updated_at", direction="DESCENDING").limit(limit).stream()
        docs = list(stream)
    except Exception:
        docs = list(coll.limit(max(limit * 3, 30)).stream())
        docs.sort(key=lambda d: (d.to_dict() or {}).get("updated_at", ""), reverse=True)
        docs = docs[:limit]
    return [_doc_to_campaign(d) for d in docs]


@router.get("/past-briefs", response_model=list[PastBrief])
async def list_past_briefs(
    limit: int = 5,
    current_user: dict = Depends(get_current_user),
):
    """v2.9 — last N locked campaigns for the current user.
    Surfaced on the Unified Campaign landing page's "Past Briefs" section."""
    db = get_firestore()
    coll = db.collection(_COLL).where("status", "==", "locked")
    if current_user.get("role") != "admin":
        coll = coll.where("user_id", "==", current_user.get("uid", ""))
    try:
        stream = coll.order_by("locked_at", direction="DESCENDING").limit(limit).stream()
        docs = list(stream)
    except Exception:
        docs = list(coll.limit(max(limit * 3, 30)).stream())
        docs.sort(
            key=lambda d: ((d.to_dict() or {}).get("locked_at") or (d.to_dict() or {}).get("updated_at") or ""),
            reverse=True,
        )
        docs = docs[:limit]

    out: list[PastBrief] = []
    for d in docs:
        data = d.to_dict() or {}
        structured = data.get("structured") or {}
        out.append(PastBrief(
            id=d.id,
            campaign_id=data.get("campaign_id"),
            campaign_name=(structured.get("campaign_name") or "")[:120],
            status=data.get("status", "draft"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            locked_at=data.get("locked_at"),
        ))
    return out


@router.get("/{campaign_id}", response_model=UnifiedCampaign)
async def get_campaign(campaign_id: str, current_user: dict = Depends(get_current_user)):
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)
    # v2.9 — lazy-backfill campaign_id on legacy docs.
    if not data.get("campaign_id"):
        ensure_campaign_id(ref, data)
        d = ref.get()
    return _doc_to_campaign(d)


@router.patch("/{campaign_id}", response_model=UnifiedCampaign)
async def patch_campaign(campaign_id: str, body: CampaignPatchRequest, current_user: dict = Depends(get_current_user)):
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)
    if data.get("status") == "locked":
        raise HTTPException(409, "Campaign is locked. POST /unlock to edit.")

    update: dict = {"updated_at": _now()}
    if body.structured is not None:
        update["structured"] = body.structured.model_dump() if hasattr(body.structured, "model_dump") else body.structured.dict()
    if body.reference_urls is not None:
        update["reference_urls"] = list(body.reference_urls)
    if body.events is not None:
        update["events"] = list(body.events)
    if body.selection is not None:
        update["selection"] = body.selection.model_dump() if hasattr(body.selection, "model_dump") else body.selection.dict()
    ref.set(update, merge=True)
    return _doc_to_campaign(ref.get())


@router.post("/{campaign_id}/lock", response_model=UnifiedCampaign)
async def lock_campaign(campaign_id: str, current_user: dict = Depends(get_current_user)):
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    _require_owner_or_admin(d.to_dict() or {}, current_user)
    ref.set({"status": "locked", "locked_at": _now(), "updated_at": _now()}, merge=True)
    return _doc_to_campaign(ref.get())


@router.post("/{campaign_id}/unlock", response_model=UnifiedCampaign)
async def unlock_campaign(campaign_id: str, current_user: dict = Depends(get_current_user)):
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    _require_owner_or_admin(d.to_dict() or {}, current_user)
    ref.set({"status": "draft", "updated_at": _now()}, merge=True)
    return _doc_to_campaign(ref.get())


@router.post("/{campaign_id}/archive", response_model=UnifiedCampaign)
async def archive_campaign(campaign_id: str, current_user: dict = Depends(get_current_user)):
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    _require_owner_or_admin(d.to_dict() or {}, current_user)
    ref.set({"status": "archived", "updated_at": _now()}, merge=True)
    return _doc_to_campaign(ref.get())


@router.post("/{campaign_id}/generate", response_model=CampaignGenerateResponse)
async def generate_campaign(
    campaign_id: str,
    body: CampaignGenerateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Fan-out: run one ad-copy / CRM generation per (entity × channel × level)."""
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)

    campaign = {"id": d.id, **data}
    try:
        result = await run_campaign(campaign, override_selection=body.selection)
    except Exception as exc:
        logger.error(
            "campaign_generate_failed",
            extra={"json_fields": {
                "campaign_id": campaign_id,
                "exc_type": type(exc).__name__,
                "exc": str(exc)[:500],
            }},
            exc_info=True,
        )
        raise HTTPException(500, f"Campaign generation failed: {str(exc)[:200]}")

    # Persist the generated results + the effective selection used.
    try:
        sel_dict = None
        if body.selection is not None:
            sel_dict = body.selection.model_dump() if hasattr(body.selection, "model_dump") else body.selection.dict()
        update = {
            "generated": result["results"],
            "updated_at": _now(),
        }
        if sel_dict is not None:
            update["selection"] = sel_dict
        ref.set(update, merge=True)
    except Exception as exc:
        logger.warning("campaign_generate persist failed: %s", exc)

    return CampaignGenerateResponse(**result)


# ──────────────────────────────────────────────────────────────────
# v3.0 — Streaming fan-out
# ──────────────────────────────────────────────────────────────────


@router.post("/{campaign_id}/generate-async", response_model=StartAsyncResponse)
async def generate_async(
    campaign_id: str,
    body: StartAsyncRequest,
    current_user: dict = Depends(get_current_user),
):
    """Kick off a streaming fan-out and return immediately.
    The worker writes per-row results to the generations subcollection."""
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)

    try:
        result = await _streaming.start_job(
            campaign_id,
            override_selection=body.selection,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error(
            "campaign_generate_async_failed",
            extra={"json_fields": {"campaign_id": campaign_id, "exc": str(exc)[:300]}},
            exc_info=True,
        )
        raise HTTPException(500, f"Failed to start job: {str(exc)[:200]}")

    return StartAsyncResponse(**result)


@router.get("/{campaign_id}/job", response_model=JobStateResponse)
async def get_job_state(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = get_firestore()
    d = db.collection(_COLL).document(campaign_id).get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    data = d.to_dict() or {}
    _require_owner_or_admin(data, current_user)
    job_raw = data.get("job") or None
    job = JobState(**job_raw) if job_raw else None
    return JobStateResponse(status=data.get("status", "draft"), job=job)


@router.get("/{campaign_id}/generations", response_model=GenerationsListResponse)
async def list_generations(
    campaign_id: str,
    since: int = -1,
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
):
    """Return generation rows where idx > since, ordered ascending.
    Polled every 2s by the streaming UI."""
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    d = ref.get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    _require_owner_or_admin(d.to_dict() or {}, current_user)

    rows: list[GenerationRow] = []
    try:
        # Stream and filter client-side — collection is small (≤ 400 rows).
        # Firestore composite index on (idx,) lets us order if needed.
        for doc in ref.collection("generations").stream():
            data = doc.to_dict() or {}
            idx = int(data.get("idx", -1))
            if idx <= since:
                continue
            rows.append(GenerationRow(**data))
    except Exception as exc:
        logger.warning("list_generations failed: %s", exc)
        raise HTTPException(500, "Could not load generations.")

    rows.sort(key=lambda r: r.idx)
    rows = rows[:limit]
    next_since = rows[-1].idx if rows else since
    return GenerationsListResponse(rows=rows, next_since=next_since)


@router.post("/{campaign_id}/steer", response_model=SteerResponse)
async def steer_job_route(
    campaign_id: str,
    body: SteerRequest,
    current_user: dict = Depends(get_current_user),
):
    """Apply a new brief mid-flight. brief_revision increments; remaining
    tasks (and optionally the already-completed ones) get re-flagged."""
    db = get_firestore()
    d = db.collection(_COLL).document(campaign_id).get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    _require_owner_or_admin(d.to_dict() or {}, current_user)
    try:
        out = _streaming.steer_job(campaign_id, body.structured, scope=body.scope)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return SteerResponse(
        brief_revision=out["brief_revision"],
        completed_marked_stale=out["completed_marked_stale"],
    )


@router.post("/{campaign_id}/cancel")
async def cancel_job_route(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = get_firestore()
    d = db.collection(_COLL).document(campaign_id).get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    _require_owner_or_admin(d.to_dict() or {}, current_user)
    _streaming.cancel_job(campaign_id)
    return {"cancelled": True}


@router.post("/{campaign_id}/regen-stale", response_model=RegenStaleResponse)
async def regen_stale_route(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = get_firestore()
    d = db.collection(_COLL).document(campaign_id).get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    _require_owner_or_admin(d.to_dict() or {}, current_user)
    out = _streaming.regen_stale(campaign_id)
    # Auto-spin the worker so the flipped rows actually run.
    try:
        restarted = await _streaming._ensure_worker(campaign_id)
    except Exception as exc:
        logger.warning("worker restart after regen-stale failed: %s", exc)
        restarted = False
    return RegenStaleResponse(flipped=out["flipped"], worker_restarted=bool(restarted))


@router.post("/{campaign_id}/resume")
async def resume_job_route(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = get_firestore()
    d = db.collection(_COLL).document(campaign_id).get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    _require_owner_or_admin(d.to_dict() or {}, current_user)
    try:
        started_new = await _streaming.resume_job(campaign_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"worker_started": bool(started_new)}
