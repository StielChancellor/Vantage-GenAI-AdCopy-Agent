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


# ── Training ────────────────────────────────────────
class TrainingUploadResponse(BaseModel):
    session_id: str
    status: str  # "questions_pending" | "approved" | "error"
    questions: list[dict] = []  # [{question: str, options: list[str], default: str}]
    directive_preview: Optional[dict] = None


class TrainingAnswerRequest(BaseModel):
    session_id: str
    answers: list[dict]  # [{question_id: int, answer: str}]
    approve: bool = False  # If True, finalize and save


# ── CRM ─────────────────────────────────────────────
class CRMGenerateRequest(BaseModel):
    hotel_name: str
    channels: list[str]  # "whatsapp" | "email" | "app_push"
    campaign_type: str  # "promotional" | "seasonal" | "event" | "loyalty" | "re-engagement"
    target_audience: str
    offer_details: str
    tone: str = "luxurious"  # "formal" | "casual" | "urgent" | "luxurious"
    events: list[dict] = []  # [{title, date, source, market}]
    schedule_start: str = ""  # ISO date
    schedule_end: str = ""  # ISO date
    frequency: str = "weekly"  # "daily" | "weekly" | "biweekly" | "monthly"
    inclusions: str = ""
    other_info: str = ""
    reference_urls: list[str] = []
    google_listing_urls: list[str] = []


class CRMContentOutput(BaseModel):
    channel: str
    messages: list[dict]  # [{subject?: str, body: str, cta: str, char_count: int}]
    warnings: list[str] = []  # Soft/strict limit warnings


class CRMGenerateResponse(BaseModel):
    hotel_name: str
    content: list[CRMContentOutput]
    calendar: list[dict]  # [{day, date, time_range, channel, message_preview}]
    tokens_used: int
    input_tokens: int = 0
    output_tokens: int = 0
    model_used: str
    time_seconds: float


class CRMRefineRequest(BaseModel):
    hotel_name: str
    channels: list[str]
    previous_content: list[CRMContentOutput]
    previous_calendar: list[dict]
    feedback: str


# ── Events ──────────────────────────────────────────
class EventSearchRequest(BaseModel):
    markets: list[str] = ["India"]  # Default India + user additions
    date_range_start: str = ""
    date_range_end: str = ""
    categories: list[str] = []  # "festivals" | "sports" | "conferences" | "holidays"


class EventResult(BaseModel):
    title: str
    date: str
    description: str
    source: str
    market: str
    relevance_score: float = 0.0
