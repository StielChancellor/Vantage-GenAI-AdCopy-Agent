from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime


# ── Auth & RBAC (v2.2 — 5-tier hierarchy) ────────────
ROLES = (
    "admin",                    # everything
    "brand_manager",            # brand + all hotels under brand
    "area_manager",             # multiple hotels (no brand-level)
    "hotel_marketing_manager",  # exactly one hotel
    "agency",                   # brands + multiple hotels
    "user",                     # legacy (still accepted, treated as area_manager-equivalent for backward compat)
)


class ScopeAssignment(BaseModel):
    """One row of access granted to a user. Either brand-scope OR hotel-scope, not both."""
    scope: Literal["brand", "hotel"]
    brand_id: Optional[str] = None
    hotel_id: Optional[str] = None

    @field_validator("hotel_id")
    @classmethod
    def _exactly_one(cls, v, info):
        # When scope is 'hotel', hotel_id required; for 'brand', brand_id is required (checked at the model level by the API).
        return v


class ScopeSummary(BaseModel):
    """Denormalized summary for fast UI listing: '3 brands · 14 hotels'."""
    brand_count: int = 0
    hotel_count: int = 0
    brand_names: list[str] = []      # first 3 for chip display
    hotel_names: list[str] = []      # first 3 for chip display


class UserCreate(BaseModel):
    full_name: str
    email: str
    password: str = Field(min_length=8)
    role: str = "user"
    show_token_count: bool = False
    show_token_amount: bool = False
    assignments: list[ScopeAssignment] = []   # admin-only roles ignore this

    @field_validator("role")
    @classmethod
    def _valid_role(cls, v):
        if v not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        return v


class UserLogin(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    uid: str
    full_name: str
    email: str
    role: str
    show_token_count: bool = False
    show_token_amount: bool = False
    scope_summary: Optional[ScopeSummary] = None
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


# ── v2.2 Property Selection (PropertySwitcher output) ─
class PropertySelection(BaseModel):
    """Structured output of the cascading PropertySwitcher.

    scope='hotel' → single hotel ad; brand_id is denormed for retrieval filtering.
    scope='brand' → brand-level ad; backend pulls anonymized hotel exemplars.
    scope='multi' → set of hotels (area_manager / agency); generation_mode controls fan-out.
    """
    scope: Literal["hotel", "brand", "multi"] = "hotel"
    hotel_id: Optional[str] = None
    brand_id: Optional[str] = None
    hotel_ids: list[str] = []
    generation_mode: Optional[str] = None   # 'unified' | 'per_hotel' for multi-scope


# ── Hotel & Brand catalog (v2.2) ─────────────────────
class HotelIngestRow(BaseModel):
    """One row of the hotels-ingestion CSV (admin-only)."""
    hotel_name: str
    hotel_code: str           # unique business key — never sent to the model
    brand_name: str           # used for hierarchy + permissions, never sent to the model
    rooms_count: Optional[int] = None    # SENT to the model so it can write '200-room property'
    fnb_count: Optional[int] = None      # SENT — '3 F&B outlets'
    website_url: Optional[str] = ""
    gmb_url: Optional[str] = ""


class HotelOut(BaseModel):
    hotel_id: str
    hotel_name: str
    hotel_code: str
    brand_id: str
    brand_name: str
    rooms_count: Optional[int] = None
    fnb_count: Optional[int] = None
    website_url: Optional[str] = ""
    gmb_url: Optional[str] = ""
    gmb_place_id: Optional[str] = ""
    status: str = "active"
    last_enriched_at: Optional[str] = None


class BrandOut(BaseModel):
    brand_id: str
    brand_name: str
    slug: str
    hotel_count: int = 0
    voice: Optional[str] = ""
    created_at: Optional[str] = None


class HotelIngestResponse(BaseModel):
    created_brands: int
    created_hotels: int
    updated_hotels: int
    skipped: int = 0
    errors: list[str] = []
    brand_tree: list[dict] = []   # [{brand_name, hotels:[{hotel_name, hotel_code}]}]


# ── Ad Generation ────────────────────────────────────
class AdGenerationRequest(BaseModel):
    context: Optional[ContextSelector] = None         # legacy — kept for backward compat
    selection: Optional[PropertySelection] = None     # v2.2 — preferred
    hotel_name: str = ""                              # backward compat — derived from selection/context
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
    flight_date: Optional[str] = ""


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
    generation_id: Optional[str] = None    # v2.2 — UUID for cross-system trace
    app_version: Optional[str] = None      # v2.2 — server version that produced this


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


# ── Copilot ────────────────────────────────────────
class CopilotMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    brief_snapshot: Optional[dict] = None
    timestamp: Optional[str] = None


class CopilotChatRequest(BaseModel):
    mode: str  # "ad_copy" | "crm"
    messages: list[CopilotMessage]
    current_brief: Optional[dict] = None


class BriefField(BaseModel):
    value: Optional[str] = None
    confidence: str = "missing"  # "confirmed" | "inferred" | "missing"


class CopilotChatResponse(BaseModel):
    message: str
    brief: dict  # {field_name: {value, confidence}}
    ready_to_generate: bool = False
    suggestions: list[str] = []
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    model_used: str = ""


class SavedBrief(BaseModel):
    brief_id: Optional[str] = None
    user_id: str = ""
    mode: str = ""  # "ad_copy" | "crm"
    name: str = ""
    brief: dict = {}
    created_at: Optional[str] = None
