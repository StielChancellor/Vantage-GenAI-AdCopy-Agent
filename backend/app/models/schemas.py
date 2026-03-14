from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


# ── Auth ──────────────────────────────────────────────
class UserCreate(BaseModel):
    full_name: str
    email: str
    password: str = Field(min_length=8)
    role: str = "user"  # "user" | "admin"


class UserLogin(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    uid: str
    full_name: str
    email: str
    role: str
    created_at: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── Ad Generation ────────────────────────────────────
class AdGenerationRequest(BaseModel):
    hotel_name: str
    offer_name: str
    inclusions: str
    reference_url: str
    google_listing_url: str
    other_info: Optional[str] = ""
    campaign_objective: Optional[str] = ""  # Awareness | Consideration | Conversion | ""
    model_name: str = "gemini-2.5-flash"
    platforms: list[str] = ["google_search"]  # google_search, meta_carousel, pmax, youtube


class AdCopyOutput(BaseModel):
    platform: str
    headlines: list[str]
    descriptions: list[str]
    captions: Optional[list[str]] = None


class AdGenerationResponse(BaseModel):
    hotel_name: str
    variants: list[AdCopyOutput]
    tokens_used: int
    model_used: str
    generated_at: str


# ── Brand & USP ──────────────────────────────────────
class BrandUSP(BaseModel):
    hotel_name: str
    usps: list[str]
    positive_keywords: list[str]
    negative_keywords: list[str]
    restricted_keywords: list[str]


# ── CSV Upload ───────────────────────────────────────
class CSVUploadResponse(BaseModel):
    rows_processed: int
    hotels_found: list[str]
    status: str


# ── Audit Log ────────────────────────────────────────
class AuditLogEntry(BaseModel):
    user_email: str
    action: str
    inputs: Optional[dict] = None
    tokens_consumed: int = 0
    timestamp: str
    session_id: Optional[str] = None
