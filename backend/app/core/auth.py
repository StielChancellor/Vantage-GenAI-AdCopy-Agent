from datetime import datetime, timedelta, timezone
from typing import Optional, Iterable

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.core.config import get_settings

settings = get_settings()
security = HTTPBearer()


# Roles known to the system. Order matters for "rank-based" comparisons but is
# generally not used — every check is explicit allowlist-based.
ROLE_ADMIN = "admin"
ROLE_BRAND_MANAGER = "brand_manager"
ROLE_AREA_MANAGER = "area_manager"
ROLE_HOTEL_MM = "hotel_marketing_manager"
ROLE_AGENCY = "agency"
ROLE_LEGACY_USER = "user"   # pre-v2.2 — treat as area_manager-equivalent


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    payload = decode_token(credentials.credentials)
    if payload.get("sub") is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )
    return payload


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return current_user


def require_role(*allowed: str):
    """FastAPI dependency factory: pass any allowed roles, returns a Depends-able guard."""
    allowed_set = set(allowed)

    async def _guard(current_user: dict = Depends(get_current_user)) -> dict:
        role = current_user.get("role", "")
        if role == ROLE_ADMIN or role in allowed_set:
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires one of: {', '.join(sorted(allowed_set))}",
        )

    return _guard


# ──────────────────────────────────────────────────────────────────
# Hotel/Brand access checks — all read assignments from Firestore.
# ──────────────────────────────────────────────────────────────────

def _get_user_assignments(uid: str) -> list[dict]:
    """Return [{scope, brand_id?, hotel_id?}] for the given user. Cached per process."""
    if not uid:
        return []
    cache = _get_user_assignments.__dict__.setdefault("_cache", {})
    if uid in cache:
        return cache[uid]
    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
        docs = list(db.collection("property_assignments").document(uid).collection("items").stream())
        items = [d.to_dict() for d in docs]
        cache[uid] = items
        return items
    except Exception:
        return []


def invalidate_assignment_cache(uid: str) -> None:
    """Call after writing assignments so subsequent requests see fresh data."""
    cache = _get_user_assignments.__dict__.get("_cache", {})
    cache.pop(uid, None)


def has_group_scope(current_user: dict) -> bool:
    """v2.4 — does the user hold a 'group' assignment (admin-equivalent
    access without the admin role itself)?"""
    if current_user.get("role") == ROLE_ADMIN:
        return True
    return any(
        a.get("scope") == "group"
        for a in _get_user_assignments(current_user.get("uid", ""))
    )


def user_can_access_hotel(current_user: dict, hotel_id: str) -> bool:
    """True if the current user is allowed to act on this hotel.

    v2.4 access paths (any one wins):
      - admin role
      - any 'group' assignment
      - direct hotel grant (scope='hotel', hotel_id matches)
      - brand grant (scope='brand', brand matches the hotel's brand_id) UNLESS
        every brand grant on the matching brand has brand_only=True
      - city grant (scope='city', city matches the hotel's city)
    """
    role = current_user.get("role", "")
    if role == ROLE_ADMIN:
        return True
    if not hotel_id:
        return False
    assignments = _get_user_assignments(current_user.get("uid", ""))
    if any(a.get("scope") == "group" for a in assignments):
        return True
    # Direct hotel grant
    for a in assignments:
        if a.get("scope") == "hotel" and a.get("hotel_id") == hotel_id:
            return True
    # Brand / city grants — need the hotel doc to check brand_id and city.
    try:
        from backend.app.core.database import get_firestore
        hotel = get_firestore().collection("hotels").document(hotel_id).get()
        if hotel.exists:
            data = hotel.to_dict() or {}
            brand_id = data.get("brand_id", "")
            hotel_city = (data.get("city") or "").strip()
            if brand_id:
                # A brand grant counts only if it's NOT brand_only (brand_only=True
                # restricts the user to brand-level ops without per-hotel access).
                for a in assignments:
                    if (
                        a.get("scope") == "brand"
                        and a.get("brand_id") == brand_id
                        and not bool(a.get("brand_only"))
                    ):
                        return True
            if hotel_city:
                for a in assignments:
                    if a.get("scope") == "city" and (a.get("city") or "").strip() == hotel_city:
                        return True
    except Exception:
        pass
    return False


def user_can_access_brand(current_user: dict, brand_id: str) -> bool:
    """True if the current user can perform brand-level operations on this brand."""
    role = current_user.get("role", "")
    if role == ROLE_ADMIN:
        return True
    if role == ROLE_HOTEL_MM:
        # Hotel-marketing-manager is explicitly excluded from brand-level ops.
        return False
    if not brand_id:
        return False
    assignments = _get_user_assignments(current_user.get("uid", ""))
    if any(a.get("scope") == "group" for a in assignments):
        return True
    return any(
        a.get("scope") == "brand" and a.get("brand_id") == brand_id for a in assignments
    )


def resolve_user_hotel_ids(current_user: dict) -> Optional[list[str]]:
    """Return the flat hotel-id allowlist this user can see, expanding every
    assignment (brand → all hotels under it; city → all hotels in that city).

    Returns None for admins or users with a 'group' grant — the caller should
    treat None as 'no filtering' (all hotels visible)."""
    if current_user.get("role") == ROLE_ADMIN or has_group_scope(current_user):
        return None
    assignments = _get_user_assignments(current_user.get("uid", ""))
    out: set[str] = set()
    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
        # Direct hotel grants
        for a in assignments:
            if a.get("scope") == "hotel" and a.get("hotel_id"):
                out.add(a["hotel_id"])
        # Brand grants (brand_only=True still grants hotel-level *visibility* in lists,
        # but generation is gated separately in user_can_access_hotel).
        brand_ids = [a["brand_id"] for a in assignments if a.get("scope") == "brand" and a.get("brand_id")]
        for bid in brand_ids:
            for d in db.collection("hotels").where("brand_id", "==", bid).where("status", "==", "active").stream():
                out.add(d.id)
        # City grants
        cities = [(a.get("city") or "").strip() for a in assignments if a.get("scope") == "city"]
        cities = [c for c in cities if c]
        for city in cities:
            for d in db.collection("hotels").where("city", "==", city).where("status", "==", "active").stream():
                out.add(d.id)
    except Exception:
        pass
    return sorted(out)


def resolve_user_brand_ids(current_user: dict) -> Optional[list[str]]:
    """Return the flat brand-id allowlist for this user. None for admin/group."""
    if current_user.get("role") == ROLE_ADMIN or has_group_scope(current_user):
        return None
    assignments = _get_user_assignments(current_user.get("uid", ""))
    out = sorted({a["brand_id"] for a in assignments if a.get("scope") == "brand" and a.get("brand_id")})
    return out


def role_allows_brand_scope(role: str) -> bool:
    """Static check — does this role *ever* grant brand-level access?"""
    return role in (ROLE_ADMIN, ROLE_BRAND_MANAGER, ROLE_AGENCY)


def role_allows_multi_hotel(role: str) -> bool:
    """Static check — does this role allow more than one hotel assignment?"""
    return role in (ROLE_ADMIN, ROLE_BRAND_MANAGER, ROLE_AREA_MANAGER, ROLE_AGENCY)
