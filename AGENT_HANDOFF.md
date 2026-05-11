# Agent Handoff — Vantage GenAI

Read this **before writing any code**. Three docs, in order:
1. **AGENT_HANDOFF.md** (this file) — rules, paved paths, anti-patterns.
2. **CODEBASE.md** — file index. Find any feature in one lookup.
3. **MEMORY.md** — runtime state, current version, known gotchas, deferred items.

## Operating rules

1. **Precision changes only.** Never refactor adjacent code "while you're here". Single-purpose diffs.
2. **Use the index first.** Open `CODEBASE.md`, jump to the file, read just the section you need. Do not grep the whole tree unless `CODEBASE.md` is wrong (then fix it in the same PR).
3. **Reuse, don't reinvent.** The `IntelligentPropertyPicker`, `SelectionContext`, `EventCalendar`, `AdResults`, `GenerationProgress`, `ad_generator.generate_ad_copy`, `crm_generator.generate_crm_content`, `rag_engine.retrieve_ad_insights`, `services/hotels/catalog.*` all exist. Wire them; don't fork.
4. **Selection is shared.** Any form that takes a property/brand pick must use `useSelection()` (frontend) and `selection: PropertySelection` (backend). Free-text property names are a regression.
5. **Picker emits a single shape**: `{scope, hotel_ids, brand_ids, cities, is_loyalty, _labels: { hotels, brands, cities }}`. Don't invent parallel shapes.
6. **Backend access gates.** Any new generate-style route must call `_enforce_selection_access` (see `routers/generate.py`) or an equivalent. Admin role + `scope='group'` bypass everything.
7. **Admin token visibility is forced True.** `/auth/me` + `/auth/me/billing` flip `show_token_count` / `show_token_amount` to True for admins regardless of the per-user flags. Don't gate admins on those.
8. **Async-ness check.** Any new code that calls `rag_engine.get_brand_usps`, `rag_engine.retrieve_ad_insights`, `ad_generator.generate_ad_copy`, `crm_generator.generate_crm_content`, `event_search.search_events` — those are all `async def`. Always `await`. Missing `await` is the #1 root cause of past 500s.
9. **Cloud Build manual submits.** Pass `--substitutions=COMMIT_SHA=manual-<unix-ts>` because `cloudbuild.yaml` requires `$COMMIT_SHA` for the image tag.
10. **CSS scoping.** The `.em-switcher input` selector is scoped to text/search inputs only (so picker row checkboxes work). Don't reintroduce the broad selector.
11. **Loyalty brand.** Club ITC = `brands/club-itc` with `kind='loyalty'`. Bootstrapped on every app startup by `ensure_club_itc()`. Don't recreate; don't rename. Treat loyalty in retrieval (`rag_engine` cross-brand exemplars) + generation (skip GMB + per-property attrs) + picker sort (top of list).
12. **Brand grant `brand_only`** restricts a user to brand-level ops only. `auth.user_can_access_hotel` already enforces this — don't bypass it in new code paths.
13. **Audit-log writes** are wrapped in try/except in `/generate`. Any new generate-style route should do the same so a Firestore hiccup never fails the user-visible response.
14. **Version bumping.** `python scripts/bump_version.py X.Y` is the only way. Touches 4 files in one commit. ASCII only in the script's print statements.
15. **Don't touch BigQuery schemas.** `vantage.ad_performance_events` and `vantage.generation_audit` have been ALTERed additively. Schema changes need a deploy-and-backfill plan.

## Paved paths (don't reinvent)

### Add a backend route
1. Add Pydantic models to `models/schemas.py` (group them under a header comment).
2. Add the route to an existing `routers/*.py` matching the domain (or create a new router if the domain is new).
3. Mount the new router in `main.py` (only if new file).
4. Use existing dependencies: `get_current_user`, `require_admin`, `require_role(*roles)`.

### Add a frontend page
1. Add file under `pages/`.
2. Wire the route in `App.jsx` inside the authenticated `<ProtectedRoute><AppLayout/></ProtectedRoute>` block.
3. Add sidebar entry to `components/AppLayout.jsx` (lucide-react icon).
4. Read shared selection via `useSelection()` — never local-only state for property picks.

### Generate something
- Single ad: `ad_generator.generate_ad_copy(AdGenerationRequest(...))`.
- Multiple ads fanned out: build `selection.generation_mode='per_entity'` and POST `/generate`, or use `services/campaigns/orchestrator.run_campaign(campaign, override_selection)` for entity × channel × level matrix.
- CRM: `crm_generator.generate_crm_content(CRMGenerateRequest(...))`.
- Loyalty exemplars: just set `selection.is_loyalty=True` (or pick a brand with `kind='loyalty'`); RAG handles the cross-brand pull automatically.

### Add a new training source
1. New adapter at `services/ingestion/adapters/<name>_adapter.py` exposing `parse_<name>(df) -> (records, errors)`.
2. Register in `services/ingestion/csv_validator.ADAPTER_SECTION_TYPES`.
3. Wire into `routers/training._run_v21_ingestion`.

### Deploy
1. `python scripts/bump_version.py X.Y`
2. `git commit -am "feat(vX.Y): …"` + `git push origin custome-HL`
3. `gcloud builds submit --config cloudbuild.yaml --substitutions=COMMIT_SHA=manual-$(date +%s) .` (or PowerShell `$([int][double]::Parse((Get-Date -UFormat %s)))`)
4. Verify `(Invoke-WebRequest /health).Content` shows the new version.

## Anti-patterns (do NOT do)

- Don't add a new property/brand picker. Use `IntelligentPropertyPicker`.
- Don't accept free-text property names. Use the picker's selection object.
- Don't call `get_brand_usps()` or `retrieve_ad_insights()` synchronously.
- Don't widen the `.em-switcher input` CSS selector.
- Don't write audit-log fields outside the existing wrapped try/except.
- Don't gate admin users on `show_token_*` flags.
- Don't introduce a new "campaign" data model — extend `unified_campaigns` if needed.
- Don't manually create Club ITC in admin UI — `ensure_club_itc()` already runs every boot.
- Don't break the existing `audit_logs` doc shape (`hotel_name` + `hotel_id` + `brand_id` + `scope`); the calendar, recent-generations panel, and `/auth/me/billing` all key off it.

## When to read more

- Adding a generate-style flow → read `services/ad_generator.py` end-to-end before writing.
- Touching RAG → read `services/rag_engine.py` end-to-end.
- Changing user roles or grants → read `core/auth.py` + `routers/admin._validate_assignments` together.
- New campaign behaviour → read `services/campaigns/orchestrator.py` end-to-end.

## When you finish

1. Run a build:`cd frontend && npm run build` (catches JSX + import errors).
2. Backend syntax: `python -c "import ast; ast.parse(open('backend/app/<file>.py').read())"`.
3. Commit with a Conventional Commit prefix: `feat`, `fix`, `chore`, `docs`. Include a one-paragraph "why".
4. Update **MEMORY.md** if the change affects runtime state (new collections, new conventions, new deferred items, new known gotchas).
5. Update **CODEBASE.md** if you added a file or moved a function.
6. Don't update `AGENT_HANDOFF.md` unless the rules themselves change.
