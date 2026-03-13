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
    return UserOut(
        uid=current_user["uid"],
        full_name=current_user["name"],
        email=current_user["sub"],
        role=current_user["role"],
    )
