from pydantic import BaseModel, Field
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
    reference_urls: list[str]  # Multiple URLs supported
    google_listing_url: Optional[str] = ""  # Backward compat
    google_listing_urls: list[str] = []  # Multiple Google listing URLs
    other_info: Optional[str] = ""
    campaign_objective: Optional[str] = ""  # Awareness | Consideration | Conversion | ""
    platforms: list[str] = ["google_search"]
    # Carousel card configuration
    carousel_mode: Optional[str] = "suggest"  # "suggest" or "manual"
    carousel_cards: Optional[list[str]] = None  # User-provided card descriptions


class AdCopyOutput(BaseModel):
    platform: str
    headlines: list[str]
    descriptions: list[str]
    captions: Optional[list[str]] = None
    card_suggestions: Optional[list[str]] = None  # AI-suggested card visual descriptions


class AdGenerationResponse(BaseModel):
    hotel_name: str
    variants: list[AdCopyOutput]
    tokens_used: int
    input_tokens: int = 0
    output_tokens: int = 0
    model_used: str
    time_seconds: float
    generated_at: str


# ── Ad Refinement ───────────────────────────────────
class AdRefinementRequest(BaseModel):
    hotel_name: str
    offer_name: str
    inclusions: str
    platforms: list[str]
    campaign_objective: Optional[str] = ""
    other_info: Optional[str] = ""
    previous_variants: list[AdCopyOutput]
    feedback: str
    accumulated_tokens: int = 0
    accumulated_time: float = 0.0


class AdRefinementResponse(BaseModel):
    hotel_name: str
    variants: list[AdCopyOutput]
    tokens_used: int  # Total accumulated
    input_tokens: int = 0  # This call only
    output_tokens: int = 0  # This call only
    model_used: str
    time_seconds: float  # Total accumulated
    generated_at: str
    refinement_count: int = 1


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


# ── Admin Settings ───────────────────────────────────
class AdminSettings(BaseModel):
    default_model: str = "gemini-2.5-flash"


# ── Audit Log ────────────────────────────────────────
class AuditLogEntry(BaseModel):
    user_email: str
    action: str
    inputs: Optional[dict] = None
    tokens_consumed: int = 0
    timestamp: str
    session_id: Optional[str] = None
