import io
import csv
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse

from backend.app.core.auth import require_admin
from backend.app.core.database import get_firestore
from backend.app.core.auth import hash_password
from backend.app.models.schemas import UserCreate, UserOut, CSVUploadResponse, BrandUSP, AdminSettings
from backend.app.services.csv_ingestion import ingest_historical_csv, ingest_brand_usp_csv

AVAILABLE_MODELS = [
    {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
    {"id": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash Lite"},
    {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
    {"id": "gemini-2.0-flash-lite", "label": "Gemini 2.0 Flash Lite"},
]

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


# ── User Management ──────────────────────────────────
@router.post("/admin/users", response_model=UserOut)
async def create_user(body: UserCreate, admin: dict = Depends(require_admin)):
    db = get_firestore()

    # Check duplicate
    existing = list(
        db.collection("users").where("email", "==", body.email).limit(1).stream()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_doc = {
        "full_name": body.full_name,
        "email": body.email,
        "password_hash": hash_password(body.password),
        "role": body.role,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": admin["sub"],
    }
    _, ref = db.collection("users").add(user_doc)

    return UserOut(
        uid=ref.id,
        full_name=body.full_name,
        email=body.email,
        role=body.role,
        created_at=user_doc["created_at"],
    )


@router.get("/admin/users", response_model=list[UserOut])
async def list_users(admin: dict = Depends(require_admin)):
    db = get_firestore()
    docs = db.collection("users").stream()
    return [
        UserOut(
            uid=doc.id,
            full_name=doc.to_dict()["full_name"],
            email=doc.to_dict()["email"],
            role=doc.to_dict()["role"],
            created_at=doc.to_dict().get("created_at"),
        )
        for doc in docs
    ]


@router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    db = get_firestore()
    doc_ref = db.collection("users").document(user_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    doc_ref.delete()
    return {"message": "User deleted"}


@router.put("/admin/users/{user_id}", response_model=UserOut)
async def update_user(user_id: str, body: UserCreate, admin: dict = Depends(require_admin)):
    db = get_firestore()
    doc_ref = db.collection("users").document(user_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = {
        "full_name": body.full_name,
        "email": body.email,
        "role": body.role,
    }
    if body.password:
        update_data["password_hash"] = hash_password(body.password)

    doc_ref.update(update_data)
    updated = doc_ref.get().to_dict()
    return UserOut(
        uid=user_id,
        full_name=updated["full_name"],
        email=updated["email"],
        role=updated["role"],
        created_at=updated.get("created_at"),
    )


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
