# Vantage GenAI — Memory

Last updated 2026-05-11. App v2.6.1.

## Live

- URL: https://vantage-adcopy-agent-yxsestxy7a-uc.a.run.app
- `/health` → `{"version":"2.6","version_date":"2026-05-11"}`
- Login: `admin@vantage.ai` / `Vantage@2025`
- Branch: `custome-HL` · https://github.com/StielChancellor/Vantage-GenAI-AdCopy-Agent
- GCP: project `supple-moon-495404-b0` (#717874273203), region `us-central1`, Firestore `nam5`, BQ `US`
- Model: `gemini-3.1-pro-preview` (override per-workspace via `admin_settings/config`)
- Cost: Cloud Run min-instance ~$15/mo + Firestore + BQ. Vector Search NOT deployed (Option D in-app cosine fallback active).

## Tool surface

| Route | Page | What it does |
|---|---|---|
| `/hub` | `pages/Hub.jsx` | Post-login home: hero + identity strip (honors `SelectionContext`) + 4 tool cards + "Pick up where you left off" + property memory side panel. Switch property/brand modal. |
| `/adcopy` | `pages/Dashboard.jsx` | Single-shot Ad Copy builder with `IntelligentPropertyPicker`. Multi-hotel auto-fill (parallel `/hotels/{id}/context`). Fan-out radio when 2+ entities. `RecentGenerations` panel below. |
| `/crm` | `pages/CRMWizard.jsx` | 5-step CRM wizard (Identity → Campaign → Events → Schedule → Results). Step 3 has Skip Events. |
| `/calendar` | `pages/MarketingCalendar.jsx` | Quarter grid. View-by dropdown (Property/Campaign/Brand/Club ITC) + drill-down. |
| `/unified` | `pages/UnifiedCampaign.jsx` | **v2.6** 5-step locked-brief wizard: Brief → Finalize (LOCK) → Events (skip) → Properties+Channels+Levels → Generate. |
| `/account` | `pages/MyAccount.jsx` | Profile · Properties · Billing · **Unified Briefs** (lists `/campaigns`, Edit auto-unlocks). |
| `/admin` | `pages/Admin.jsx` | Tabs: Users · Training · Audit · **Hotels Ingestion** · **Knowledge Base** · LLM Settings. |

## Key conventions (DO NOT break)

1. **Selection** is a single, persisted object shared via `contexts/SelectionContext.jsx` (`localStorage['vantage.selection.v1']`). All forms read/write via `useSelection()`. Hub modal writes to it before navigating.
2. **Property picker** is `components/IntelligentPropertyPicker.jsx`. Emits `{scope, hotel_ids, brand_ids, cities, is_loyalty, _labels}`. **Never** add free-text property inputs — always wire the picker.
3. **Backend access gate** for `/generate` is `routers/generate._enforce_selection_access`. All new generate-style routes must call something equivalent.
4. **Admin** always sees their own tokens + costs — `/auth/me` and `/auth/me/billing` force `show_token_count = show_token_amount = True` when role=admin. Don't gate admins on those flags.
5. **Club ITC** is a Firestore brand doc at `brands/club-itc` with `kind='loyalty'`. Bootstrapped on every FastAPI startup by `services/hotels/catalog.ensure_club_itc()` (called from `main.py`).
6. **Loyalty retrieval**: when the resolved brand has `kind='loyalty'`, `rag_engine.retrieve_ad_insights` fans out to up to 8 non-loyalty partner brands and anonymizes their exemplars before merging. `ad_generator` skips GMB review fetch + per-property attrs in loyalty mode.
7. **Brand-only flag** on a brand assignment means "brand-level ops only" — `auth.user_can_access_hotel` refuses hotel access when ALL matching brand grants are `brand_only=True`.
8. **CSS scoping**: `.em-switcher input` is scoped to `[type=text|search]` and direct-child inputs only. Checkbox inputs inside picker rows use `.em-switcher-check` and MUST NOT inherit the wide-input style.
9. **GMB review counts** are fetched lazily and cached on the hotel doc as `gmb_rating` / `gmb_review_count` / `gmb_details_at` (24h TTL) by `/hotels/{id}/context`. Frontend auto-fill reads `data.gmb` first, falls back to `hotel.gmb_*`.
10. **Manual `gcloud builds submit`** must pass `--substitutions=COMMIT_SHA=manual-<unix-ts>` because `cloudbuild.yaml` interpolates `$COMMIT_SHA` into the image tag.
11. **Version bump**: `python scripts/bump_version.py X.Y` updates `backend/app/core/version.py` + `frontend/src/version.js` + `frontend/package.json` + `README.md` in one go. ASCII-only output (no `→`/`✓` because Windows cp1252 console).

## Async-ness gotcha (root cause of multiple past 500s)

`services/rag_engine.get_brand_usps()` is **`async def`**. Calling it without `await` returns a coroutine; any `.get()` downstream raises `AttributeError` → 500. `crm_generator` was hit by this in v2.5 — fixed by adding `await` + try/except. Same trap exists in any new code that touches `get_brand_usps` or `retrieve_ad_insights`.

## Unified Campaign (v2.6) — orchestration rules

- Pick 1 brand + level `single` → orchestrator expands to one ad PER hotel under that brand (each generation gets that hotel's reviews + USPs + historic exemplars + past offers + property attrs).
- Pick 1 brand + level `chain` → one brand-anonymized ad.
- Pick 1 brand + level `chain_plus_single` → 1 brand + N per-hotel = N+1 results per channel.
- Pick Club ITC → forced loyalty mode, chain level only (single is silently dropped).
- Pick a city → `chain` keeps city scope; `single` expands to every hotel in that city.
- Channels: `search_ads` → Google Search via ad_generator; `meta_ads` → fb_single_image + fb_carousel via ad_generator; `app_push` → CRM generator.

## Open / deferred

| Item | Status |
|---|---|
| Vertex AI Vector Search deployment | Deferred — Option D in-app cosine handles current scale. Flip on with one `gcloud` command when volume demands. |
| Marketing Calendar drag/drop scheduling | Read-only quarter grid only. Needs a `campaigns` Firestore collection + scheduling state machine. |
| Per-version diffing of edited locked campaigns | Only unlock-to-edit supported; no diff. |
| Live channel-API delivery (push to FB/Google Ads) | Out of scope. We only generate copy. |
| Composite Firestore indexes for `audit_logs(user_email, hotel_name, timestamp DESC)` and `audit_logs(action, timestamp DESC)` | Indexes still missing; code falls back to unordered scan. Create indexes for perf. |
| Memorystore / Redis | Not deployed. `core/cache.py` in-process fallback. |
| `ContextSelector.jsx` cleanup | Legacy component, no active imports. Safe to delete next pass. |

## Recent commits (newest first)

```
4280a7b  fix(v2.6.1): stepper class · short campaign_name · brand → per-hotel fan-out
70e260c  feat(v2.6):  Unified Campaign tool (locked briefs + orchestrator)
8a522eb  feat(crm):   Skip events affordance in Step 3
e7e1327  fix(v2.5):   CRM 500 — await async get_brand_usps + harden router
7497178  feat(v2.5):  persistent shared selection + admin billing + calendar dropdowns + GMB review fix
3d0b7e4  fix(v2.4):   Hub modal dropdown clipped · smart picker counter · drop Edit identity
52e241d  fix(v2.4):   Hub modal sticky footer + MEMORY hotfix log
cade2e4  fix(v2.4):   primary_ct NameError · picker chip-fold visibility · LandingPage version pin
ebe16f5  fix(v2.4):   .em-switcher input scoped to search field only
34cf7a3  fix(v2.4):   multi-property auto-fill · brand/loyalty validation · Hub picker · per-entity fan-out
7883420  feat(v2.4):  Intelligent Ad Copy Builder · Club ITC · Chain/City Hierarchy
```

## Paved paths

- **Bump version**: `python scripts/bump_version.py X.Y` → commit 4 files → deploy.
- **Add a hotel**: Admin → Hotels Ingestion → CSV (8 cols incl. city) or manual.
- **Add a user with grants**: Admin → Users → pick role → pick preset → optionally city add-on chips.
- **Trace a generation**: `gcloud logging read 'jsonPayload.generation_id="<UUID>"'`. Same UUID lives in BQ `generation_audit` + Firestore `audit_logs`.
- **Add a training type**: new adapter at `services/ingestion/adapters/` → register in `csv_validator.ADAPTER_SECTION_TYPES` + `routers/training.py` → wire into `_run_v21_ingestion`.
- **Run the manual Cloud Build deploy**: `gcloud builds submit --config cloudbuild.yaml --substitutions=COMMIT_SHA=manual-$(date +%s) .` (or the PowerShell equivalent).
