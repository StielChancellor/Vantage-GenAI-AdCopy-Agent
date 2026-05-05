"""A/B variant generator — produces multiple ad variants and ranks them.

Generates N variants using different creative angles (hook, CTA, emotional tone),
then scores each with performance_predictor.py. Returns ranked variants.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date

logger = logging.getLogger("vantage.ab_testing")

_VARIANT_ANGLES = [
    "urgency_and_scarcity",
    "emotional_benefit",
    "rational_value",
]

_ANGLE_INSTRUCTIONS = {
    "urgency_and_scarcity": "Focus on limited availability, time-sensitive pricing, and urgency ('Last few rooms', 'Offer ends soon', 'Book now before it's gone').",
    "emotional_benefit": "Focus on emotional outcomes: how the guest will FEEL. Use sensory language, aspirational imagery, and emotional resonance ('Wake up to breathtaking views', 'Create memories that last a lifetime').",
    "rational_value": "Focus on concrete value: what's included, savings, and tangible benefits ('Save 30% with breakfast included', 'All-inclusive from ₹X per night', 'Free airport transfer + spa access').",
}


@dataclass
class RankedVariant:
    angle: str
    platform: str
    headlines: list[str]
    descriptions: list[str]
    captions: list[str] | None
    card_suggestions: list[str] | None
    score: float
    score_breakdown: dict = field(default_factory=dict)
    score_explanation: str = ""


async def generate_ranked_variants(
    request,  # AdGenerationRequest
    base_prompt: str,
    system_prompt: str,
    platform_specs: dict,
    flight_date: date | str | None = None,
    n_variants: int = 3,
) -> list[RankedVariant]:
    """Generate N variants with different angles, score each, return ranked list.

    Falls back to single variant if multi-variant generation fails.
    """
    from backend.app.core.vertex_client import get_generative_model
    from backend.app.services.ad_testing.performance_predictor import score_variant

    variants: list[RankedVariant] = []
    angles = _VARIANT_ANGLES[:n_variants]

    for angle in angles:
        try:
            angle_prompt = (
                base_prompt
                + f"\n\n## CREATIVE ANGLE FOR THIS VARIANT:\n{_ANGLE_INSTRUCTIONS[angle]}\n"
                + "Ensure all copy in this variant strongly reflects the angle above."
            )
            model = get_generative_model(system_instruction=system_prompt)
            response = model.generate_content(angle_prompt)

            parsed = _parse_variant_response(response.text, request.platforms)

            for platform_variant in parsed:
                platform = platform_variant.get("platform", "unknown")
                headlines = platform_variant.get("headlines", [])
                descriptions = platform_variant.get("descriptions", [])

                from backend.app.services.ab_testing.performance_predictor import score_variant as _score
                score_result = _score(
                    headlines=headlines,
                    descriptions=descriptions,
                    platform=platform,
                    brand_id=request.hotel_name,
                    flight_date=flight_date,
                )

                variants.append(RankedVariant(
                    angle=angle,
                    platform=platform,
                    headlines=headlines,
                    descriptions=descriptions,
                    captions=platform_variant.get("captions"),
                    card_suggestions=platform_variant.get("card_suggestions"),
                    score=score_result.score,
                    score_breakdown={
                        "semantic": score_result.semantic_score,
                        "structural": score_result.structural_score,
                        "seasonal": score_result.seasonal_score,
                    },
                    score_explanation=score_result.explanation,
                ))
        except Exception as exc:
            logger.warning("Variant generation failed for angle '%s': %s", angle, exc)

    # Sort by score descending
    variants.sort(key=lambda v: v.score, reverse=True)
    return variants


def _parse_variant_response(text: str, platforms: list[str]) -> list[dict]:
    """Extract JSON array from Gemini response."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return [{"platform": platforms[0] if platforms else "unknown", "headlines": [], "descriptions": []}]
