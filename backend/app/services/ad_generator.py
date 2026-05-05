"""Ad copy generation using Gemini with pre-processed insights, brand guardrails, and platform optimization."""
import json
import time
from datetime import datetime, timezone

from backend.app.core.vertex_client import get_generative_model, extract_token_counts, calculate_cost_inr
from backend.app.core.config import get_settings
from backend.app.core.database import get_firestore
from backend.app.services.rag_engine import retrieve_ad_insights, get_brand_usps
from backend.app.services.training_engine import get_training_directives
from backend.app.services.scraper import scrape_hotel_page
from backend.app.services.reviews import fetch_google_reviews
from backend.app.services.seasonal.season_context import build_seasonal_prompt_context
from backend.app.services.safety.content_filter import check_response
from backend.app.models.schemas import (
    AdGenerationRequest, AdGenerationResponse, AdCopyOutput,
    AdRefinementRequest,
)

settings = get_settings()

# Platform character limits
PLATFORM_SPECS = {
    "google_search": {
        "name": "Google Search Ads",
        "headlines": {"count": 15, "max_chars": 30},
        "descriptions": {"count": 4, "max_chars": 90},
    },
    "fb_single_image": {
        "name": "Facebook Single Image Ad",
        "headlines": {"count": 5, "max_chars": 27},
        "descriptions": {"count": 5, "max_chars": 150, "min_chars": 50, "label": "Primary Text"},
    },
    "fb_carousel": {
        "name": "Facebook Carousel Ad",
        "headlines": {"count": 5, "max_chars": 45, "label": "Card Headlines"},
        "descriptions": {"count": 5, "max_chars": 18, "label": "Card Descriptions"},
        "captions": {"count": 1, "max_chars": 80, "label": "Primary Text"},
    },
    "fb_video": {
        "name": "Facebook Video Ad",
        "headlines": {"count": 5, "max_chars": 27},
        "descriptions": {"count": 5, "max_chars": 150, "min_chars": 50, "label": "Primary Text"},
    },
    "pmax": {
        "name": "Performance Max",
        "headlines": {"count": 15, "max_chars": 30},
        "descriptions": {"count": 5, "max_chars": 90},
    },
    "youtube": {
        "name": "YouTube Ads",
        "headlines": {"count": 5, "max_chars": 40},
        "descriptions": {"count": 5, "max_chars": 90},
        "captions": {"count": 1, "max_chars": 150},
    },
}


def _get_admin_model() -> str:
    """Get the admin-configured default model from Firestore."""
    try:
        db = get_firestore()
        doc = db.collection("admin_settings").document("config").get()
        if doc.exists:
            return doc.to_dict().get("default_model", "gemini-2.5-flash")
    except Exception:
        pass
    return "gemini-2.5-flash"


async def generate_ad_copy(request: AdGenerationRequest) -> AdGenerationResponse:
    """Full ad copy generation pipeline with caching, seasonal context, and safety filtering."""
    start_time = time.time()

    # Check cache first
    from backend.app.core.cache import get_cache, set_cache, cache_key, TTL_AD_GEN
    import hashlib
    brief_hash = hashlib.md5(
        f"{request.hotel_name}|{request.offer_name}|{request.inclusions}|{','.join(sorted(request.platforms))}".encode()
    ).hexdigest()[:16]
    ck = cache_key("ad_gen", brief_hash)
    cached_result = await get_cache(ck)
    if cached_result:
        return AdGenerationResponse(**cached_result)

    # Get admin-configured model (resolved via vertex_client)
    model_name = _get_admin_model()

    # 1. Gather context
    # Semantic RAG — pre-processed ad performance insights
    ad_insights = await retrieve_ad_insights(request.hotel_name)

    # Brand USPs & guardrails (semantic RAG)
    brand_data = await get_brand_usps(request.hotel_name)

    # Training directives (approved AI-generated insights from admin — global)
    training_directives = get_training_directives()

    # Scrape ALL reference URLs and merge content
    scraped_contents = []
    for url in request.reference_urls:
        url = url.strip()
        if not url:
            continue
        try:
            result = await scrape_hotel_page(url)
            scraped_contents.append(result)
        except Exception:
            scraped_contents.append({"content": f"Could not scrape {url}.", "title": ""})

    # Merge all scraped content
    scraped = {
        "content": "\n\n---\n\n".join(
            [s.get("content", "") for s in scraped_contents if s.get("content")]
        ),
        "title": " | ".join(
            [s.get("title", "") for s in scraped_contents if s.get("title")]
        ),
        "urls_scraped": len(scraped_contents),
    }

    # Google Reviews insights (support multiple listing URLs)
    review_data = {}
    listing_urls = request.google_listing_urls or (
        [request.google_listing_url] if request.google_listing_url and request.google_listing_url.strip() else []
    )
    for listing_url in listing_urls:
        if not listing_url or not listing_url.strip():
            continue
        try:
            rd = await fetch_google_reviews(listing_url, request.hotel_name)
            if not review_data or rd.get("review_count", 0) > review_data.get("review_count", 0):
                review_data = rd  # Keep the richest review data
        except Exception:
            pass
    if not review_data and listing_urls:
        review_data = {"insights": "No review data available.", "review_count": 0}

    # 2. Build the system prompt with guardrails
    system_prompt = _build_system_prompt(brand_data)

    # 3. Build the user prompt with all context (including seasonal)
    seasonal_context = build_seasonal_prompt_context(
        getattr(request, "flight_date", None)
    )
    user_prompt = _build_user_prompt(
        request=request,
        ad_insights=ad_insights,
        scraped=scraped,
        review_data=review_data,
        brand_data=brand_data,
        training_directives=training_directives,
        seasonal_context=seasonal_context,
    )

    # 4. Call Gemini via Vertex AI
    model = get_generative_model(model_name, system_instruction=system_prompt)
    response = model.generate_content(user_prompt)

    # 4b. Safety filter
    filter_result = check_response(
        response,
        brand_id=request.hotel_name,
        request_type="ad_copy",
    )
    if not filter_result.passed:
        raise ValueError(f"Generated content blocked by safety filter: {filter_result.harm_category}")

    # 5. Parse response and calculate tokens
    input_tokens = 0
    output_tokens = 0
    tokens_used = 0
    if response.usage_metadata:
        input_tokens = response.usage_metadata.prompt_token_count
        output_tokens = response.usage_metadata.candidates_token_count
        tokens_used = input_tokens + output_tokens

    variants = _parse_response(response.text, request.platforms)

    elapsed = round(time.time() - start_time, 2)

    ad_response = AdGenerationResponse(
        hotel_name=request.hotel_name,
        variants=variants,
        tokens_used=tokens_used,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_used=model_name,
        time_seconds=elapsed,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # Cache result for repeat briefs
    try:
        await set_cache(ck, ad_response.model_dump(), ttl=TTL_AD_GEN)
    except Exception:
        pass

    return ad_response


async def refine_ad_copy(request: AdRefinementRequest) -> dict:
    """Refine ad copy based on user feedback."""
    start_time = time.time()
    model_name = _get_admin_model()

    # Build the previous output as context
    previous_output_str = json.dumps(
        [
            {
                "platform": v.platform,
                "headlines": v.headlines,
                "descriptions": v.descriptions,
                "captions": v.captions,
                "card_suggestions": v.card_suggestions,
            }
            for v in request.previous_variants
        ],
        indent=2,
    )

    system_prompt = """You are an expert hotel advertising copywriter. You are refining previously generated ad copy based on user feedback.

RULES:
- Apply the user's feedback precisely.
- Maintain all character limits from the original generation.
- Only change what the feedback requests. Keep everything else intact.
- Every headline and description must still be unique.
- CRITICAL for fb_carousel: Each card_suggestion[i], headline[i], and description[i] MUST correspond to the same card.
  If you change a headline, ensure its card_suggestion still matches, and vice versa.
  card_suggestions[0] = visual for Card 1, headlines[0] = headline for Card 1, descriptions[0] = description for Card 1.
- Output ONLY valid JSON matching the same format as the input."""

    # Build platform specs reminder
    platform_specs_str = ""
    for p in request.platforms:
        spec = PLATFORM_SPECS.get(p, {})
        if spec:
            h_label = spec["headlines"].get("label", "Headlines")
            d_label = spec["descriptions"].get("label", "Descriptions")
            platform_specs_str += f"\n{spec['name']}: {h_label} max {spec['headlines']['max_chars']} chars"
            platform_specs_str += f", {d_label} max {spec['descriptions']['max_chars']} chars"
            if "captions" in spec:
                c_label = spec["captions"].get("label", "Captions")
                platform_specs_str += f", {c_label} max {spec['captions']['max_chars']} chars"

    user_prompt = f"""## CONTEXT:
- Hotel: {request.hotel_name}
- Offer: {request.offer_name}
- Inclusions: {request.inclusions}
{f'- Additional Info: {request.other_info}' if request.other_info else ''}

## CHARACTER LIMITS REMINDER:{platform_specs_str}

## PREVIOUS GENERATED AD COPY:
```json
{previous_output_str}
```

## USER FEEDBACK:
{request.feedback}

## INSTRUCTIONS:
Apply the feedback to the ad copy above. Return the FULL updated JSON array (all platforms, all headlines/descriptions/captions/card_suggestions), not just the changed items. Maintain the same structure.
For fb_carousel: ensure card_suggestions[i] always matches headlines[i] and descriptions[i] (same card index).

```json
[
  {{
    "platform": "platform_name",
    "headlines": ["headline1", ...],
    "descriptions": ["desc1", ...],
    "captions": ["caption1", ...],
    "card_suggestions": ["visual for card matching headline1", ...]
  }}
]
```"""

    model = get_generative_model(model_name, system_instruction=system_prompt)
    response = model.generate_content(user_prompt)

    input_tokens = 0
    output_tokens = 0
    if response.usage_metadata:
        input_tokens = response.usage_metadata.prompt_token_count
        output_tokens = response.usage_metadata.candidates_token_count

    variants = _parse_response(response.text, request.platforms)
    elapsed = round(time.time() - start_time, 2)

    return {
        "variants": variants,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tokens_used": input_tokens + output_tokens,
        "model_used": model_name,
        "time_seconds": elapsed,
    }


def _build_system_prompt(brand_data: dict | None) -> str:
    """Build system prompt with brand guardrails and restricted keywords."""
    base = """You are an expert hotel advertising copywriter. You create high-converting ad copy
for hotel campaigns across Google, Meta/Facebook, and YouTube platforms.

RULES:
- Always follow the exact character limits specified for each platform.
- Every headline and description must be unique - no duplicates.
- Include a clear call-to-action in descriptions.
- Highlight the specific offer/inclusion details prominently.
- Use power words that drive urgency and desire.
- Output ONLY valid JSON matching the requested format."""

    if brand_data:
        if brand_data.get("restricted_keywords"):
            keywords = ", ".join(brand_data["restricted_keywords"])
            base += f"""

STRICT RESTRICTION: Under NO circumstances use any of the following words or phrases in any generated copy:
[{keywords}]
If any of these words appear in your output, the generation will be rejected."""

        if brand_data.get("negative_keywords"):
            neg = ", ".join(brand_data["negative_keywords"])
            base += f"\n\nAVOID these negative keywords: [{neg}]"

    return base


def _build_user_prompt(
    request: AdGenerationRequest,
    ad_insights: dict,
    scraped: dict,
    review_data: dict,
    brand_data: dict | None,
    training_directives: list[dict] | None = None,
    seasonal_context: str = "",
) -> str:
    """Build the user prompt with all gathered context."""

    # Determine objective
    objective = request.campaign_objective
    if not objective:
        objective = "INFER the best campaign objective (Awareness, Consideration, or Conversion) based on the offer details below."

    # Platform specs
    platform_instructions = []
    for p in request.platforms:
        spec = PLATFORM_SPECS.get(p, {})
        if spec:
            lines = [f"\n### {spec['name']}"]
            h_label = spec["headlines"].get("label", "Headlines")
            d_label = spec["descriptions"].get("label", "Descriptions")
            lines.append(f"- {h_label}: {spec['headlines']['count']}x, max {spec['headlines']['max_chars']} chars each")
            d_line = f"- {d_label}: {spec['descriptions']['count']}x, max {spec['descriptions']['max_chars']} chars each"
            if spec["descriptions"].get("min_chars"):
                d_line += f", min {spec['descriptions']['min_chars']} chars each"
            lines.append(d_line)
            if "captions" in spec:
                c_label = spec["captions"].get("label", "Captions")
                lines.append(f"- {c_label}: {spec['captions']['count']}x, max {spec['captions']['max_chars']} chars each")
            platform_instructions.append("\n".join(lines))

    # Carousel card context
    carousel_context = ""
    if "fb_carousel" in request.platforms:
        if request.carousel_mode == "manual" and request.carousel_cards:
            carousel_context = "\n\n## CAROUSEL CARD DETAILS (user-provided descriptions for each card):\n"
            for i, card_desc in enumerate(request.carousel_cards):
                if card_desc.strip():
                    carousel_context += f"  Card {i+1}: {card_desc}\n"
            carousel_context += """
CRITICAL: Each card headline and description MUST match its corresponding card visual above.
- headlines[0] and descriptions[0] MUST be written specifically for Card 1's visual/content.
- headlines[1] and descriptions[1] MUST be written specifically for Card 2's visual/content.
- And so on for each card.
The headline and description for each card should directly reflect what is shown in that card's image/video.
"""
        else:
            carousel_context = """

## CAROUSEL FLOW SUGGESTION:
For the Facebook Carousel, also generate a "card_suggestions" array with one-line recommendations
per card describing what image/video should be shown on each card. Base suggestions on the hotel details and offer.

CRITICAL ALIGNMENT RULE: Each card_suggestion MUST correspond to the headline and description at the SAME index.
- card_suggestions[0] describes the visual for Card 1, and headlines[0] + descriptions[0] must match that visual.
- card_suggestions[1] describes the visual for Card 2, and headlines[1] + descriptions[1] must match that visual.
- And so on for each card.
First decide the visual story flow for the carousel (what each card should show), then write the matching headline
and description for each card based on that visual.

Example: If card_suggestions[0] = "Hotel facade with a model walking towards the entrance", then headlines[0]
should be about arrival/welcome, NOT about spa or dining.

Generate exactly 5 card suggestions, 5 matching headlines, and 5 matching descriptions — all aligned by index."""

    # Historical ad performance insights
    historical_context = ""
    if ad_insights and ad_insights.get("insight_text"):
        historical_context = f"\n\n## HISTORICAL AD PERFORMANCE INSIGHTS ({ad_insights.get('total_ads_analyzed', 0)} ads analyzed):\n"
        historical_context += ad_insights["insight_text"]

        if ad_insights.get("top_headlines"):
            historical_context += "\n\n### Top-Performing Headlines (use as style reference):\n"
            for h in ad_insights["top_headlines"][:5]:
                historical_context += f"- {h}\n"

        if ad_insights.get("top_descriptions"):
            historical_context += "\n### Top-Performing Descriptions:\n"
            for d in ad_insights["top_descriptions"][:5]:
                historical_context += f"- {d}\n"

        if ad_insights.get("patterns"):
            historical_context += "\n### Key Patterns:\n"
            for p in ad_insights["patterns"][:5]:
                historical_context += f"- {p}\n"

    # Training directive context (admin-approved AI insights)
    training_context = ""
    if training_directives:
        for td in training_directives:
            content = td.get("content", {})
            if content.get("insight_text"):
                training_context += f"\n\n## TRAINING DIRECTIVES (admin-approved):\n{content['insight_text']}"
            if content.get("recommended_tone"):
                training_context += f"\nRecommended Tone: {content['recommended_tone']}"
            if content.get("power_words"):
                training_context += "\nPower Words: " + ", ".join(content["power_words"][:10])
            if content.get("avoid_words"):
                training_context += "\nWords to Avoid: " + ", ".join(content["avoid_words"][:10])

    # Brand USP context
    usp_context = ""
    if brand_data:
        if brand_data.get("usps"):
            usp_context += f"\n\n## BRAND USPs (must incorporate):\n- " + "\n- ".join(brand_data["usps"])
        if brand_data.get("positive_keywords"):
            usp_context += f"\n\n## PREFERRED KEYWORDS:\n- " + "\n- ".join(brand_data["positive_keywords"])

    # Review insights
    review_context = ""
    if review_data.get("insights") and review_data.get("review_count", 0) > 0:
        review_context = f"\n\n## GUEST REVIEW INSIGHTS ({review_data.get('overall_rating', 'N/A')}★ rating):\n{review_data['insights']}"

    # Scraped website content
    website_context = ""
    if scraped.get("content"):
        website_context = f"\n\n## HOTEL WEBSITE CONTENT ({scraped.get('urls_scraped', 1)} pages analyzed):\n{scraped['content'][:5000]}"

    # Objective weighting
    weighting = ""
    if objective == "Awareness" or objective.startswith("INFER"):
        weighting = "\nEMPHASIS: Heavily weight USPs, brand differentiators, and review insights for maximum brand awareness."

    prompt = f"""Generate hotel ad copy with the following details:

## HOTEL DETAILS:
- Hotel Name: {request.hotel_name}
- Offer Name: {request.offer_name}
- Inclusions: {request.inclusions}
- Campaign Objective: {objective}
{f'- Additional Info: {request.other_info}' if request.other_info else ''}
{weighting}

## PLATFORM REQUIREMENTS:
{"".join(platform_instructions)}
{carousel_context}
{historical_context}
{training_context}
{usp_context}
{review_context}
{website_context}
{seasonal_context}

## OUTPUT FORMAT:
Return ONLY a JSON array where each element represents a platform:
```json
[
  {{
    "platform": "platform_name",
    "headlines": ["headline1", "headline2", ...],
    "descriptions": ["desc1", "desc2", ...],
    "captions": ["caption1", ...]  // only if platform requires captions
  }}
]
```

Ensure EVERY headline and description respects the character limits specified above. Count characters carefully."""

    return prompt


def _parse_response(response_text: str, platforms: list[str]) -> list[AdCopyOutput]:
    """Parse LLM response JSON into AdCopyOutput objects."""
    # Extract JSON from response (may be wrapped in markdown code blocks)
    json_str = response_text
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0]
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0]

    try:
        data = json.loads(json_str.strip())
    except json.JSONDecodeError:
        # Fallback: return raw text as single description
        return [
            AdCopyOutput(
                platform=platforms[0] if platforms else "unknown",
                headlines=["Ad copy generation completed"],
                descriptions=[response_text[:500]],
            )
        ]

    variants = []
    for item in data:
        variants.append(
            AdCopyOutput(
                platform=item.get("platform", "unknown"),
                headlines=item.get("headlines", []),
                descriptions=item.get("descriptions", []),
                captions=item.get("captions"),
                card_suggestions=item.get("card_suggestions"),
            )
        )
    return variants
