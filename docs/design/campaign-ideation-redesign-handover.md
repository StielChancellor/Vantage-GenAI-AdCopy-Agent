# Design Handover — Campaign Ideation (v2.7)
## Brief for a full UI redesign of `/ideation`

**App:** Vantage GenAI · v2.7 · https://vantage-adcopy-agent-yxsestxy7a-uc.a.run.app/ideation
**Brand:** ITC Hotels — luxury hospitality, multi-brand chain (ITC Hotels, Welcomhotel, Fortune, Storii, plus Club ITC loyalty programme).
**Audience for the UI:** brand managers, agency leads, and senior marketers ideating multi-property campaigns.

---

## 1. What the section does

Campaign Ideation is the **upstream creative entry point** for the platform. The marketer arrives with a theme ("Monsoon Soiree", "Independence Day", "summer family escapes") and a property/brand selection; the tool acts as a senior critique partner, asks 5–7 sharpening questions, and returns **10 distinct campaign concepts** — each a name + tagline + 2–4 sentence story line + a prompt-ready visual direction paragraph. Selecting a concept auto-creates a draft in the existing Unified Campaign tool, where the user continues into brief-lock → multi-channel fan-out.

The concepts are grounded in past creative when available — Gemini Vision captions of the brand's previously-uploaded static ads (palette, motifs, logo unit, photography style, mood) feed the shortlist generator as RAG context.

This is positioned UPSTREAM of every other generation tool in the platform: Ideation → Unified Campaign → (per-channel) Ad Copy / CRM / Marketing Calendar.

---

## 2. Where it sits (information architecture)

**Sidebar order (left-to-right intent):**
1. Home (`/hub`)
2. **Campaign Ideation** (`/ideation`) ← this section
3. Unified Campaign (`/unified`)
4. Ad Copy (`/adcopy`)
5. CRM (`/crm`)
6. Marketing Calendar (`/calendar`)
7. My Account
8. (Admin) Users & Settings, Creative Assets, …

The sidebar narrative is "Start here for net-new ideas → finalise the brief → execute the channels → see the calendar." The redesign should reinforce that Ideation is **the front door for new thinking**, distinct from Unified Campaign (which already assumes the user knows what they want to brief).

**Adjacent admin page worth noting:** `/admin/creative-assets` is where past campaign packs (zip of static images + Excel of paired ad copies) are uploaded and Gemini-Vision-captioned. The captions are what make Ideation's visual direction specific instead of generic. The two pages do NOT need to live together, but the redesign should make it obvious to the brand manager that "what you see in visual direction comes from what was trained over there."

---

## 3. Current implementation (what exists today)

The current page is a functional MVP — 4-step wizard, no visual polish, reuses generic platform CSS. **Treat it as a strawman, not a constraint.**

| Step | What happens | Current UI |
|---|---|---|
| 1 — Setup | User enters theme free-text + optional date range + picks scope (hotel / brand / mix / loyalty) via `IntelligentPropertyPicker` | Single `wizard-panel` card with textarea, two date inputs, picker, primary CTA "Start critique" |
| 2 — Critique | LLM asks one question at a time, capped at 7 turns. Required topics: audience, hero offer, tone, must-mention, must-avoid | Past Q/A list on top, current question highlighted in a soft-bordered card with textarea + "Next" button. When ready, the card shows "Brief looks tight" with a "Generate 10 concepts" CTA |
| 3 — Shortlist | 10 cards in a responsive grid, each with name / tagline / story / visual direction / "Use this concept" CTA + a Regenerate-10 footer | Auto-fill grid of `em-card` blocks |
| 4 — Done | Toast + auto-redirect to `/unified?campaign_id=<new>` | Single success card |

**File:** [`frontend/src/pages/CampaignIdeation.jsx`](../../frontend/src/pages/CampaignIdeation.jsx)
**Backend it talks to:** `/api/v1/ideation/{start,answer,shortlist,choose,archive}` — see [`backend/app/routers/ideation.py`](../../backend/app/routers/ideation.py).

---

## 4. User flow + data shapes

Every screen has access to the following client state. Use it to design contextual cues, progress indicators, and graceful empties.

### 4.1 Selection (shared with the rest of the app)
```
{
  scope: "hotel" | "brand" | "multi" | "city" | "loyalty",
  hotel_ids: string[],     // when scope=multi/city
  brand_ids: string[],     // when scope=brand or multi
  cities:    string[],
  is_loyalty: boolean,     // Club ITC
  _labels: {
    hotels:  [{ id, label, brand }],
    brands:  [{ id, label, kind }],   // kind === 'loyalty' = Club ITC
    cities:  [{ label }]
  }
}
```
The picker is the canonical way to gather this — **do not design a new picker**. It collapses chips into groups and shows a "N selected" pill inside its input. Loyalty (Club ITC) sorts to the top.

### 4.2 Critique state
```
ideation_id, theme_text, date_start, date_end,
phase: "critique" | "shortlist" | "chosen" | "archived",
critique_turns: [{ q, a, ts }],     // 0..7
captured: {
  audience?, hero_offer?, tone?,
  must_mention?, must_avoid?,
  extras?
},
ready_for_shortlist: boolean
```

### 4.3 Shortlist item
```
{
  name:             string,  // ≤ 8 words
  tagline:          string,  // ≤ 12 words
  story_line:       string,  // 2–4 sentences
  visual_direction: string,  // 3–6 sentences; prompt-ready
  inspiration_asset_ids: string[]   // present but not surfaced in Phase 1
}
```
The shortlist is always exactly 10 items. The visual direction references palette tokens, motifs, logo placement, photography style, mood — concrete enough to feed image generation later.

### 4.4 Loyalty mode (Club ITC)
When `is_loyalty=true`, the backend anonymises any retrieved past-creative captions across partner brands. The visual direction in the shortlist will NOT mention specific property names. The redesign should subtly indicate this (a chip? a tone? an icon?) so the marketer understands why visual direction reads slightly more generic in loyalty mode.

---

## 5. Reuse list (DO NOT reinvent)

These components are battle-tested and used across other tools — the redesign should style around them, not replace them:

| Component | Path | Role |
|---|---|---|
| `IntelligentPropertyPicker` | `frontend/src/components/IntelligentPropertyPicker.jsx` | The only way to pick a property/brand/city. Knows the user's permissions, handles single-static-hotel mode, surfaces Club ITC at top. |
| `useSelection` | `frontend/src/contexts/SelectionContext.jsx` | Reads/writes the shared selection persisted in `localStorage`. Whatever the user picked here also pre-fills Ad Copy, CRM, Marketing Calendar. |
| Editorial Mono CSS | `frontend/src/styles/editorial-mono.css` | Existing design tokens — see § 7. |
| `TweaksPanel` | floating FAB in the bottom-right | User-chosen theme + density. Keep it visible. |
| Toaster | `react-hot-toast` (top-right) | Already wired. |

**Routes the redesign must keep working:** `/ideation` (this page), `/unified?campaign_id=<id>` (handoff target when a concept is chosen), `/admin/creative-assets` (the upstream training page — link to it from an empty state).

---

## 6. Hard constraints (non-negotiable)

These are platform invariants, not design choices:

1. **No free-text property names.** Every property/brand/city pick must flow through `IntelligentPropertyPicker`. Free-text inputs for "which hotel?" are a regression.
2. **Selection is shared.** The page must read AND write `useSelection()` so the choice survives navigation to Unified Campaign.
3. **Exactly 10 items in the shortlist.** The backend guarantees this; the layout must scale to 10 without scroll fatigue.
4. **Loyalty visual direction is anonymised.** Don't surface "ITC Maurya" or specific cities when `is_loyalty=true`.
5. **Critique cap is 7 questions.** Server-enforced — UI should make remaining-question-count visible so the user doesn't feel interrogated.
6. **Theme text minimum length is 6 characters.** Anything shorter is rejected by the Start CTA today; the redesign should communicate why.
7. **No emojis in the UI** unless the user explicitly opts in (platform-wide convention).

---

## 7. Visual system — Editorial Mono

The platform's design system is "Editorial Mono" — a restrained palette inspired by luxury editorial print (think Wallpaper*, Cereal). Available CSS classes the redesign already has access to:

| Token / class | Role |
|---|---|
| `--primary` (Editorial Mono red, aliased from `--gold` for backward compat) | Hero accent, primary CTAs |
| `--em-ink`, `--em-ink-soft`, `--em-ink-faint` | Three-tier ink for hierarchy (body / secondary / tertiary) |
| `--em-bg-soft` | Card background; subtle elevation |
| `em-card`, `em-pill`, `em-chip`, `em-switcher`, `em-mode-card`, `em-hero`, `em-identity`, `em-tool`, `em-tree`, `em-stat`, `em-panel`, `em-cal-*`, `em-tweaks` | Pre-built component classes |
| `em-mono-label` | The signature mono-spaced micro-label (used for section dividers, field hints) |
| `data-em-theme` / `data-em-density` | User-toggleable (Tweaks panel) — must work in light + dark, comfortable + compact |

**Tone:** considered, slow, premium. Plenty of negative space. Mono labels are a signature — keep them. Avoid the SaaS-default style of dense forms + bright pills.

The current `/ideation` page does NOT yet use these classes coherently — it leans on generic wizard CSS. The redesign should make Ideation feel like the most editorial, considered surface in the platform, since it's where creative thinking starts.

---

## 8. Edge + empty + error states the redesign must cover

The MVP under-handles these. Treat each as a first-class screen, not an afterthought.

1. **No creative assets uploaded yet for this brand.** Today the shortlist still generates but with generic visual direction. Design an empty state that links to `/admin/creative-assets` and explains "Upload past campaign packs to make visual direction specific to your brand."
2. **Picker isn't filled.** Theme + dates entered, but no scope → CTA disabled. Today: toast on click. Better: clear inline guidance.
3. **Critique question stream — long question.** Some Gemini outputs exceed ~28 words. The container needs to handle 1–4 lines without breaking the layout.
4. **User edits an already-answered question.** Currently impossible — once answered, the turn is fixed. UX research opportunity: should the user be able to revise an answer mid-critique?
5. **Regenerate the shortlist.** Today the only affordance is a "Regenerate 10" footer button. Consider: regenerate just one card, swap a tone, weight toward "less expected concepts," etc.
6. **Concept comparison.** With 10 cards on screen at once, users will want to pin / favourite / side-by-side compare 2–3 before committing.
7. **Loyalty mode indicator.** Today the only signal is the picker chip. Should be obvious throughout that this ideation is loyalty-mode (affects visual direction).
8. **Promotion success.** Step 4 is a stub with auto-redirect. Could it instead show the new Unified Campaign card with "Open" and "Stay here for another ideation"?
9. **Resuming an ideation.** The backend persists every ideation in `campaign_ideations/{id}` with phase. The UI has no list / continue-where-I-left-off affordance yet. (`GET /api/v1/ideation` returns the user's history — wire it.)
10. **Mobile / narrow viewport.** Current MVP is desktop-first. Brand managers will check shortlists from phones.

---

## 9. Tone of voice for copy in the UI

Same register as the brand: confident, considered, slightly editorial. Avoid:
- "Let's create some amazing campaigns!"
- "Awesome! Your ideation is ready."
- "We've generated 10 ideas for you to explore."

Prefer:
- "Sharpening the brief."
- "Ten concepts, ranked by distance from the obvious."
- "Choose one. It becomes the brief."

Mono labels are short, declarative, lowercase or small-caps — never sentence-case marketing copy.

---

## 10. Opportunities the redesign should explore

Not required, but valuable to think about:

1. **A visible "brief is taking shape" panel** during critique — live-updating chips for audience / hero offer / tone / must-mention / must-avoid as they get captured. Today the user can't see what the model has heard until step 3.
2. **Concept ranking / clustering** — the 10 are presented flat; some are inevitably variations of each other. Could we group by creative angle (narrative-led / visual-led / promo-led / experiential / cultural)?
3. **Reference-image moodboard** — the shortlist already cites `inspiration_asset_ids` from past creative; Phase 1 doesn't surface them. A small thumbnail strip per concept ("inspired by these past campaigns") would make the visual direction tangible.
4. **Compare drawer** — pin 2–3 concepts side-by-side before choosing.
5. **Edit-a-concept** — minor inline tweaks to name / tagline before promotion to Unified Campaign.
6. **Conversational re-shape** — after seeing the 10, the user might say "make them more festive" or "lean indulgent, less family." A free-text "shape the next batch" input would close the loop.
7. **Reusable concept library** — past ideations and their chosen concepts as a browsable archive in `/account` or `/calendar`.

---

## 11. What success looks like

- A senior brand manager can go from theme to chosen concept in **under 5 minutes**, with **zero confusion** about which step they're on or why a question is being asked.
- The page **feels like the editorial start of a creative process**, not a SaaS form.
- Users who haven't uploaded any creative assets yet **still get usable concepts**, AND understand exactly how to upgrade the output (upload past packs).
- The Loyalty (Club ITC) flow **looks visibly different** from a single-brand flow, so the user trusts that anonymisation is happening.
- The handoff to Unified Campaign is **continuous** — the marketer doesn't feel like they're starting a separate task.
- Works in **light + dark**, **comfortable + compact**, **desktop + mobile**, with no broken layouts.

---

## 12. Acceptance criteria for the redesigned `/ideation`

- [ ] All four steps usable end-to-end against the existing backend without API changes.
- [ ] Uses `IntelligentPropertyPicker` + `useSelection` as-is (no fork).
- [ ] Honors `data-em-theme` (light/dark) and `data-em-density` (comfortable/compact).
- [ ] Exactly-10 shortlist layout works without forcing scroll-fatigue on a 1440px screen.
- [ ] Empty-state for "no creative assets" with deep-link to `/admin/creative-assets`.
- [ ] Loyalty mode is visually distinct AND copy-distinct.
- [ ] Critique cap of 7 is visible to the user at all times.
- [ ] Concept cards readable on a 375px viewport (single column with comfortable line length).
- [ ] No new emoji introduced. No bright SaaS gradients. Mono labels preserved.
- [ ] Resume-an-ideation list (calls `GET /api/v1/ideation`) is at least scaffolded — even if the MVP only shows the last 5.

---

## 13. Out of scope (Phase 2+, do not design now)

These are intentional gaps — call them out in the design only as "future" if you want, but don't build them:

- AI-generated mockup images per concept (planned for Phase 2 via Imagen).
- Region scope (chain / region / hotel — region pending data-model work).
- A/B variant slot per concept.
- Live in-place edit of the visual direction in Unified Campaign.

---

## 14. Useful files / endpoints for the design exploration

- Page component: [`frontend/src/pages/CampaignIdeation.jsx`](../../frontend/src/pages/CampaignIdeation.jsx)
- Admin creative-assets uploader: [`frontend/src/pages/admin/CreativeAssets.jsx`](../../frontend/src/pages/admin/CreativeAssets.jsx)
- Sidebar (where the entry point lives): [`frontend/src/components/AppLayout.jsx`](../../frontend/src/components/AppLayout.jsx)
- Shared selection: [`frontend/src/contexts/SelectionContext.jsx`](../../frontend/src/contexts/SelectionContext.jsx)
- The picker: [`frontend/src/components/IntelligentPropertyPicker.jsx`](../../frontend/src/components/IntelligentPropertyPicker.jsx)
- Editorial Mono tokens + components: [`frontend/src/styles/editorial-mono.css`](../../frontend/src/styles/editorial-mono.css)
- Backend routes (read-only reference): [`backend/app/routers/ideation.py`](../../backend/app/routers/ideation.py)
- Pydantic shapes returned to the UI: search `class IdeationState`, `class ShortlistItem` in [`backend/app/models/schemas.py`](../../backend/app/models/schemas.py)
- Live app to click through: https://vantage-adcopy-agent-yxsestxy7a-uc.a.run.app/ideation (login: `admin@vantage.ai` / `Vantage@2025`)

---

## 15. Quick context the designer is allowed to assume

- The user is logged in (auth handled outside this page).
- The user has at least one accessible brand/hotel — the picker handles the no-access case at the platform level.
- The backend is online and returns within ~30s for critique turns and ~60s for the 10-concept shortlist.
- The user reads English. Multi-language is not Phase 1.
- Print is not a target. The web app is the only surface.
- The marketer cares more about quality of thinking than speed.

---

*Last updated 2026-05-14 against v2.7. If the underlying backend contract changes, update sections 4 + 14 first.*
