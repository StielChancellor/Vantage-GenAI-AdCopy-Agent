# Vantage GenAI — Memory

A running record of where the project is. Read this first when picking the
work back up. Last updated: 2026-05-09 (App v2.4).

## v2.4 hotfix sweep (2026-05-09 PM)

QA pass via Claude-in-Chrome MCP found one critical bug + minor polish items:

- **`POST /generate` was 500-ing on every call.** `_build_user_prompt` in
  `services/ad_generator.py` had a stale reference to `primary_ct` (a local
  in `generate_ad_copy`). Recompute inline via `_primary_campaign_type(request.platforms)`.
- **`/generate/url-suggestions` 500s** are now silently swallowed — composite
  index missing, but it's a non-essential autocomplete and shouldn't pollute
  the console.
- **Picker dropdown empty rows** — root cause was the broad `.em-switcher input`
  CSS rule applying `width:100%/padding/border-radius` to row checkboxes.
  Selector was tightened to `.em-switcher > input` + `input[type=text/search]`.
- **Picker "No matches" shadow** — empty state now only renders when EVERY
  group (loyalty / cities / brands / hotels) is empty, so folded-in selected
  chips remain deselectable.
- **Hub Switch context modal scroll** — modal now caps at 80vh with the picker
  scrolling internally; the action footer is sticky so the "Use this for Ad
  Copy" button is always reachable.
- **LandingPage version label** — `v2.6` hardcoded badges replaced with
  `{APP_VERSION}` so landing stays in sync with `core/version.py`.

Re-QA after hotfix (10 scenarios, all ✅):
1. Picker dropdown rows render real labels
2. Single hotel auto-fill (URL + rooms/F&B summary)
3. Generate single → 200 (2,130 tok / 15.5s)
4. Multi-hotel combined → 200 (2,060 tok / 23.2s)
5. Multi-hotel separate fan-out → 200 (4,244 tok / 33.8s; variant labels suffixed per hotel)
6. Brand-only generation without URLs → 200 (762 tok)
7. Club ITC loyalty → 200 (875 tok); cross-brand exemplars verified
8. Recent generations Re-use brief repopulates form
9. Hub Switch context modal → multi-select → /adcopy with chips applied
10. 42 /api/v1/* requests, all 200; no 500s on /generate or /hotels/*

## v2.4 — Intelligent Ad Copy Builder + Club ITC + Chain/City Hierarchy (2026-05-09)

- **Club ITC** is now bootstrapped on every backend startup as a
  `kind='loyalty'` brand at `brands/club-itc`. `services/hotels/catalog.py:ensure_club_itc()`
  runs in the FastAPI startup hook. Loyalty brands sort to the top of the
  PropertySwitcher and trigger cross-brand RAG.
- **Cross-brand training for loyalty brands.** When the resolved brand has
  `kind='loyalty'` (or `is_loyalty=True` is set in `PropertySelection`),
  `services/rag_engine.retrieve_ad_insights()` pulls top exemplars from every
  non-loyalty brand and pushes them through `_anonymize_passage` before
  merging with the loyalty brand's own training. `ad_generator` skips per-property
  attributes and GMB review fetch in this mode and injects a `## LOYALTY
  PROGRAMME CONTEXT` block.
- **City as a new RBAC + scope level.** `hotels.city` is an optional CSV
  column; `ScopeAssignment.scope='city'` grants access to every hotel in that
  city. New `/hotels/cities` endpoint feeds the admin city-chip add-on.
- **Group scope.** `ScopeAssignment.scope='group'` is admin-equivalent without
  the admin role. Must stand alone. `core/auth.has_group_scope()` short-circuits
  every access helper.
- **brand_only flag.** A brand-scope grant with `brand_only=True` restricts the
  user to brand-level ops only — they cannot access individual hotels under
  that brand. Enforced in `auth.user_can_access_hotel` and
  `routers/generate._enforce_selection_access`.
- **IntelligentPropertyPicker** (`frontend/src/components/IntelligentPropertyPicker.jsx`)
  replaces ContextSelector on the Ad Copy form. Role-aware:
  - 1 hotel scope → static chip (no picker).
  - Multiple hotels → typeahead opens dropdown of every accessible hotel with checkboxes.
  - Mixed brands/cities/Club ITC → typeahead with grouped sections (Loyalty,
    Cities, Brands, Hotels) and independent checkboxes.
  - Auto-fetches `/hotels/scope-search?include_empty=true` to pre-pick the
    user's only entity.
  - Emits `{scope, hotel_ids, brand_ids, cities, is_loyalty, _labels}`.
- **Auto-fill in Dashboard.** On selection of one hotel: GMB url, website url,
  rooms/F&B/city summary auto-populate (with the existing "Remembered" pill).
  On selection of one brand: brand voice fills Other Information. Loyalty
  picks lock GMB and rooms/F&B fields.
- **Recent generations panel.** New `<RecentGenerations>` below the form;
  filtered by current `hotel_id` / `brand_id`. Each row has a "Re-use brief"
  button that repopulates the form from the audit row (offer_name, inclusions,
  reference_urls, platforms, campaign_objective). Powered by `/generate/recent`.
- **Five admin grant presets** in `UserForm.jsx`:
  1. Brand only (`brand_only=true`)
  2. All hotels in brand (`brand_only=false`)
  3. Brand + few hotels
  4. Club ITC only
  5. Complete group access
  Plus a separate City multi-chip add-on layered on top of any non-group preset.
  Hotels-only preset retained for area_managers + hotel_marketing_managers.
- **Cloud Build invocation reminder.** `cloudbuild.yaml` references
  `$COMMIT_SHA`; manual submits must pass it explicitly via
  `--substitutions=COMMIT_SHA=manual-<ts>` (still required as of v2.4).

## v2.3.1 hotfix (2026-05-07)

## v2.3.1 hotfix (2026-05-07)

- **Unified color scheme.** Legacy `--gold/--primary` tokens redefined in
  `frontend/src/index.css` to point at the Editorial Mono red accent
  (`#c8331e` light / `#e85a44` dark). 8 hardcoded `rgba(201,168,76,*)`
  values that survived the token swap (vite was minifying them to
  `#c9a84c*` in the bundle) were also replaced with the red equivalent.
  `Login.jsx` Zap icon switched from hardcoded `#c9a84c` to `var(--primary)`.
- **My Account resilience.** Frontend uses `Promise.allSettled` so a failing
  `/auth/me/billing` no longer blanks the page. Backend `/auth/me` wraps
  `_user_to_out` (and its scope-summary lookups) in try/except + falls back
  to a minimal `UserOut`. `/auth/me/billing` retries without the composite
  `where + order_by` index when Firestore raises.
- **Admin tabs reorganized.** `Hotels Ingestion` and `Knowledge Base` are
  now inner tabs of `/admin` alongside `Users / Training / Audit & Usage /
  LLM Settings`. The standalone sidebar links to those routes were removed.
  Routes `/admin/hotels` and `/admin/knowledge` are still mounted in
  `App.jsx` for backward compatibility.
- **Training tab cleanup.** `TrainingWizard` no longer renders the inner
  `Directives` + `Knowledge Base` panels. `Sessions` is the only sub-panel.
  Unused handlers (`handleDeleteDirective`, `loadDirectives`, KB search) and
  imports removed.
- **Cloud Build invocation note.** `cloudbuild.yaml` references `$COMMIT_SHA`
  which is empty for `gcloud builds submit` runs. Pass it explicitly:
  `gcloud builds submit --config cloudbuild.yaml --substitutions=COMMIT_SHA=manual-<ts> .`

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
