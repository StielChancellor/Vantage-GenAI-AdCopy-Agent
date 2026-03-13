"""Ad copy generation using Gemini with RAG context, brand guardrails, and platform optimization."""
import json
from datetime import datetime, timezone

import google.generativeai as genai

from backend.app.core.config import get_settings
from backend.app.services.rag_engine import retrieve_top_ads, get_brand_usps
from backend.app.services.scraper import scrape_hotel_page
from backend.app.services.reviews import fetch_google_reviews
from backend.app.models.schemas import AdGenerationRequest, AdGenerationResponse, AdCopyOutput

settings = get_settings()

# Platform character limits
PLATFORM_SPECS = {
    "google_search": {
        "name": "Google Search Ads",
        "headlines": {"count": 15, "max_chars": 30},
        "descriptions": {"count": 4, "max_chars": 90},
    },
    "meta_carousel": {
        "name": "Meta Carousel Ads",
        "headlines": {"count": 5, "max_chars": 40},
        "descriptions": {"count": 5, "max_chars": 125},
        "captions": {"count": 5, "max_chars": 2200},
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


async def generate_ad_copy(request: AdGenerationRequest) -> AdGenerationResponse:
    """Full ad copy generation pipeline."""
    genai.configure(api_key=settings.GEMINI_API_KEY)

    # 1. Gather context in parallel-ish fashion
    # RAG: retrieve historical top performers
    top_ads = retrieve_top_ads(request.hotel_name)

    # Brand USPs & guardrails
    brand_data = get_brand_usps(request.hotel_name)

    # Scrape reference URL
    scraped = {}
    try:
        scraped = await scrape_hotel_page(request.reference_url)
    except Exception:
        scraped = {"content": "Could not scrape reference URL.", "title": ""}

    # Google Reviews insights
    review_data = {}
    try:
        review_data = await fetch_google_reviews(
            request.google_listing_url, request.hotel_name
        )
    except Exception:
        review_data = {"insights": "No review data available.", "review_count": 0}

    # 2. Build the system prompt with guardrails
    system_prompt = _build_system_prompt(brand_data)

    # 3. Build the user prompt with all context
    user_prompt = _build_user_prompt(
        request=request,
        top_ads=top_ads,
        scraped=scraped,
        review_data=review_data,
        brand_data=brand_data,
    )

    # 4. Call Gemini
    model = genai.GenerativeModel(
        request.model_name,
        system_instruction=system_prompt,
    )

    response = model.generate_content(user_prompt)

    # 5. Parse response and calculate tokens
    tokens_used = 0
    if response.usage_metadata:
        tokens_used = (
            response.usage_metadata.prompt_token_count
            + response.usage_metadata.candidates_token_count
        )

    variants = _parse_response(response.text, request.platforms)

    return AdGenerationResponse(
        hotel_name=request.hotel_name,
        variants=variants,
        tokens_used=tokens_used,
        model_used=request.model_name,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def _build_system_prompt(brand_data: dict | None) -> str:
    """Build system prompt with brand guardrails and restricted keywords."""
    base = """You are an expert hotel advertising copywriter. You create high-converting ad copy
for hotel campaigns across Google, Meta, and YouTube platforms.

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
    top_ads: list[dict],
    scraped: dict,
    review_data: dict,
    brand_data: dict | None,
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
            lines.append(f"- Headlines: {spec['headlines']['count']}x, max {spec['headlines']['max_chars']} chars each")
            lines.append(f"- Descriptions: {spec['descriptions']['count']}x, max {spec['descriptions']['max_chars']} chars each")
            if "captions" in spec:
                lines.append(f"- Captions: {spec['captions']['count']}x, max {spec['captions']['max_chars']} chars each")
            platform_instructions.append("\n".join(lines))

    # Historical ad context
    historical_context = ""
    if top_ads:
        historical_context = "\n\n## TOP PERFORMING HISTORICAL ADS (use as style reference):\n"
        for i, ad in enumerate(top_ads[:3]):
            historical_context += f"\nAd {i+1} (CTR: {ad.get('ctr', 0)}%, CVR: {ad.get('cvr', 0)}%):\n"
            historical_context += f"  Headlines: {ad.get('headlines', '')}\n"
            historical_context += f"  Descriptions: {ad.get('descriptions', '')}\n"

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
        website_context = f"\n\n## HOTEL WEBSITE CONTENT:\n{scraped['content'][:3000]}"

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
{historical_context}
{usp_context}
{review_context}
{website_context}

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
            )
        )
    return variants
