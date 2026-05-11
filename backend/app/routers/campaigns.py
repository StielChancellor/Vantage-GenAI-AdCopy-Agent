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
)
from backend.app.services.campaigns.structurer import structure_brief
from backend.app.services.campaigns.orchestrator import run_campaign

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
    """Step-1 → step-2: structure the brief and persist as a draft."""
    structured_data = await structure_brief(body.raw_brief, body.reference_urls)
    db = get_firestore()
    cid = uuid.uuid4().hex[:16]
    payload = {
        "user_id": current_user.get("uid", ""),
        "user_email": current_user.get("sub", ""),
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


@router.get("/{campaign_id}", response_model=UnifiedCampaign)
async def get_campaign(campaign_id: str, current_user: dict = Depends(get_current_user)):
    db = get_firestore()
    d = db.collection(_COLL).document(campaign_id).get()
    if not d.exists:
        raise HTTPException(404, "Campaign not found.")
    _require_owner_or_admin(d.to_dict() or {}, current_user)
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
