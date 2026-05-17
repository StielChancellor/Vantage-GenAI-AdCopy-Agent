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
    """One row of access granted to a user.

    v2.4 — extended scopes:
      - 'brand'  → brand_id required. brand_only=True restricts user to brand-level ops only.
      - 'hotel'  → hotel_id required.
      - 'city'   → city required (free-text, matches hotels.city).
      - 'group'  → no extra fields. Grants admin-equivalent access (every brand + hotel + Club ITC).
    """
    scope: Literal["brand", "hotel", "city", "group"]
    brand_id: Optional[str] = None
    hotel_id: Optional[str] = None
    city: Optional[str] = None
    brand_only: bool = False           # only valid on scope='brand' rows
    granted_at: Optional[str] = None

    @field_validator("hotel_id")
    @classmethod
    def _exactly_one(cls, v, info):
        # When scope is 'hotel', hotel_id required; for 'brand', brand_id is required (checked at the model level by the API).
        return v


class ScopeSummary(BaseModel):
    """Denormalized summary for fast UI listing: '3 brands · 14 hotels · 2 cities'."""
    brand_count: int = 0
    hotel_count: int = 0
    city_count: int = 0
    has_group: bool = False
    has_loyalty: bool = False        # true if user has access to Club ITC (loyalty brand)
    brand_names: list[str] = []      # first 3 for chip display
    hotel_names: list[str] = []      # first 3 for chip display
    city_names: list[str] = []
    # Pre-resolved hotel_ids the user can see across every assignment (capped at 200 for chip listing).
    hotel_ids: list[str] = []


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

    @field_validator("assignments")
    @classmethod
    def _validate_assignment_combos(cls, v: list[ScopeAssignment]):
        """Per-row sanity checks. Cross-row checks (e.g. 'group must stand alone',
        'hotel_marketing_manager has exactly 1 hotel') happen in admin.py since
        they need access to other fields (role)."""
        for a in v:
            if a.scope == "brand" and not a.brand_id:
                raise ValueError("scope='brand' requires brand_id")
            if a.scope == "hotel" and not a.hotel_id:
                raise ValueError("scope='hotel' requires hotel_id")
            if a.scope == "city" and not (a.city or "").strip():
                raise ValueError("scope='city' requires non-empty city")
            if a.brand_only and a.scope != "brand":
                raise ValueError("brand_only is valid only on scope='brand' rows")
        # Group must stand alone (it implies everything).
        if any(a.scope == "group" for a in v) and len(v) > 1:
            raise ValueError("scope='group' must be the sole assignment")
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
    """Structured output of the IntelligentPropertyPicker / cascading PropertySwitcher.

    v2.4 — extended to multi-select brand_ids/cities and loyalty mode:
      scope='hotel'   → single hotel ad; brand_id denormed for retrieval filtering.
      scope='brand'   → brand-level ad; backend pulls anonymized hotel exemplars.
      scope='multi'   → set of hotels and/or brands and/or cities; generation_mode controls fan-out.
      scope='city'    → all hotels in city/cities; behaves like multi with derived hotel_ids.
      scope='loyalty' → loyalty brand (e.g., Club ITC); RAG pulls cross-brand anonymized exemplars.
    """
    scope: Literal["hotel", "brand", "multi", "city", "loyalty"] = "hotel"
    hotel_id: Optional[str] = None
    brand_id: Optional[str] = None
    hotel_ids: list[str] = []
    brand_ids: list[str] = []
    cities: list[str] = []
    is_loyalty: bool = False
    generation_mode: Optional[str] = None   # 'unified' | 'per_hotel' for multi-scope


# ── Hotel & Brand catalog (v2.2) ─────────────────────
class HotelIngestRow(BaseModel):
    """One row of the hotels-ingestion CSV (admin-only)."""
    hotel_name: str
    hotel_code: str           # unique business key — never sent to the model
    brand_name: str           # used for hierarchy + permissions, never sent to the model
    city: Optional[str] = ""             # v2.4 — used for city-level scope; sent to the model as context
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
    city: Optional[str] = ""
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
    kind: str = "hotel"               # v2.4 — 'hotel' | 'loyalty'. Loyalty brands like Club ITC sort to top of pickers.
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


# ── Unified Campaigns (v2.6) ──────────────────────────
class UnifiedCampaignBrief(BaseModel):
    """Step-1 input — the user's free-form brief + any reference URLs.
    The brief can mention campaign name / dates / inclusions / promo /
    target audience in any order; the structurer normalises it."""
    raw_brief: str
    reference_urls: list[str] = []


class StructuredHotel(BaseModel):
    hotel_id: Optional[str] = None
    hotel_name: str


class StructuredCampaign(BaseModel):
    """Step-2 output of the Gemini structurer; user-editable in the
    finalization page. campaign_name is the only required field — every
    other slot is best-effort."""
    campaign_name: str
    start_date: Optional[str] = ""
    end_date: Optional[str] = ""
    booking_window_start: Optional[str] = ""
    booking_window_end: Optional[str] = ""
    cancellation_policy: Optional[str] = ""
    inclusions: Optional[str] = ""
    promo_code: Optional[str] = ""
    landing_page_url: Optional[str] = ""
    participating_hotels: list[StructuredHotel] = []
    brand_ids: list[str] = []
    cities: list[str] = []
    target_audience: Optional[str] = ""
    summary: Optional[str] = ""


class UnifiedCampaignSelection(BaseModel):
    """Step-4 selection — extends PropertySelection with campaign-level
    + channel choices for the orchestrator's fan-out."""
    scope: Literal["hotel", "brand", "multi", "city", "loyalty"] = "multi"
    hotel_id: Optional[str] = None
    brand_id: Optional[str] = None
    hotel_ids: list[str] = []
    brand_ids: list[str] = []
    cities: list[str] = []
    is_loyalty: bool = False
    # 'chain' = brand-level ad; 'single' = per-property ad; 'chain_plus_single' = both.
    campaign_levels: list[str] = ["single"]
    # Channels supported in v2.6: app_push (CRM), search_ads (Google Search), meta_ads (FB).
    channels: list[str] = ["search_ads"]


class UnifiedCampaign(BaseModel):
    """Returned by GETs. Status flow: draft → locked → archived."""
    id: str
    user_id: str = ""
    user_email: str = ""
    campaign_id: Optional[str] = None          # v2.9 — 5-char human-visible id
    ideation_id: Optional[str] = None          # v2.9 — set when promoted from an ideation
    status: Literal["draft", "locked", "archived"] = "draft"
    raw_brief: str = ""
    reference_urls: list[str] = []
    structured: Optional[StructuredCampaign] = None
    events: list[dict] = []
    selection: Optional[UnifiedCampaignSelection] = None
    generated: list[dict] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    locked_at: Optional[str] = None


class CampaignPatchRequest(BaseModel):
    """Partial update for a draft campaign. Server-side rejects writes
    that touch fields once status='locked' — caller must POST /unlock first."""
    structured: Optional[StructuredCampaign] = None
    reference_urls: Optional[list[str]] = None
    events: Optional[list[dict]] = None
    selection: Optional[UnifiedCampaignSelection] = None


class CampaignGenerateRequest(BaseModel):
    """Triggered from step 5. The selection here can override the one
    persisted on the campaign (so the user can re-shoot with different
    properties / channels without editing the locked brief)."""
    selection: Optional[UnifiedCampaignSelection] = None


class CampaignResultRow(BaseModel):
    label: str                 # entity display label (hotel/brand/city/Club ITC)
    scope: str                 # 'hotel' | 'brand' | 'loyalty' | 'city'
    channel: str               # 'app_push' | 'search_ads' | 'meta_ads'
    level: str                 # 'chain' | 'single'
    variants: list[dict] = []  # raw AdCopyOutput / CRMContentOutput dicts
    tokens_used: int = 0
    model_used: str = ""
    time_seconds: float = 0.0
    error: Optional[str] = None


class CampaignGenerateResponse(BaseModel):
    campaign_id: str
    results: list[CampaignResultRow] = []
    total_tokens: int = 0
    total_cost_inr: float = 0.0
    time_seconds: float = 0.0


# ── Campaign Ideation (v2.7) ──────────────────────────
# Upstream tool that produces a 10-item shortlist of campaign concepts from a
# free-text theme + critique chat, grounded in past static creative trained
# via the `creative_assets` adapter. Selecting one shortlist item creates a
# draft `unified_campaigns` doc so the user continues into lock → fan-out.

class IdeationStartRequest(BaseModel):
    theme_text: str
    date_start: Optional[str] = ""
    date_end: Optional[str] = ""
    selection: PropertySelection


class IdeationAnswerRequest(BaseModel):
    answer_text: str


class CritiqueTurn(BaseModel):
    q: str
    a: str = ""
    ts: Optional[str] = None


class ShortlistItem(BaseModel):
    name: str                                  # ≤ 8 words
    tagline: str                               # ≤ 12 words
    story_line: str                            # 2–4 sentences
    visual_direction: str                      # prompt-ready paragraph
    inspiration_asset_ids: list[str] = []      # not surfaced in Phase 1 UI


class IdeationState(BaseModel):
    id: str
    user_id: str = ""
    user_email: str = ""
    selection: Optional[PropertySelection] = None
    theme_text: str = ""
    date_start: Optional[str] = ""
    date_end: Optional[str] = ""
    phase: Literal["critique", "shortlist", "chosen", "archived"] = "critique"
    critique_turns: list[CritiqueTurn] = []
    captured: dict = {}                        # {audience, hero_offer, tone, must_mention, must_avoid, ...}
    shortlist: list[ShortlistItem] = []
    chosen_index: Optional[int] = None
    linked_campaign_id: Optional[str] = None
    app_version: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class IdeationStartResponse(BaseModel):
    ideation_id: str
    next_question: str
    ready_for_shortlist: bool = False


class IdeationAnswerResponse(BaseModel):
    next_question: Optional[str] = None
    ready_for_shortlist: bool = False
    captured: dict = {}


class IdeationShortlistResponse(BaseModel):
    shortlist: list[ShortlistItem]
    tokens_used: int = 0
    model_used: str = ""


class IdeationChooseRequest(BaseModel):
    index: int


class IdeationChooseResponse(BaseModel):
    ideation_id: str
    chosen_index: int
    unified_campaign_id: str


# ── Creative Assets (training corpus for ideation) ────
class CreativeAssetRecord(BaseModel):
    id: str
    brand_id: str
    hotel_id: Optional[str] = None
    pack_id: str
    image_filename: str
    gcs_path: str
    signed_url: Optional[str] = None           # populated on read only
    campaign_name: Optional[str] = ""
    season: Optional[str] = ""
    theme: Optional[str] = ""
    date_start: Optional[str] = ""
    date_end: Optional[str] = ""
    headline: str = ""
    body: str = ""
    cta: Optional[str] = ""
    platform: Optional[str] = ""
    persona: Optional[str] = ""
    hero_offer: Optional[str] = ""
    caption_json: dict = {}
    embedding_id: Optional[str] = ""
    ingested_by: Optional[str] = ""
    ingested_at: Optional[str] = ""


class CreativePackUploadResponse(BaseModel):
    run_id: str
    pack_id: str
    brand_id: str
    images_found: int
    rows_in_manifest: int
    status: str                                # "started" | "completed" | "failed"


# ── Campaign Ideation v2.8 (Form → Directions → Final 10 → Handoff) ────
# Supersedes the v2.7 chat-coach flow. Old IdeationStartRequest /
# IdeationAnswerRequest / IdeationState above stay for in-progress
# v2.7 ideations on phase ∈ {critique, shortlist}.

class IdeationDiscount(BaseModel):
    """Structured discount field on the Step-1 brief.

    v2.9 — `notes` is the human-readable rephrasing produced by the discount
    resolver (e.g. "Rs.3000 off + complimentary spa credit"). Used in the
    brief composer + Final 10 exports."""
    kind: Literal["percent_off", "flat_amount", "bogo", "free_upgrade", "no_discount"] = "no_discount"
    value: str = ""                            # free-text value when kind needs it
    notes: str = ""                            # v2.9 — canonical, human-readable rephrasing


class ResolveDiscountRequest(BaseModel):
    phrase: str


class ResolveDiscountResponse(BaseModel):
    kind: Literal["percent_off", "flat_amount", "bogo", "free_upgrade", "no_discount"] = "no_discount"
    value: str = ""
    notes: str = ""


class IdeationHotelsResolution(BaseModel):
    """How the marketer told us which properties participate.
    mode='list' uses IntelligentPropertyPicker output (hotel_ids/brand_ids).
    mode='phrase' captures the natural-language string PLUS the LLM-resolved ids."""
    mode: Literal["list", "phrase"] = "list"
    phrase: Optional[str] = ""
    resolved_hotel_ids: list[str] = []
    resolved_brand_ids: list[str] = []
    is_loyalty: bool = False


class IdeationInputs(BaseModel):
    """Step-1 form payload. The single structured input the v2.8 generator reads."""
    offer_name: str
    inclusions: str = ""
    discount: IdeationDiscount = IdeationDiscount()
    hotels_resolution: IdeationHotelsResolution
    audience_axis: Literal["business", "in_between", "leisure"] = "in_between"
    tone_axis: Literal["tactical", "hybrid", "aspirational"] = "hybrid"


class ResolvedHotelRef(BaseModel):
    hotel_id: str
    name: str
    brand: Optional[str] = ""
    brand_id: Optional[str] = ""
    city: Optional[str] = ""


class ResolveHotelsRequest(BaseModel):
    phrase: str


class ResolveHotelsResponse(BaseModel):
    matched: list[ResolvedHotelRef] = []
    resolved_hotel_ids: list[str] = []
    resolved_brand_ids: list[str] = []
    is_loyalty: bool = False
    notes: Optional[str] = ""                  # model's reasoning, surfaced as a sub-label


class IdeationStartV2Request(BaseModel):
    inputs: IdeationInputs


class IdeationStartV2Response(BaseModel):
    ideation_id: str
    campaign_id: Optional[str] = None          # v2.9 — 5-char human-visible id


class IdeationVisualCue(BaseModel):
    palette: list[str] = []                    # short tokens, e.g. "mist", "ochre"
    motifs: list[str] = []
    photography_style: str = ""
    mood: str = ""
    logo_placement: str = ""


class IdeationDirectionConcept(BaseModel):
    id: str                                    # stable across this directions batch, used as seed reference
    name: str                                  # ≤ 8 words
    justification: str                         # 1 line


class IdeationDirection(BaseModel):
    id: str                                    # e.g. "dir_aspirational_stillness"
    title: str                                 # e.g. "Aspirational — Mountain Stillness"
    rationale: str                             # 1 sentence
    visual_cue: IdeationVisualCue
    concepts: list[IdeationDirectionConcept]   # exactly 5 per direction


class IdeationDirectionsResponse(BaseModel):
    iteration: int                              # 1-based; increments per /directions or /refine call
    directions: list[IdeationDirection]        # 3–5 entries
    tokens_used: int = 0
    model_used: str = ""


class IdeationRefineRequest(BaseModel):
    selected_direction_id: Optional[str] = None
    selected_concept_ids: list[str] = []
    freetext_steer: str = ""


class IdeationFinalConcept(BaseModel):
    id: str                                    # stable across the final batch
    name: str
    justification: str                         # one-line subhead
    story_line: str = ""                       # v2.9 — 2–3 sentence narrative; used in card expand + exports
    visual_cue: IdeationVisualCue
    inspiration_asset_ids: list[str] = []      # reserved for Phase-3 moodboard


class IdeationFinalizeRequest(BaseModel):
    """Empty body = first finalize call. seed_concept_ids + freetext_steer
    on subsequent calls produce a fresh batch of 10 (merge semantic)."""
    seed_concept_ids: list[str] = []
    freetext_steer: str = ""


class IdeationFinalResponse(BaseModel):
    iteration: int                             # bumped per /finalize call
    concepts: list[IdeationFinalConcept]       # exactly 10
    tokens_used: int = 0
    model_used: str = ""


class IdeationIterationRecord(BaseModel):
    """One entry in the persisted iterations history."""
    idx: int
    kind: Literal["directions", "final"]
    directions: list[IdeationDirection] = []
    final: list[IdeationFinalConcept] = []
    seed_direction_id: Optional[str] = None
    seed_concept_ids: list[str] = []
    freetext_steer: str = ""
    created_at: Optional[str] = None


class IdeationStateV2(BaseModel):
    """Full state document for a v2.8/v2.9 ideation. Loaded by GET /ideation/{id}."""
    id: str
    user_id: str = ""
    user_email: str = ""
    schema_version: int = 2                    # 1 = legacy v2.7, 2 = v2.8/2.9
    campaign_id: Optional[str] = None          # v2.9 — 5-char human-visible id
    phase: Literal["inputs", "directions", "refining", "final", "chosen", "archived"] = "inputs"
    inputs: Optional[IdeationInputs] = None
    selection: Optional[PropertySelection] = None
    iterations: list[IdeationIterationRecord] = []
    chosen_final_index: Optional[int] = None
    linked_campaign_id: Optional[str] = None
    app_version: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ── v2.9 Past Briefs + Ideated Campaigns landing rows ──────────────

class PastBrief(BaseModel):
    """One row on the Unified Campaign landing page (Past Briefs section)."""
    id: str                                    # Firestore doc id
    campaign_id: Optional[str] = None          # 5-char human id (may be empty for legacy docs)
    campaign_name: str = ""                    # from structured.campaign_name
    status: str = "draft"                      # draft | locked | archived
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    locked_at: Optional[str] = None


class IdeatedCampaignRow(BaseModel):
    """One row on the Unified Campaign landing page (Ideated Campaigns section)."""
    id: str                                    # Firestore doc id of the ideation
    campaign_id: Optional[str] = None
    offer_name: str = ""
    phase: str = "inputs"
    is_loyalty: bool = False
    hotel_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
