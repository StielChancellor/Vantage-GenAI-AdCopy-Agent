import io
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status

from backend.app.core.auth import require_admin
from backend.app.core.database import get_firestore, get_chroma
from backend.app.core.auth import hash_password
from backend.app.models.schemas import UserCreate, UserOut, CSVUploadResponse, BrandUSP
from backend.app.services.csv_ingestion import ingest_historical_csv, ingest_brand_usp_csv

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
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


@router.get("/admin/usage-stats")
async def get_usage_stats(admin: dict = Depends(require_admin)):
    db = get_firestore()
    logs = list(db.collection("audit_logs").stream())

    stats = {}
    for log in logs:
        data = log.to_dict()
        email = data.get("user_email", "unknown")
        if email not in stats:
            stats[email] = {"total_tokens": 0, "login_count": 0, "generations": 0}
        if data.get("action") == "login":
            stats[email]["login_count"] += 1
        if data.get("action") == "generate":
            stats[email]["generations"] += 1
            stats[email]["total_tokens"] += data.get("tokens_consumed", 0)

    return stats
