import io
import csv
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse

from backend.app.core.auth import (
    require_admin, hash_password, invalidate_assignment_cache,
    role_allows_brand_scope, role_allows_multi_hotel,
    ROLE_HOTEL_MM, ROLE_BRAND_MANAGER, ROLE_AREA_MANAGER, ROLE_AGENCY,
)
from backend.app.core.database import get_firestore
from backend.app.models.schemas import (
    UserCreate, UserOut, CSVUploadResponse, BrandUSP, AdminSettings,
    ScopeAssignment, ScopeSummary,
)
from backend.app.services.csv_ingestion import ingest_historical_csv, ingest_brand_usp_csv
from backend.app.services.hotels import catalog as hotel_catalog

AVAILABLE_MODELS = [
    {"id": "gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro (Preview) — needs Model Garden enablement"},
    {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash (Default)"},
    {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
    {"id": "claude-opus-4-7", "label": "Claude Opus 4.7 (Anthropic, via Vertex)"},
    {"id": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash Lite"},
    {"id": "gemini-2.0-flash-lite", "label": "Gemini 2.0 Flash Lite"},
]

# Cost calculation: USD per 1M tokens
MODEL_PRICING = {
    "gemini-3.1-pro-preview": {"input": 3.50, "output": 14.00},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
    # Anthropic Claude on Vertex AI Model Garden.
    "claude-opus-4-7": {"input": 15.00, "output": 75.00},
}
USD_TO_INR = 85.0


def calculate_cost_inr(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in INR for a generation."""
    pricing = MODEL_PRICING.get(model, {"input": 0.15, "output": 0.60})
    cost_usd = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return round(cost_usd * USD_TO_INR, 4)


router = APIRouter()


# ──────────────────────────────────────────────────────────────────
# Helpers — assignment validation + denormalized scope_summary
# ──────────────────────────────────────────────────────────────────


def _validate_assignments(role: str, assignments: list[ScopeAssignment]) -> None:
    """Reject role↔assignment combinations the data model doesn't allow.

    v2.4 — adds 'group' (full access) and 'city' scopes:
      - 'group' is admin-equivalent. It must stand alone and is allowed only
        for agency / brand_manager / admin (admin already short-circuits).
      - 'city' grants are allowed for area_manager (city-of-hotels) and agency.
    """
    if role == "admin":
        return  # admin assignments are ignored — they have everything

    # Group scope must stand alone.
    has_group = any(a.scope == "group" for a in assignments)
    if has_group:
        if len(assignments) != 1:
            raise HTTPException(400, "scope='group' must be the sole assignment.")
        if role not in (ROLE_AGENCY, ROLE_BRAND_MANAGER):
            raise HTTPException(400, "scope='group' requires role agency or brand_manager (or admin).")
        return

    if role == ROLE_HOTEL_MM:
        if len(assignments) != 1 or assignments[0].scope != "hotel":
            raise HTTPException(400, "hotel_marketing_manager must have exactly 1 hotel assignment.")
    if role == ROLE_BRAND_MANAGER:
        # Brand managers may have brand + city; never raw hotel-only.
        for a in assignments:
            if a.scope not in ("brand", "city"):
                raise HTTPException(400, "brand_manager assignments must be brand- or city-scoped.")
    if role == ROLE_AREA_MANAGER:
        # Area managers are hotel- or city-scoped (no brand-level access).
        for a in assignments:
            if a.scope not in ("hotel", "city"):
                raise HTTPException(400, "area_manager assignments must be hotel- or city-scoped.")
    if not role_allows_multi_hotel(role) and sum(1 for a in assignments if a.scope == "hotel") > 1:
        raise HTTPException(400, f"Role '{role}' cannot have more than one hotel.")

    for a in assignments:
        if a.scope == "brand" and not a.brand_id:
            raise HTTPException(400, "brand_id required on brand-scope assignments.")
        if a.scope == "hotel" and not a.hotel_id:
            raise HTTPException(400, "hotel_id required on hotel-scope assignments.")
        if a.scope == "city" and not (a.city or "").strip():
            raise HTTPException(400, "city required on city-scope assignments.")
        if a.scope == "brand" and not role_allows_brand_scope(role):
            raise HTTPException(400, f"Role '{role}' cannot hold brand-scope assignments.")
        if a.brand_only and a.scope != "brand":
            raise HTTPException(400, "brand_only=True is valid only on brand-scope assignments.")


def _write_assignments(uid: str, assignments: list[ScopeAssignment]) -> None:
    """Replace the user's assignment list (idempotent)."""
    db = get_firestore()
    items_ref = db.collection("property_assignments").document(uid).collection("items")
    # Delete existing first
    for d in items_ref.stream():
        d.reference.delete()
    # Write new
    for a in assignments:
        item = {
            "scope": a.scope,
            "brand_id": a.brand_id or None,
            "hotel_id": a.hotel_id or None,
            "city": (a.city or None) if a.scope == "city" else None,
            "brand_only": bool(a.brand_only) if a.scope == "brand" else False,
            "granted_at": datetime.now(timezone.utc).isoformat(),
        }
        items_ref.add(item)
    invalidate_assignment_cache(uid)


def _build_scope_summary(assignments: list[ScopeAssignment]) -> ScopeSummary:
    """Resolve assignment IDs back to display names so the UI can chip them.

    v2.4 — also tracks city scope, group scope, loyalty access, and the flat
    hotel-id list (capped) the user can see. Used by the IntelligentPropertyPicker
    to skip the picker entirely when the user has only one accessible entity."""
    brand_names: list[str] = []
    hotel_names: list[str] = []
    city_names: list[str] = []
    has_group = False
    has_loyalty = False
    db = get_firestore()
    for a in assignments:
        if a.scope == "group":
            has_group = True
            continue
        if a.scope == "brand" and a.brand_id:
            d = db.collection("brands").document(a.brand_id).get()
            if d.exists:
                bdata = d.to_dict() or {}
                brand_names.append(bdata.get("brand_name", ""))
                if bdata.get("kind") == "loyalty":
                    has_loyalty = True
        elif a.scope == "hotel" and a.hotel_id:
            d = db.collection("hotels").document(a.hotel_id).get()
            if d.exists:
                hotel_names.append((d.to_dict() or {}).get("hotel_name", ""))
        elif a.scope == "city" and a.city:
            city_names.append(a.city)
    # Count expansion: brand grants implicitly include their hotels, so the
    # hotel_count below is the *direct* hotel grants only — picker uses this
    # to decide whether to render the static-chip mode.
    return ScopeSummary(
        brand_count=len(brand_names),
        hotel_count=len(hotel_names),
        city_count=len(city_names),
        has_group=has_group,
        has_loyalty=has_loyalty,
        brand_names=brand_names[:3],
        hotel_names=hotel_names[:3],
        city_names=city_names[:3],
    )


def _safe_assignment(d: dict) -> dict:
    """Defensively coerce a Firestore-stored assignment doc into the v2.4 shape.
    Older docs may be missing 'city'/'brand_only'; treat them as defaults."""
    return {
        "scope": d.get("scope") or "hotel",
        "brand_id": d.get("brand_id"),
        "hotel_id": d.get("hotel_id"),
        "city": d.get("city"),
        "brand_only": bool(d.get("brand_only", False)),
        "granted_at": d.get("granted_at"),
    }


def _user_to_out(uid: str, data: dict, assignments: list[dict] | None = None) -> UserOut:
    """Fold a Firestore user doc + assignments into UserOut."""
    if assignments is None:
        try:
            items = list(
                get_firestore().collection("property_assignments").document(uid).collection("items").stream()
            )
            assignments = [a.to_dict() for a in items]
        except Exception:
            assignments = []
    summary = _build_scope_summary([ScopeAssignment(**_safe_assignment(a)) for a in assignments]) if assignments else ScopeSummary()
    return UserOut(
        uid=uid,
        full_name=data.get("full_name", ""),
        email=data.get("email", ""),
        role=data.get("role", "user"),
        show_token_count=bool(data.get("show_token_count", False)),
        show_token_amount=bool(data.get("show_token_amount", False)),
        scope_summary=summary,
        created_at=data.get("created_at"),
    )


# ──────────────────────────────────────────────────────────────────
# User Management — v2.2
# ──────────────────────────────────────────────────────────────────


@router.post("/admin/users", response_model=UserOut)
async def create_user(body: UserCreate, admin: dict = Depends(require_admin)):
    db = get_firestore()
    existing = list(
        db.collection("users").where("email", "==", body.email).limit(1).stream()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    _validate_assignments(body.role, body.assignments)

    user_doc = {
        "full_name": body.full_name,
        "email": body.email,
        "password_hash": hash_password(body.password),
        "role": body.role,
        "show_token_count": bool(body.show_token_count),
        "show_token_amount": bool(body.show_token_amount),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": admin["sub"],
    }
    _, ref = db.collection("users").add(user_doc)
    _write_assignments(ref.id, body.assignments)

    return _user_to_out(ref.id, user_doc, [a.model_dump() for a in body.assignments])


@router.get("/admin/users", response_model=list[UserOut])
async def list_users(admin: dict = Depends(require_admin)):
    db = get_firestore()
    docs = list(db.collection("users").stream())
    return [_user_to_out(d.id, d.to_dict() or {}) for d in docs]


@router.get("/admin/users/{user_id}", response_model=UserOut)
async def get_user(user_id: str, admin: dict = Depends(require_admin)):
    db = get_firestore()
    d = db.collection("users").document(user_id).get()
    if not d.exists:
        raise HTTPException(404, "User not found")
    items = list(db.collection("property_assignments").document(user_id).collection("items").stream())
    return _user_to_out(user_id, d.to_dict() or {}, [i.to_dict() for i in items])


@router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    db = get_firestore()
    doc_ref = db.collection("users").document(user_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    # Cascade: clear assignments first
    for d in db.collection("property_assignments").document(user_id).collection("items").stream():
        d.reference.delete()
    doc_ref.delete()
    invalidate_assignment_cache(user_id)
    return {"message": "User deleted"}


@router.put("/admin/users/{user_id}", response_model=UserOut)
async def update_user(user_id: str, body: UserCreate, admin: dict = Depends(require_admin)):
    db = get_firestore()
    doc_ref = db.collection("users").document(user_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    _validate_assignments(body.role, body.assignments)

    update_data = {
        "full_name": body.full_name,
        "email": body.email,
        "role": body.role,
        "show_token_count": bool(body.show_token_count),
        "show_token_amount": bool(body.show_token_amount),
    }
    if body.password:
        update_data["password_hash"] = hash_password(body.password)
    doc_ref.update(update_data)

    _write_assignments(user_id, body.assignments)

    updated = doc_ref.get().to_dict()
    return _user_to_out(user_id, updated, [a.model_dump() for a in body.assignments])


# Scope search — for the cascading PropertySwitcher in the user form
@router.get("/admin/scope-search")
async def admin_scope_search(q: str = "", limit: int = 30, admin: dict = Depends(require_admin)):
    rows = hotel_catalog.search_scope(q, limit=limit)
    return {"results": rows}


# ── CSV Uploads ──────────────────────────────────────
@router.post("/admin/upload/historical-ads", response_model=CSVUploadResponse)
async def upload_historical_ads(
    file: UploadFile = File(...), admin: dict = Depends(require_admin)
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")

    content = await file.read()
    df = pd.read_csv(io.BytesIO(content))
    result = ingest_historical_csv(df)
    return result


@router.post("/admin/upload/brand-usp", response_model=CSVUploadResponse)
async def upload_brand_usp(
    file: UploadFile = File(...), admin: dict = Depends(require_admin)
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")

    content = await file.read()
    df = pd.read_csv(io.BytesIO(content))
    result = ingest_brand_usp_csv(df)
    return result


# ── Audit Logs ───────────────────────────────────────
@router.get("/admin/audit-logs")
async def get_audit_logs(
    limit: int = 100, admin: dict = Depends(require_admin)
):
    db = get_firestore()
    docs = (
        db.collection("audit_logs")
        .order_by("timestamp", direction="DESCENDING")
        .limit(limit)
        .stream()
    )
    results = []
    for doc in docs:
        data = doc.to_dict()
        # Calculate cost for generation logs that don't already have it
        if data.get("action") == "generate" and "cost_inr" not in data:
            model = data.get("model_used", "gemini-2.5-flash")
            input_t = data.get("input_tokens", 0)
            output_t = data.get("output_tokens", 0)
            if input_t == 0 and output_t == 0 and data.get("tokens_consumed", 0) > 0:
                total = data["tokens_consumed"]
                input_t = int(total * 0.7)
                output_t = total - input_t
            data["cost_inr"] = calculate_cost_inr(model, input_t, output_t)
        # Extract hotel_name from inputs dict for older logs
        if data.get("action") == "generate" and "hotel_name" not in data:
            inputs = data.get("inputs", {})
            data["hotel_name"] = inputs.get("hotel_name", "")
        results.append({"id": doc.id, **data})
    return results


@router.get("/admin/usage-stats")
async def get_usage_stats(admin: dict = Depends(require_admin)):
    db = get_firestore()
    logs = list(db.collection("audit_logs").stream())

    stats = {}
    for log in logs:
        data = log.to_dict()
        email = data.get("user_email", "unknown")
        if email not in stats:
            stats[email] = {"total_tokens": 0, "login_count": 0, "generations": 0, "total_cost_inr": 0.0}
        if data.get("action") == "login":
            stats[email]["login_count"] += 1
        if data.get("action") == "generate":
            stats[email]["generations"] += 1
            stats[email]["total_tokens"] += data.get("tokens_consumed", 0)
            if "cost_inr" in data:
                stats[email]["total_cost_inr"] += data["cost_inr"]
            else:
                model = data.get("model_used", "gemini-2.5-flash")
                input_t = data.get("input_tokens", 0)
                output_t = data.get("output_tokens", 0)
                if input_t == 0 and output_t == 0 and data.get("tokens_consumed", 0) > 0:
                    total = data["tokens_consumed"]
                    input_t = int(total * 0.7)
                    output_t = total - input_t
                stats[email]["total_cost_inr"] += calculate_cost_inr(model, input_t, output_t)

    for email in stats:
        stats[email]["total_cost_inr"] = round(stats[email]["total_cost_inr"], 4)

    return stats


# ── Export ───────────────────────────────────────────
@router.get("/admin/export/usage")
async def export_usage_csv(admin: dict = Depends(require_admin)):
    """Export all generation audit logs as a downloadable CSV."""
    db = get_firestore()
    docs = (
        db.collection("audit_logs")
        .order_by("timestamp", direction="DESCENDING")
        .stream()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Timestamp", "User Email", "Hotel Name", "Offer Name",
        "Platforms", "Inclusions", "Campaign Objective", "Reference URLs",
        "Total Tokens", "Input Tokens", "Output Tokens",
        "Model Used", "Cost (INR)", "Time (seconds)"
    ])

    for doc in docs:
        data = doc.to_dict()
        if data.get("action") != "generate":
            continue

        model = data.get("model_used", "gemini-2.5-flash")
        input_t = data.get("input_tokens", 0)
        output_t = data.get("output_tokens", 0)
        if input_t == 0 and output_t == 0 and data.get("tokens_consumed", 0) > 0:
            total = data["tokens_consumed"]
            input_t = int(total * 0.7)
            output_t = total - input_t

        cost = data.get("cost_inr", calculate_cost_inr(model, input_t, output_t))

        inputs = data.get("inputs", {})
        hotel_name = data.get("hotel_name", inputs.get("hotel_name", ""))
        offer_name = data.get("offer_name", inputs.get("offer_name", ""))
        platforms = data.get("platforms", inputs.get("platforms", []))
        inclusions = data.get("inclusions", inputs.get("inclusions", ""))
        objective = data.get("campaign_objective", inputs.get("campaign_objective", ""))
        ref_urls = data.get("reference_urls", inputs.get("reference_urls", inputs.get("reference_url", "")))

        writer.writerow([
            data.get("timestamp", ""),
            data.get("user_email", ""),
            hotel_name,
            offer_name,
            ", ".join(platforms) if isinstance(platforms, list) else str(platforms),
            inclusions,
            objective,
            ", ".join(ref_urls) if isinstance(ref_urls, list) else str(ref_urls),
            data.get("tokens_consumed", 0),
            input_t,
            output_t,
            model,
            f"{cost:.4f}",
            data.get("time_seconds", ""),
        ])

    output.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=usage_export_{timestamp}.csv"},
    )


# ── Settings ────────────────────────────────────────
@router.get("/admin/settings")
async def get_admin_settings(admin: dict = Depends(require_admin)):
    db = get_firestore()
    doc = db.collection("admin_settings").document("config").get()
    current = doc.to_dict() if doc.exists else {"default_model": "gemini-2.5-flash"}
    return {"settings": current, "available_models": AVAILABLE_MODELS}


@router.put("/admin/settings")
async def update_admin_settings(body: AdminSettings, admin: dict = Depends(require_admin)):
    db = get_firestore()
    db.collection("admin_settings").document("config").set(
        {"default_model": body.default_model}, merge=True
    )
    return {"status": "updated", "default_model": body.default_model}
