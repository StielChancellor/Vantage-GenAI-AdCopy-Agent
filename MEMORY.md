# Vantage GenAI — Memory

A running record of where the project is. Read this first when picking the
work back up. Last updated: 2026-05-07 (App v2.3).

---

## Live deployment

- **URL:** https://vantage-adcopy-agent-yxsestxy7a-uc.a.run.app
- **Health:** `GET /health` → `{"status":"healthy", "version":"2.3", "version_date":"2026-05-07"}`
- **Login:** `admin@vantage.ai` / `Vantage@2025` (admin)
- **Branch:** `custome-HL` on `https://github.com/StielChancellor/Vantage-GenAI-AdCopy-Agent`
- **GCP project:** `supple-moon-495404-b0` (project number 717874273203)
- **Region:** `us-central1` (Cloud Run, BigQuery `US` multi-region, Firestore `nam5`)
- **Model:** `gemini-3.1-pro-preview` via Vertex AI SDK (admin can override per workspace via Firestore `admin_settings/config`)
- **Cost:** Cloud Run min-instance ~$15/mo + Firestore + BQ. Vector Search NOT deployed (saving ~$53/mo); semantic retrieval falls through to Firestore-backed in-process cosine similarity (Option D).

## Version

- Single source of truth: `backend/app/core/version.py` + `frontend/src/version.js` + `frontend/package.json` + `README.md` first lines
- Bumper: `python scripts/bump_version.py 2.4 [--date YYYY-MM-DD]` (updates all four)
- BigQuery `vantage.ad_performance_events` and `vantage.generation_audit` rows carry `app_version` so historical performance can be sliced by version

## Roles & permissions (v2.2+)

5-tier RBAC stored in `users/{uid}` (Firestore):

| Role | Brand-level | Hotel-level | Notes |
|---|---|---|---|
| `admin` | All | All | Bypass on every check |
| `brand_manager` | Assigned brands | All hotels under those brands | Cannot have hotel-only assignments |
| `area_manager` | None | Assigned hotels (multi) | Hotel-only assignments |
| `hotel_marketing_manager` | None | Exactly 1 hotel | Reject brand-level ops |
| `agency` | Assigned brands | Plus assigned hotels | Cross-client mix |
| `user` (legacy) | None | Treated as area_manager-equivalent for backwards compat |

Two visibility flags on each user, set by admin:
- `show_token_count` — when off, `/auth/me/billing` returns `tokens: null` for every row
- `show_token_amount` — same, for `cost_inr`. Frontend renders "—" in their place.

Assignments live in `property_assignments/{uid}/items/{auto_id}`:
```
{ scope: 'brand' | 'hotel', brand_id?, hotel_id?, granted_at }
```

## Data model — Firestore collections

| Collection | Purpose | Created in |
|---|---|---|
| `users` | User profiles + role + visibility flags | v1 (extended v2.2) |
| `audit_logs` | Per-action firehose for admin views (login, generate, refine) | v1 |
| `admin_settings/config` | Workspace LLM config (default model) | v1 |
| `ad_insights` | Legacy keyword-search insights (still read by RAG fallback) | v1 |
| `brand_usps` | Legacy brand USP records (still queried by `_firestore_fallback_usps`) | v1 |
| `historical_ads` | Raw ad rows from CSV uploads | v1 |
| `embedding_cache` | `{embedding, headline, description, campaign_type, ...rich metadata}` keyed by content hash. Used by both Vector Search and the in-app cosine fallback. | v2.0 |
| `bq_query_cache` | 24h cached BigQuery aggregates | v2.0 |
| `training_state` | Training run records (Sessions table data) | v2.0 |
| `training_directives` | Approved AI-summarized training directives | v2.0 |
| `ingestion_jobs` | Async CSV ingestion progress (Cloud Tasks-fired) | v2.1 |
| `ingestion_progress/{run_id}` | Live progress for in-flight v2.1 training runs | v2.1 |
| **`brands`** | Brand catalog. `{brand_name, slug, voice, hotel_count, created_at}` | v2.2 |
| **`hotels`** | Hotel catalog. `{hotel_name, hotel_code, brand_id, brand_name, rooms_count, fnb_count, website_url, gmb_url, gmb_place_id, status}` | v2.2 |
| **`property_assignments/{uid}/items`** | RBAC scope grants per user | v2.2 |
| **`kb_summaries/{brand_id|hotel_id}`** | (Optional) digest written on training run completion for the Knowledge Base panel. KB router currently aggregates live; this is an optimization opportunity. | v2.2 |

## Data model — BigQuery

`vantage.ad_performance_events` (25 cols, `US` multi-region):

```
brand_id, platform, campaign_id, headline, description,
ctr, cpc, roas, impressions,
date, training_run_id, model_version, ingested_at,

(v2.1 additions)
campaign_type, ad_strength, hour_of_day, day_of_week, month, season,
performance_score, confidence_weight, recency_decay, ctr_normalized,

(v2.2 additions)
generation_id, app_version
```

`vantage.generation_audit` (17 cols):

```
timestamp, brand_id, user_id, platform, model,
tokens_in, tokens_out, latency_ms,
ad_content_hash, training_run_id, request_type,

(v2.2 additions)
generation_id, app_version, scope, hotel_id, status, error_message
```

`vantage.training_audit`, `vantage.safety_events` — provisioned, basic schemas, used by `audit_logger.py` (fire-and-forget).

## Critical pipelines

### Ad generation (v2.2)

Path: `routers/generate.py → services/ad_generator.py → rag_engine + scraper + reviews + seasonal + audit_logger`.

1. Resolve `selection.scope` (`hotel | brand | multi`) from request.
2. If `scope = hotel`, fetch hotel record from `hotels/{hotel_id}` — gets `rooms_count`, `fnb_count`, `gmb_url` to inject as `## PROPERTY ATTRIBUTES`.
3. Call `retrieve_ad_insights(scope, brand_id, hotel_id, hotel_name_for_anonymize, ...)`:
   - Embeds the brief, queries Vector Search (or Firestore cosine fallback).
   - For `scope = brand`: anonymizes hotel exemplars (strips property names, possessives like "X's spa" → "the spa").
4. Brand scope ALSO skips GMB review fetch entirely (no `review_data` injection).
5. Generates `generation_id` UUID, threads it through:
   - Cloud Logging structured fields (`json_fields.generation_id`)
   - Firestore `audit_logs` row
   - BigQuery `generation_audit` row (via `audit_logger.log_generation`)
6. On exception, the router writes a `status='error'` BQ row before re-raising.

### Training ingestion (v2.1+)

Three section types route to the v2.1 deterministic pipeline (NOT the legacy AI-summarization flow):

| section_type | Adapter | Source schema |
|---|---|---|
| `google_ads_export` | `google_ads_adapter.parse_google_ads` | 39-col Google Ads Editor CSV |
| `moengage_push` | `moengage_adapter.parse_moengage` | 11-col MoEngage push export |
| `brand_usp_csv` | `brand_usp_adapter.parse_brand_usp` | 3-col `brand_name, hotel_name, usps` |

Pipeline: validate → parse → score (recency × confidence × CTR_normalized, hard floor at 100 impr) → write BQ → embed eligible records → upsert vectors. Live progress at `/training/progress/{run_id}` polled every 800ms by the frontend.

### Hotels Ingestion (v2.2)

`POST /hotels/ingest` accepts a 7-column CSV (XLSX too). Required: `hotel_name, hotel_code, brand_name`. Optional: `rooms_count, fnb_count, website_url, gmb_url`.

Brand auto-creation on first sighting via `slugify(brand_name)`. Background enrichment fires `enrich_batch(hotel_ids)` after the response — Place ID resolution via Find Place API.

## Frontend layout (v2.3)

| Path | Component | Visibility |
|---|---|---|
| `/hub` | `pages/Hub.jsx` | All authenticated. Post-login default. Hero + identity strip + tools grid + recents. |
| `/adcopy` | `pages/Dashboard.jsx` | All. Builder + Copilot mode toggle. ⌘⏎ submit, ⌘K toggle Copilot. |
| `/crm` | `pages/CRMWizard.jsx` | All. Multi-channel CRM campaign builder. |
| `/calendar` | `pages/MarketingCalendar.jsx` | All. Quarter grid view (read-only v2.3). |
| `/account` | `pages/MyAccount.jsx` | All. Profile / Properties & brands / Billing & usage. Token columns gated by `show_token_count` / `show_token_amount`. |
| `/admin` | `pages/Admin.jsx` | admin only. Users (5-tier UserForm) / Training / Audit / Settings tabs. |
| `/admin/hotels` | `pages/admin/HotelsIngestion.jsx` | admin only. CSV bulk + manual + template download. |
| `/admin/knowledge` | `pages/admin/KnowledgeBase.jsx` | admin only. Hierarchical brand → hotel tree. |

Editorial Mono design system: `frontend/src/styles/editorial-mono.css` — opt-in via `.em-scope` wrapper or individual `em-*` utility classes. Theme + density toggle via `<TweaksPanel>` (floating bottom-right).

## What's deferred / open

| Item | Rationale | Plan |
|---|---|---|
| Vertex AI Vector Search deployment | $50–100/mo VM cost; Option D in-app cosine handles up to ~10K records/brand at $0 | Flip on with one `gcloud` command when scale demands |
| Marketing Calendar drag/drop scheduling | v2.3 ships a read-only quarter grid pulled from audit logs | v2.4 — needs a `campaigns` Firestore collection + scheduling state machine |
| Full Ad Copy Builder pixel-match | v2.3 added kbd hints + shortcuts; deeper restyle deferred for stability of the working form | v2.4 — wrap fields in `em-card` and add the "remembered" auto-fill highlight pattern |
| Custom Search Engine CX | Replaced with Vertex AI Google Search grounding (v2.1) | Done; CX no longer needed |
| Memorystore / Redis | $50/mo + VPC connector cost | Not deployed; in-memory fallback in `core/cache.py` |
| Brand-level review aggregation | Brand scope skips GMB fetch entirely (per spec) | Optional: aggregate reviews across brand hotels into a synthetic "brand voice" summary |

## Paved paths for common tasks

- **Bump version:** `python scripts/bump_version.py 2.4` then commit & deploy.
- **Add a hotel:** Admin → Hotels Ingestion → CSV or manual form. Brand created on first sighting.
- **Add a user:** Admin → Users → role tile + assignment search + visibility tickboxes.
- **Add a training type:** new adapter at `backend/app/services/ingestion/adapters/`, register in `ADAPTER_SECTION_TYPES` in `csv_validator.py` + `training.py`, wire into `_run_v21_ingestion`.
- **Trace a generation:** `gcloud logging read 'jsonPayload.generation_id="<UUID>"'` filters Cloud Run logs; same UUID appears in BQ `generation_audit` and Firestore `audit_logs.generation_id`.

## Recent commits

```
0d21ee5  feat(v2.3): Hub Home + Marketing Calendar + Tweaks Panel + Ad Copy kbd hints
dec4273  chore: bump app version 2.2 -> 2.3
1845c08  feat(v2.2): frontend — Editorial Mono tokens + 5-tier user form + Hotels Ingestion + Knowledge Base + My Account
1f1fd20  feat(v2.2): 5-tier RBAC + Hotels Ingestion + Knowledge Base + scope-aware retrieval + generation IDs
c4653f8  feat: per-session remarks + delete button for training sessions
7811f43  feat: live progress bar for v2.1 training ingestion runs
e9c4eda  fix: route v2.1 section types to ingestion pipeline + robust CSV decode
92e4fa7  feat(v2.1): in-app cosine similarity fallback (Option D)
e879257  feat(v2.1): training pipeline overhaul for Google Ads + MoEngage
70ff608  fix: correct SeasonalContext field name uplift_pct -> demand_uplift_pct
9fdc61f  feat: Vantage v2.0 upgrade — Vertex AI, semantic RAG, BigQuery, enterprise features
```
