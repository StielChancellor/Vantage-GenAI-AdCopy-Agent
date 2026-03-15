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


# ── Context Selector ─────────────────────────────────
class ContextSelector(BaseModel):
    context_type: str = "single_property"  # single_property | multi_property | destination | brand_hq
    property_names: list[str] = []
    destination_name: Optional[str] = ""
    generation_mode: Optional[str] = None  # "unified" | "per_property" (multi/hq only)


# ── Ad Generation ────────────────────────────────────
class AdGenerationRequest(BaseModel):
    context: Optional[ContextSelector] = None
    hotel_name: str = ""  # Backward compat — derived from context
    offer_name: str
    inclusions: str
    reference_urls: list[str]
    google_listing_url: Optional[str] = ""
    google_listing_urls: list[str] = []
    other_info: Optional[str] = ""
    campaign_objective: Optional[str] = ""
    platforms: list[str] = ["google_search"]
    carousel_mode: Optional[str] = "suggest"
    carousel_cards: Optional[list[str]] = None


class AdCopyOutput(BaseModel):
    platform: str
    headlines: list[str]
    descriptions: list[str]
    captions: Optional[list[str]] = None
    card_suggestions: Optional[list[str]] = None


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
    tokens_used: int
    input_tokens: int = 0
    output_tokens: int = 0
    model_used: str
    time_seconds: float
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


# ── Training (Phase 2.1 — Revised) ──────────────────
class TrainingUploadResponse(BaseModel):
    session_id: str
    status: str  # "questions_pending" | "ready_for_approval" | "approved" | "error"
    questions: list[dict] = []
    directive_preview: Optional[dict] = None


class TrainingAnswerRequest(BaseModel):
    session_id: str
    answers: list[dict]  # [{question_id: int, answer: str}]
    approve: bool = False
    save_mode: Optional[str] = None  # "append" | "replace" (only when approve=True)


class TrainingSessionLog(BaseModel):
    session_id: str
    section_type: str  # "ad_performance" | "brand_usp" | "crm_performance"
    training_mode: str  # "csv_only" | "text_only" | "csv_and_text"
    status: str  # "pending" | "approved" | "rejected"
    save_mode: Optional[str] = None  # "append" | "replace"
    input_tokens: int = 0
    output_tokens: int = 0
    time_seconds: float = 0.0
    cost_inr: float = 0.0
    created_at: str = ""
    completed_at: Optional[str] = None


# ── CRM (Phase 2.1 — Revised) ───────────────────────
class CRMGenerateRequest(BaseModel):
    context: Optional[ContextSelector] = None
    hotel_name: str = ""  # Backward compat
    channels: list[str]  # "whatsapp" | "email" | "app_push"
    campaign_type: str
    target_audience: str
    offer_details: str
    tone: str = "luxurious"
    events: list[dict] = []
    schedule_start: str = ""
    schedule_end: str = ""
    channel_frequencies: dict = {}  # {channel: {days, every_n_weeks, duration_weeks, custom_pattern}}
    frequency: str = "weekly"  # Fallback if channel_frequencies empty
    inclusions: str = ""
    other_info: str = ""
    reference_urls: list[str] = []
    google_listing_urls: list[str] = []


class CRMContentOutput(BaseModel):
    channel: str
    messages: list[dict]  # [{headline?, subject?, body, cta, char_count}]
    warnings: list[str] = []


class CRMGenerateResponse(BaseModel):
    hotel_name: str
    content: list[CRMContentOutput]
    calendar: list[dict]  # [{day, date, time_range, channel, headline, body, subject, cta, message_preview}]
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
    markets: list[str] = ["India"]
    date_range_start: str = ""
    date_range_end: str = ""
    categories: list[str] = []


class EventResult(BaseModel):
    title: str
    date: str
    description: str
    source: str
    market: str
    relevance_score: float = 0.0
