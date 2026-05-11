# Vantage GenAI — Codebase Map

App v2.6 · 2026-05-11. Branch `custome-HL`. Live `https://vantage-adcopy-agent-yxsestxy7a-uc.a.run.app`.

Pure file index — one line per file, what lives there. Pair with `MEMORY.md` (runtime state) and `AGENT_HANDOFF.md` (rules + paved paths).

## Backend — `backend/app/**`

### Core (`core/`, `middleware/`)
| File | Role |
|---|---|
| `main.py` | FastAPI app, router mounts, startup hook (`ensure_club_itc`), SPA static serve. |
| `core/auth.py` | JWT, bcrypt, `get_current_user`, `require_admin`, `require_role`, 5-tier role consts, `has_group_scope`, `user_can_access_hotel/brand`, `resolve_user_hotel_ids/brand_ids`, assignment cache. |
| `core/config.py` | `get_settings()` — env vars + secret loading. |
| `core/database.py` | `get_firestore()` singleton. |
| `core/vertex_client.py` | Vertex AI init + `get_generative_model(model_name, system_instruction=)`. |
| `core/cache.py` | In-process TTL cache + `cache_key()` + `TTL_*` constants. |
| `core/version.py` | `APP_VERSION`, `APP_VERSION_DATE`. Bumped via `scripts/bump_version.py`. |
| `core/observability.py` | Cloud Logging + Cloud Trace setup. |
| `core/secrets.py` | Secret-Manager helpers. |
| `middleware/request_logger.py` | Structured request logging with trace IDs. |

### Routers (`routers/`) — every router under `/api/v1` prefix
| File | Mount | What |
|---|---|---|
| `health.py` | `/health` | Liveness + version. |
| `auth.py` | `/auth/{login,logout,me,me/billing}` | Login + JWT. `UserOut` forces token visibility=True for admins (v2.5). `/billing` retries without composite-index ordering on failure. |
| `admin.py` | `/admin/users{,/{id}}`, `/admin/scope-search`, `/admin/settings`, `/admin/audit-logs`, `/admin/usage-stats`, `/admin/export/usage`, `/admin/upload/*` | 5-tier user CRUD. Helpers: `_validate_assignments`, `_write_assignments`, `_build_scope_summary`, `_safe_assignment`, `_user_to_out`. |
| `hotels.py` | `/hotels/*` | `list_hotels`, `/scope-search?include_empty=true` (picker pre-fill), `/cities`, `/{id}`, `/{id}/context` (returns hotel + brand + USPs + recent_generations + **live GMB rating/review_count**, cached 24h via `gmb_details_at`), `/brands/{id}`, `/brands/{id}/context`, ingest CSV (8 cols incl. city), manual POST, PATCH, soft DELETE. |
| `generate.py` | `/generate{,/refine,/recent,/url-suggestions}` | Ad-copy. `_enforce_selection_access` (v2.4). `_explode_selection_for_fanout` when `selection.generation_mode='per_entity'`. `url-suggestions` falls back to unordered scan. Audit-log write wrapped in try/except. |
| `crm.py` | `/crm/{generate,refine,export-calendar}` | CRM. v2.5 wrapped in try/except + structured exc log. |
| `campaigns.py` | `/campaigns{,/structure,/{id},/{id}/lock,/{id}/unlock,/{id}/archive,/{id}/generate}` | Unified Campaign CRUD. PATCH draft-only (409 on locked). Owner-or-admin guard via `_require_owner_or_admin`. |
| `training.py` | `/training/{upload,progress/{run_id},answer,sessions,sessions/export,directives,knowledge-base}` | v2.1 deterministic ingestion + legacy AI-summarisation. |
| `knowledge.py` | `/kb/tree?brand_id=` | Admin hierarchical KB — brand→USPs+notes→hotels. |
| `places.py` | `/places/autocomplete` | Google Places autocomplete → details (rating + review_count). |
| `events.py` | `/events/search` | Vertex AI Google-Search-grounded event lookup. |
| `copilot.py` | `/copilot/{chat,briefs/save,briefs/{mode},briefs/{id}}` | Conversational brief mode. |

### Services (`services/`)
| File | Role |
|---|---|
| `ad_generator.py` | `generate_ad_copy(request)` — main pipeline. Scope-aware (`hotel`/`brand`/`loyalty`/`multi`/`city`). Pulls reviews (skipped for brand/loyalty), scraped URLs, RAG insights, USPs, training directives, seasonal. v2.4.1 fix: `_build_user_prompt` recomputes `primary_ct` inline via `_primary_campaign_type(platforms)`. Helpers: `_primary_campaign_type`, `_build_system_prompt`, `_parse_response`. |
| `rag_engine.py` | `retrieve_ad_insights(scope, brand_id, hotel_id, hotel_name_for_anonymize, city_for_anonymize, is_loyalty)`. Loyalty mode pulls top 2 exemplars from each of up to 8 partner brands, anonymized. `get_brand_usps()` **async — must await**. `_anonymize_passage()` strips property names + possessives ("X's spa" → "the spa"). `_semantic_retrieve` → embed → Vector Search → Firestore fetch → sort by perf_score. |
| `crm_generator.py` | `generate_crm_content(request)` — v2.5 awaits `get_brand_usps`. Calendar generator gracefully handles non-ISO dates. |
| `profile_insights.py` | `get_or_create_profile(hotel_name, urls, listings)` — cached scrape + review summary. |
| `scraper.py` | `scrape_hotel_page(url)` — defensive HTTP + BS4. |
| `reviews.py` | `fetch_google_reviews(gmb_url, hotel_name)`. |
| `training_engine.py` | `get_training_directives(section_type=None)` — sync. |
| `event_search.py` | Vertex AI grounded event search. |
| `copilot_engine.py` | Brief tracker + multi-turn chat. |
| `csv_ingestion.py` | Legacy CSV ingestors: `ingest_historical_csv`, `ingest_brand_usp_csv`. |
| `hotels/catalog.py` | `slugify`, `upsert_brand(name, kind='hotel')`, `ensure_club_itc()`, `set_brand_kind`, `upsert_hotel(row, brand_id, brand_name)`, `recount_brand_hotels`, `ingest_csv(df)`, `list_hotels/list_brands`, `search_scope(q, include_empty)`, `list_cities`, `hotels_for_brand(brand_id)`, `hotels_for_city(city)`, `get_hotel/get_brand`, `soft_delete_hotel`. Constants `CLUB_ITC_BRAND_ID='club-itc'`, `CLUB_ITC_DEFAULT_VOICE`. |
| `hotels/enrichment.py` | `enrich_hotel(id)`, `enrich_batch(ids)` — async place_id resolution; `_extract_place_id`, `_find_place_by_text`. |
| `campaigns/structurer.py` | `structure_brief(raw, urls)` — Gemini → StructuredCampaign JSON. `_short_name()` enforces ≤60 chars / ≤8 words. `_heuristic_fallback()` for LLM failures. |
| `campaigns/orchestrator.py` | `run_campaign(campaign, override_selection)` — fan-out per (entity × channel × level). v2.6.1: brand entity + `single`/`chain_plus_single` expands to `hotels_for_brand`. City expands to `hotels_for_city`. Reuses `ad_generator` (search/meta) + `crm_generator` (app_push). Helpers: `_hotels_under_brand`, `_expand_entities`, `_channel_to_platforms`, `_resolve_label`, `_gen_search_or_meta`, `_gen_app_push`. |
| `embedding/vertex_embedder.py` | `embed_texts(texts, use_cache=True)` — Vertex `text-embedding-005`. |
| `embedding/vector_index_manager.py` | `query_similar(...)` — ANN search; Option-D in-app cosine fallback. |
| `ingestion/normalized_record.py` | `NormalizedAdRecord`, `season_for_month(month)`. |
| `ingestion/csv_validator.py` | `ADAPTER_SECTION_TYPES` registry, tolerant decode. |
| `ingestion/batch_processor.py` | v2.1 pipeline: validate → parse → score → embed → write. |
| `ingestion/adapters/google_ads_adapter.py` | Parse 39-col Google Ads Editor CSV. |
| `ingestion/adapters/moengage_adapter.py` | Parse 11-col MoEngage push export. |
| `ingestion/adapters/brand_usp_adapter.py` | Parse 3-col `brand_name, hotel_name, usps` CSV. |
| `analytics/audit_logger.py` | `log_generation(...)` → BigQuery `vantage.generation_audit`. |
| `analytics/bq_query_engine.py` | Cached aggregations from `vantage.ad_performance_events`. |
| `analytics/bq_writer.py` | Append rows to BQ tables. |
| `analytics/quality_scorer.py` | Computes `performance_score`. |
| `seasonal/season_context.py` | `build_seasonal_prompt_context(flight_date)`. |
| `seasonal/trend_analyzer.py` | Trend windows. |
| `safety/content_filter.py` | `check_response(response, brand_id, request_type)` — Gemini safety + custom rules. |
| `ab_testing/variant_generator.py` | A/B variant generation helpers. |
| `ab_testing/performance_predictor.py` | Predictive scoring stub. |
| `tasks/task_dispatcher.py` | Cloud Tasks dispatch. |

### Models (`models/`)
| File | Role |
|---|---|
| `models/schemas.py` | ALL Pydantic models. Key items: `ROLES`, `ScopeAssignment` (brand/hotel/city/group + `brand_only`), `ScopeSummary`, `UserCreate/UserOut`, `PropertySelection` (`is_loyalty`, `generation_mode`), `HotelIngestRow/HotelOut/BrandOut` (`kind`), `AdGenerationRequest/Response`, `CRMGenerateRequest/Response`, training/copilot models, **Unified Campaign block at bottom**: `UnifiedCampaignBrief`, `StructuredHotel`, `StructuredCampaign`, `UnifiedCampaignSelection` (adds `campaign_levels` + `channels`), `UnifiedCampaign`, `CampaignPatchRequest`, `CampaignGenerateRequest`, `CampaignResultRow`, `CampaignGenerateResponse`. |

## Frontend — `frontend/src/**`

### Top-level
| File | Role |
|---|---|
| `App.jsx` | Routes; provider chain `ThemeProvider > AuthProvider > SelectionProvider`. Routes: `/`, `/login`, `/hub`, `/adcopy`, `/crm`, `/calendar`, `/unified`, `/account`, `/admin{,/hotels,/knowledge}`. |
| `main.jsx` | Vite entry; imports `index.css`. |
| `index.css` | Legacy app CSS. `--gold`/`--primary` aliased to Editorial Mono red (v2.3.1). Sidebar, forms, buttons, tabs, wizard-steps, wizard-panel, wizard-nav. |
| `App.css` | Unused boilerplate (Vite default). |
| `styles/editorial-mono.css` | v2.2+ Editorial Mono palette + components (`em-card`, `em-pill`, `em-chip`, `em-switcher`, `em-mode-card`, `em-hero`, `em-identity`, `em-tool`, `em-tree`, `em-stat`, `em-panel`, `em-cal-*`, `em-tweaks`). Theme via `data-em-theme`, density via `data-em-density`. `em-switcher input` scoped to text inputs only (v2.4.1 fix). |
| `version.js` | `APP_VERSION`, `APP_VERSION_DATE`. |

### Contexts
| File | Role |
|---|---|
| `contexts/ThemeContext.jsx` | Theme + density, localStorage persistence, sets `data-em-theme`/`data-em-density`/`data-theme` on `<html>`. |
| `contexts/SelectionContext.jsx` | **v2.5** — `useSelection()` returns `{selection, setSelection}`. Persists to `localStorage['vantage.selection.v1']`. Cleared on logout. |

### Hooks
| File | Role |
|---|---|
| `hooks/useAuth.jsx` | `AuthProvider`, `useAuth()`, login/logout, user JSON in `localStorage`. |

### Pages (`pages/`)
| File | Role |
|---|---|
| `LandingPage.jsx` | Public landing. Uses `APP_VERSION` for badges. |
| `Login.jsx` | Email + password. Zap icon = `var(--primary)`. |
| `Hub.jsx` | Post-login home. Hero, identity strip (honors `SelectionContext` — shows hotel/brand/composite labels), tools grid, recents, property memory ("All" for admin/group), Switch property/brand **modal** with `IntelligentPropertyPicker` + counter + Clear. |
| `Dashboard.jsx` | Ad Copy form. `useLocation` for router-state selection bootstrap, `useSelection()`, multi-hotel auto-fill (Promise.allSettled over `getHotelContext`), `urlOptional()` for brand/loyalty/city, fan-out radio when `needsFanoutPrompt()`. Renders `<RecentGenerations>` below. |
| `CRMWizard.jsx` | 5-step CRM wizard. v2.5 uses `IntelligentPropertyPicker` + `useSelection()`. Step 3 has Skip Events button (panel + nav). |
| `MarketingCalendar.jsx` | Quarter view. v2.5 dropdowns: View-by (Property/Campaign/Brand/Club ITC) + drill-down. Honors `useSelection()`. |
| `UnifiedCampaign.jsx` | **v2.6** 5-step wizard: Brief → Finalize (lock) → Events (skip) → Properties+Channels+Levels → Generate. Stepper class `.wizard-steps`. `VariantBlock` for inline edit. CSV export. |
| `MyAccount.jsx` | Tabs: Profile / Properties & brands / Billing & usage / **Unified Briefs** (v2.6). Billing uses `Promise.allSettled`. Unified Briefs lists campaigns with Edit (auto-unlocks) + Archive. |
| `Admin.jsx` | Admin Panel tabs: Users / Training / Audit & Usage / **Hotels Ingestion** / **Knowledge Base** / LLM Settings (v2.3.1 moved Hotels+KB into tabs). |
| `admin/HotelsIngestion.jsx` | CSV bulk + manual hotel form. v2.4: `city` optional column. Template download. |
| `admin/KnowledgeBase.jsx` | Hierarchical brand→hotel tree. |

### Components (`components/`)
| File | Role |
|---|---|
| `AppLayout.jsx` | Sidebar shell. Order: Home / Unified Campaign / Ad Copy / CRM / Marketing Calendar / My Account / (admin) Users & Settings. Theme toggle + version footer. |
| `AppNavbar.jsx` | Legacy (unused). |
| `IntelligentPropertyPicker.jsx` | **v2.4** picker. Reads `scopeSummary` to pick UX mode. Grouped dropdown (Loyalty / Cities / Brands / Hotels). Folds selected chips back into groups. "N selected" pill inside input (v2.4.2). Emits `{scope, hotel_ids, brand_ids, cities, is_loyalty, _labels}`. |
| `PropertySwitcher.jsx` | v2.2 single-select cascading picker (kept for admin UserForm). |
| `RecentGenerations.jsx` | v2.4 panel — last N briefs from `/generate/recent` filtered by hotel_id/brand_id; "Re-use brief" → `onReuse(row)`. |
| `ContextSelector.jsx` | **Legacy** — replaced by IntelligentPropertyPicker. No active imports; safe to remove next cleanup. |
| `AdResults.jsx` | Per-platform ad copy renderer with inline edit + refine. |
| `CRMResults.jsx` | CRM channel results (messages + char counts + warnings). |
| `CalendarView.jsx` | Day-grid CRM calendar. |
| `CampaignCalendarGrid.jsx` | Quarter grid component. |
| `CampaignTableView.jsx` | CRM messages table view. |
| `ChannelFrequency.jsx` | Per-channel send-days picker for CRM. |
| `EventCalendar.jsx` | Events grid (reused by CRM step 3 and UnifiedCampaign step 3). |
| `CopilotChat.jsx` | Conversational ad-copy/CRM mode. |
| `BriefSummaryCard.jsx`, `BriefTracker.jsx` | Copilot brief state visualisation. |
| `GenerationProgress.jsx` | Skeleton + spinner during long generations. |
| `TrainingWizard.jsx` | Admin training upload (v2.3 cleanup — Sessions only). |
| `TweaksPanel.jsx` | Floating theme + density FAB. |
| `admin/UserForm.jsx` | v2.4 form. Role tile + 5 grant presets (Brand only / All hotels in brand / Brand + few hotels / Club ITC only / Complete group / Hotels only) + city add-on chips. Uses `PropertySwitcher` (single mode). |

### Services
| File | Role |
|---|---|
| `services/api.js` | Axios instance + ALL API clients. Auth · admin · generate (`generateAds`, `refineAds`, `getRecentGenerations`, `getUrlSuggestions`) · hotels (`getHotel`, `getHotelContext`, `getBrandContext`, `getCities`, `scopeSearch`) · training · places · CRM · copilot · **campaigns** (`structureCampaign`, `createCampaign`, `lockCampaign`, `unlockCampaign`, `archiveCampaign`, `listCampaigns`, `getCampaign`, `patchCampaign`, `generateCampaign`). |

## Infra & ops

| File | Role |
|---|---|
| `Dockerfile` | 2-stage: node:20 builds frontend → python:3.12 runs uvicorn; copies `frontend/dist`. |
| `cloudbuild.yaml` | Cloud Build steps. **Uses `$COMMIT_SHA` — manual submits MUST pass `--substitutions=COMMIT_SHA=manual-<ts>`.** |
| `scripts/bump_version.py` | Bumps `core/version.py` + `frontend/src/version.js` + `frontend/package.json` + `README.md`. ASCII-only output (Windows cp1252-safe). |
| `backend/requirements.txt` | Python deps. |
| `frontend/package.json` | npm deps (vite, react, axios, lucide-react, react-hot-toast). |
| `frontend/vite.config.js` | Vite config. |
| `firestore.rules`, `firestore.indexes.json` | Rules + composite indexes (some still missing — code tolerates via `try`/fallback unordered scan). |

## Firestore collections

| Collection | Doc shape (key fields) |
|---|---|
| `users/{uid}` | full_name, email, password_hash, role (admin/brand_manager/area_manager/hotel_marketing_manager/agency/user), show_token_count, show_token_amount, created_at |
| `property_assignments/{uid}/items/{auto}` | scope, brand_id?, hotel_id?, city?, brand_only, granted_at |
| `brands/{brand_id}` | brand_name, slug, voice, hotel_count, **kind** (hotel/loyalty), created_at |
| `hotels/{hotel_id}` | hotel_name, hotel_code, brand_id, brand_name, **city**, rooms_count, fnb_count, website_url, gmb_url, gmb_place_id, **gmb_rating, gmb_review_count, gmb_details_at** (24h cache), status, ingested_at, last_modified_at |
| `audit_logs/{auto}` | user_email, user_id, action, hotel_name, **hotel_id**, **brand_id**, **scope**, offer_name, platforms, inclusions, reference_urls, tokens_consumed, cost_inr, model_used, time_seconds, timestamp, generation_id, app_version |
| `unified_campaigns/{id}` | user_id, user_email, status (draft/locked/archived), raw_brief, reference_urls, structured{}, events[], selection{}, generated[], created_at, updated_at, locked_at |
| `embedding_cache/{hash}` | embedding[], headline, description, campaign_type, brand_id, hotel_id?, performance_score, season |
| `bq_query_cache/{key}` | 24h cached BQ aggregates |
| `training_state/{run_id}` | run record + remarks |
| `training_directives/{auto}` | approved AI directives |
| `ingestion_jobs/{job_id}` | async CSV ingestion |
| `ingestion_progress/{run_id}` | live v2.1 ingestion progress |
| `kb_summaries/{brand_id\|hotel_id}` | optional KB digest |
| `admin_settings/config` | default_model + workspace LLM config |
| `ad_insights`, `brand_usps`, `historical_ads` | legacy v1 collections (still read by fallbacks) |

## BigQuery — `vantage.*`

| Table | Key columns |
|---|---|
| `ad_performance_events` | brand_id, platform, campaign_id, headline, description, ctr, cpc, roas, impressions, date, training_run_id, model_version, ingested_at, campaign_type, ad_strength, hour_of_day, day_of_week, month, season, performance_score, confidence_weight, recency_decay, ctr_normalized, generation_id, app_version |
| `generation_audit` | timestamp, brand_id, user_id, platform, model, tokens_in, tokens_out, latency_ms, ad_content_hash, training_run_id, request_type, generation_id, app_version, scope, hotel_id, status, error_message |
| `training_audit`, `safety_events` | provisioned, lightly used |
