import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status, Depends

from backend.app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
from backend.app.core.database import get_firestore
from backend.app.models.schemas import UserLogin, TokenResponse, UserOut

router = APIRouter()


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: UserLogin):
    db = get_firestore()
    users_ref = db.collection("users").where("email", "==", body.email).limit(1)
    docs = list(users_ref.stream())

    if not docs:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_data = docs[0].to_dict()
    if not verify_password(body.password, user_data["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Create session and log login
    session_id = str(uuid.uuid4())
    token = create_access_token(
        {
            "sub": user_data["email"],
            "role": user_data["role"],
            "name": user_data["full_name"],
            "uid": docs[0].id,
            "session_id": session_id,
        }
    )

    # Audit: log login
    db.collection("audit_logs").add(
        {
            "user_email": user_data["email"],
            "action": "login",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
        }
    )

    return TokenResponse(
        access_token=token,
        user=UserOut(
            uid=docs[0].id,
            full_name=user_data["full_name"],
            email=user_data["email"],
            role=user_data["role"],
            created_at=user_data.get("created_at"),
        ),
    )


@router.post("/auth/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    db = get_firestore()
    db.collection("audit_logs").add(
        {
            "user_email": current_user["sub"],
            "action": "logout",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": current_user.get("session_id"),
        }
    )
    return {"message": "Logged out"}


@router.get("/auth/me", response_model=UserOut)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Hydrate the JWT into a full UserOut by reading the live Firestore doc.
    The JWT carries minimal data (sub, uid, role); show_token_count, show_token_amount,
    and scope_summary live on the user doc and are needed by My Account."""
    db = get_firestore()
    uid = current_user.get("uid", "")
    data = {}
    if uid:
        d = db.collection("users").document(uid).get()
        if d.exists:
            data = d.to_dict() or {}

    # Build a scope_summary from property_assignments so the frontend can chip it.
    from backend.app.routers.admin import _user_to_out
    fallback_data = {
        "full_name": current_user.get("name", ""),
        "email": current_user.get("sub", ""),
        "role": current_user.get("role", "user"),
    }
    try:
        out = _user_to_out(uid, data or fallback_data)
        # v2.5 — admins always see their own token visibility, even if the per-user
        # flags happen to be off. This keeps the My Account billing table populated.
        if (out.role or "").lower() == "admin":
            out.show_token_count = True
            out.show_token_amount = True
        return out
    except Exception as exc:  # noqa: BLE001
        # Never let scope-summary errors break /auth/me.
        from backend.app.models.schemas import UserOut, ScopeSummary
        d = data or fallback_data
        is_admin = (d.get("role") or "").lower() == "admin"
        return UserOut(
            uid=uid,
            full_name=d.get("full_name", ""),
            email=d.get("email", ""),
            role=d.get("role", "user"),
            show_token_count=is_admin or bool(d.get("show_token_count", False)),
            show_token_amount=is_admin or bool(d.get("show_token_amount", False)),
            scope_summary=ScopeSummary(),
            created_at=d.get("created_at"),
        )


@router.get("/auth/me/billing")
async def get_my_billing(current_user: dict = Depends(get_current_user)):
    """Per-user billing summary, gated by show_token_count/show_token_amount.
    Returns redacted "—" markers for users whose admin disabled visibility.

    v2.5 — admins always see their own consumption regardless of the per-user
    flags (the flags are intended to gate non-admin reports, not the admin's
    own usage view)."""
    db = get_firestore()
    uid = current_user.get("uid", "")
    user_doc = db.collection("users").document(uid).get() if uid else None
    user_data = (user_doc.to_dict() or {}) if (user_doc and user_doc.exists) else {}
    is_admin = current_user.get("role") == "admin"
    show_count = is_admin or bool(user_data.get("show_token_count", False))
    show_amount = is_admin or bool(user_data.get("show_token_amount", False))

    rows = []
    total_tokens = 0
    total_cost = 0.0
    # Try ordered query first (needs a composite index in production); fall back
    # to unordered + in-memory sort if the index is missing.
    try:
        stream = (
            db.collection("audit_logs")
            .where("user_email", "==", current_user.get("sub", ""))
            .order_by("timestamp", direction="DESCENDING")
            .limit(200)
            .stream()
        )
        docs = list(stream)
    except Exception:  # noqa: BLE001
        docs = list(
            db.collection("audit_logs")
            .where("user_email", "==", current_user.get("sub", ""))
            .limit(500)
            .stream()
        )
        docs.sort(key=lambda d: (d.to_dict() or {}).get("timestamp", ""), reverse=True)
        docs = docs[:200]

    for d in docs:
        data = d.to_dict() or {}
        if data.get("action") not in ("generate", "refine"):
            continue
        tokens = int(data.get("tokens_consumed", 0))
        cost = float(data.get("cost_inr", 0))
        total_tokens += tokens
        total_cost += cost
        rows.append({
            "id": d.id,
            "timestamp": data.get("timestamp", ""),
            "hotel_name": data.get("hotel_name", ""),
            "offer_name": data.get("offer_name", ""),
            "platforms": data.get("platforms", []),
            "tokens": tokens if show_count else None,
            "cost_inr": round(cost, 4) if show_amount else None,
            "model_used": data.get("model_used", ""),
            "generation_id": data.get("generation_id", ""),
        })

    return {
        "show_token_count": show_count,
        "show_token_amount": show_amount,
        "total_tokens": total_tokens if show_count else None,
        "total_cost_inr": round(total_cost, 4) if show_amount else None,
        "rows": rows,
    }
