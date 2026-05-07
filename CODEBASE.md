# Vantage GenAI — Codebase Map

A guided tour for anyone (human or agent) joining the project. Pair with
`MEMORY.md` for runtime state and `README.md` for product framing.

App version: **2.3** (last live: 2026-05-07).

---

## High-level architecture

```
                ┌─────────────────────────┐
                │   React frontend         │  Vite SPA, served as static
                │   (Editorial Mono UI)    │  assets from FastAPI in prod
                └────────────┬────────────┘
                             │  HTTPS / JWT
                ┌────────────▼────────────┐
                │   FastAPI backend        │  Cloud Run, asia: nope, us-central1
                │   (uvicorn + middleware) │
                └────────────┬────────────┘
        ┌────────────┬───────┴────────┬──────────────┐
        ▼            ▼                ▼              ▼
   ┌────────┐  ┌──────────┐  ┌──────────────┐  ┌────────────┐
   │ Vertex │  │Firestore │  │  BigQuery    │  │Google Places│
   │  AI    │  │ (NoSQL)  │  │ (analytics)  │  │   + GMB     │
   │ Gemini │  │          │  │              │  │             │
   └────────┘  └──────────┘  └──────────────┘  └────────────┘
```

`gemini-3.1-pro-preview` for generation; `text-embedding-005` for retrieval
embeddings; Vertex AI Vector Search **provisioned but not deployed** — RAG
falls through to in-app cosine similarity over Firestore-cached embeddings
(see Option D in `vector_index_manager._firestore_similarity_search`).

---

## Backend layout (`backend/app/`)

```
backend/app/
├── main.py                    FastAPI app, observability bootstrap, router registration
├── core/
│   ├── version.py             APP_VERSION constant — kept in sync with frontend + README via scripts/bump_version.py
│   ├── config.py              Pydantic settings + secret manager hydration
│   ├── auth.py                JWT, bcrypt, 5-tier RBAC helpers (require_role, user_can_access_hotel/brand)
│   ├── secrets.py             Secret Manager wrapper with 5-min TTL cache
│   ├── database.py            Firestore client singleton (ADC on Cloud Run, key file locally)
│   ├── vertex_client.py       Vertex AI SDK init + GenerativeModel factory + cost calc
│   ├── observability.py       Cloud Trace + structured Cloud Logging setup
│   └── cache.py               Redis-or-memory cache with TTL constants
├── middleware/
│   └── request_logger.py      Per-request trace_id + structured access log
├── models/
│   └── schemas.py             Every Pydantic schema (AdGenerationRequest/Response, UserCreate, ScopeAssignment, HotelOut, etc.)
├── routers/
│   ├── health.py              GET /health, /version (returns APP_VERSION)
│   ├── auth.py                login, logout, /auth/me (hydrated), /auth/me/billing (visibility-gated)
│   ├── admin.py               5-tier user CRUD, audit logs, usage stats, settings, scope-search
│   ├── hotels.py              POST /hotels/ingest (CSV), CRUD, scope-search, role-aware reads
│   ├── knowledge.py           GET /kb/tree — admin-only hierarchical brand→hotel view
│   ├── generate.py            POST /generate, /generate/refine — wires generation_id + structured error logs
│   ├── places.py              Google Places autocomplete proxy
│   ├── training.py            POST /upload (with progress polling), /sessions, /progress/{run_id}, DELETE /sessions/{id}
│   ├── events.py              Vertex AI grounding-based event search (replaces Custom Search API)
│   ├── crm.py                 Multi-channel CRM campaign generator
│   └── copilot.py             Conversational brief builder
└── services/
    ├── ad_generator.py            Main pipeline. Resolves selection.scope, fetches hotel attrs, retrieves anonymized exemplars when scope=brand, threads generation_id everywhere.
    ├── rag_engine.py              Semantic retrieval. retrieve_ad_insights(scope, brand_id, hotel_id, ...). _anonymize_passage strips property identity for brand-level generations.
    ├── training_engine.py         Legacy AI-summarization training flow (kept for ad_performance/brand_usp/crm_performance section types).
    ├── scraper.py                 Multi-page crawler (1-level deep) for reference URL ingestion.
    ├── reviews.py                 Google Places Find Place + review fetch (skipped for brand-scope generations).
    ├── csv_ingestion.py           Legacy CSV ingestion (used by /admin/upload/historical-ads endpoints).
    ├── safety/content_filter.py   Vertex AI safety ratings + custom hospitality blocklist
    ├── analytics/
    │   ├── audit_logger.py        Streams generation_audit, training_audit, safety_events to BigQuery
    │   ├── bq_writer.py           write_ad_performance_rows, write_normalized_records (v2.1)
    │   ├── bq_query_engine.py     get_top_ads_for_scoring, get_pattern_summary, etc. (24h Firestore cache)
    │   └── quality_scorer.py      score_records: recency_decay × confidence_weight × ctr_normalized; impression floor at 100
    ├── seasonal/
    │   ├── season_context.py      Indian hospitality calendar (10 seasons with demand_uplift_pct)
    │   └── trend_analyzer.py      Vertex AI Google Search grounding for trending keywords
    ├── ab_testing/
    │   ├── variant_generator.py   3-angle variant generation (urgency, emotional, rational)
    │   └── performance_predictor.py  BQ-backed scoring of generated variants
    ├── ingestion/
    │   ├── normalized_record.py   NormalizedAdRecord dataclass (universal pipeline shape)
    │   ├── csv_validator.py       Schema validation + ADAPTER_SECTION_TYPES dispatch
    │   ├── batch_processor.py     Async chunked processing with Firestore progress writes
    │   └── adapters/
    │       ├── google_ads_adapter.py    39-col Editor CSV → exploded per-asset records
    │       ├── moengage_adapter.py      Push notification CSV → split per Android/iOS, drops zero-impression rows
    │       └── brand_usp_adapter.py     3-col CSV (brand_name, hotel_name, usps) → individual USP records
    ├── embedding/
    │   ├── vertex_embedder.py     embed_records → text-embedding-005 + content-hash cache + Firestore persist + Vector Search upsert
    │   └── vector_index_manager.py  upsert_vectors + query_similar with restricts (brand_id, campaign_type, season, impression_bucket)
    │                              Falls through to _firestore_similarity_search when no Vector Search endpoint deployed.
    ├── tasks/
    │   └── task_dispatcher.py     Cloud Tasks HTTP queue wrapper
    └── hotels/                    (v2.2)
        ├── catalog.py             upsert_brand, upsert_hotel, ingest_csv, search_scope, list_hotels/list_brands, soft_delete_hotel
        └── enrichment.py          enrich_hotel/enrich_batch — Place ID resolution, fire-and-forget after ingest
```

---

## Frontend layout (`frontend/src/`)

```
frontend/src/
├── version.js                   APP_VERSION mirror — bumped via scripts/bump_version.py
├── main.jsx                     React entry
├── App.jsx                      Router. /hub is post-login default.
├── styles/
│   ├── editorial-mono.css       v2.2+ design system (tokens + utility classes). Opt-in via .em-scope or em-* classes.
│   └── (legacy)                 The pre-existing app stylesheet still drives Dashboard/CRMWizard/Admin tables.
├── contexts/
│   └── ThemeContext.jsx         Theme (light|dark) + density (comfy|normal|dense). Writes data-theme + data-em-theme + data-em-density on <html>.
├── hooks/
│   └── useAuth.jsx              JWT bootstrap + logout helper
├── services/
│   └── api.js                   Axios instance + every API method (login, generateAds, startTraining, getTrainingProgress, deleteTrainingSession, ...)
├── components/
│   ├── AppLayout.jsx            Sidebar shell (Home, Ad Copy, CRM, Calendar, My Account, Admin section). Mounts <TweaksPanel/>.
│   ├── PropertySwitcher.jsx     Cascading brand→hotel typeahead (v2.2). Renders selection chips.
│   ├── TweaksPanel.jsx          Floating bottom-right panel for theme + density.
│   ├── TrainingWizard.jsx       Training upload form with live progress bar + sessions table + KB.
│   ├── ContextSelector.jsx      Legacy hotel/brand picker (still used by Dashboard).
│   ├── CopilotChat.jsx          Conversational brief builder.
│   ├── AdResults.jsx            Generated ad copy display.
│   ├── GenerationProgress.jsx   Generation progress UI.
│   └── admin/
│       └── UserForm.jsx         5-tier role tile picker + scope assignment + visibility tickboxes.
└── pages/
    ├── Hub.jsx                  Hub Home (v2.3) — hero + identity + tools + recents.
    ├── Dashboard.jsx            Ad Copy Builder (with ⌘⏎ + ⌘K shortcuts).
    ├── CRMWizard.jsx            CRM campaign builder.
    ├── MarketingCalendar.jsx    Quarter grid view (v2.3).
    ├── MyAccount.jsx            Profile / Properties / Billing (token columns visibility-gated).
    ├── Admin.jsx                Users + Training + Audit tabs (admin only).
    ├── LandingPage.jsx          Pre-login landing.
    ├── Login.jsx                Login form.
    └── admin/
        ├── HotelsIngestion.jsx  Bulk CSV + manual + template download (admin only).
        └── KnowledgeBase.jsx    Hierarchical brand→hotel tree (admin only).
```

---

## Infrastructure

```
infra/
├── setup-gcp.sh                One-shot bootstrap: 20 GCP APIs, 4 SAs, IAM, AR, GCS, BQ
└── cloud-run-service.yaml      Production Cloud Run spec (2Gi/2CPU, min=1, no CPU throttle)

scripts/
├── bump_version.py             Single-shot version bumper (4 files in lockstep)
└── (other admin scripts)

cloudbuild.yaml                  Build pipeline: Docker build → push to AR → deploy Cloud Run
Dockerfile                       Multi-stage: Node 20 frontend build → Python 3.12 backend
```

---

## API surface

`/health` `/version` — open
`/api/v1/auth/{login,logout,me,me/billing}` — JWT auth
`/api/v1/admin/{users,users/{id},scope-search,upload/*,audit-logs,usage-stats,settings}` — admin only
`/api/v1/hotels/{ingest,brands,scope-search,/{id}}` — admin writes, role-scoped reads
`/api/v1/kb/tree` — admin only
`/api/v1/generate` `/api/v1/generate/refine` — authenticated; carries generation_id
`/api/v1/training/{upload,sessions,progress/{run_id},sessions/{id}}` — admin only
`/api/v1/places/autocomplete` — proxied Google Places
`/api/v1/events/search` — Vertex AI grounding
`/api/v1/crm/{generate,refine,export-calendar}` — authenticated
`/api/v1/copilot/{chat,briefs/save,briefs/{mode},briefs/{id}}` — authenticated

---

## Where to add things

| Adding... | Edit |
|---|---|
| New role | `core/auth.py` constants + `models/schemas.py` ROLES + `core/auth.py` helpers + `routers/admin.py` `_validate_assignments` + `components/admin/UserForm.jsx` ROLES |
| New training section type | `services/ingestion/adapters/<new>.py` + register in `csv_validator.ADAPTER_SECTION_TYPES` + branch in `routers/training.py._run_v21_ingestion` + `frontend/src/components/TrainingWizard.jsx` SECTION_TYPES |
| New ad platform | `services/ad_generator.py` PLATFORM_SPECS + PLATFORM_TO_CAMPAIGN_TYPE + `frontend/src/pages/Dashboard.jsx` PLATFORMS |
| New visual screen | `frontend/src/pages/<New>.jsx` + register in `App.jsx` Routes + add NavLink in `components/AppLayout.jsx` |
| New KPI tracked in BigQuery | ALTER `vantage.ad_performance_events` (use the same PATCH-with-full-schema pattern in `infra/`) + add field in `services/analytics/bq_writer.py` and `services/ingestion/normalized_record.py:as_bq_row` |
| Bump version | `python scripts/bump_version.py 2.4` then commit + Cloud Build |

---

## Conventions

- **Role check ordering:** `require_admin` for write paths; `user_can_access_hotel/brand` for any cross-scope read; legacy `get_current_user` only when role doesn't matter.
- **Logging:** structured fields via `logger.info("event_name", extra={"json_fields": {...}})`. Include `generation_id` whenever known.
- **Errors in critical paths:** never let an audit/log/cache write break the primary flow. Wrap in try/except and log at debug.
- **Versioning:** any user-visible behavior change → bump version. The bumper script ensures README + frontend + backend all flip together so screenshots and BQ rows agree on what was live when.
- **Branch:** always `custome-HL`. `main` is upstream and untouched.
