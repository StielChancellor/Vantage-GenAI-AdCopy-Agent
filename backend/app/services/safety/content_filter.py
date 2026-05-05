"""Content safety filter for generated ad copy and CRM messages.

Checks Vertex AI safety ratings from GenerateContentResponse and applies
a hospitality-specific custom blocklist. Logs filtered content to BigQuery.
"""
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("vantage.safety")

# Hospitality-specific prohibited phrases (unsubstantiated absolute claims)
_HOSPITALITY_BLOCKLIST = [
    "best hotel in the world",
    "number one hotel",
    "world's best",
    "unmatched anywhere",
    "100% satisfaction guaranteed",
    "no other hotel",
]

# Vertex AI harm categories to check (from google.cloud.aiplatform types)
_BLOCKED_CATEGORIES = {
    "HARM_CATEGORY_DANGEROUS_CONTENT",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
}

# Threshold: block if rating >= MEDIUM (value 3 in Vertex AI enum)
_BLOCK_THRESHOLD = 3


@dataclass
class FilterResult:
    passed: bool
    text: str
    blocked_reason: str = ""
    harm_category: str = ""


def check_response(
    response: Any,
    brand_id: str = "",
    user_id: str = "",
    request_type: str = "",
) -> FilterResult:
    """Inspect a Vertex AI GenerateContentResponse for safety issues.

    Returns FilterResult with passed=True if content is safe, False otherwise.
    Logs blocked events to BigQuery asynchronously.
    """
    # Check Vertex AI built-in safety ratings
    try:
        for candidate in response.candidates:
            for rating in candidate.safety_ratings:
                category_name = rating.category.name if hasattr(rating.category, "name") else str(rating.category)
                if category_name in _BLOCKED_CATEGORIES:
                    probability = rating.probability.value if hasattr(rating.probability, "value") else int(rating.probability)
                    if probability >= _BLOCK_THRESHOLD:
                        result = FilterResult(
                            passed=False,
                            text="",
                            blocked_reason="safety_rating",
                            harm_category=category_name,
                        )
                        _log_blocked(result, brand_id, user_id, request_type)
                        return result
    except Exception as exc:
        logger.warning("Could not check safety ratings: %s", exc)

    # Extract text for custom blocklist check
    try:
        text = response.text
    except Exception:
        return FilterResult(passed=True, text="")

    lower = text.lower()
    for phrase in _HOSPITALITY_BLOCKLIST:
        if phrase in lower:
            result = FilterResult(
                passed=False,
                text=text,
                blocked_reason="custom_blocklist",
                harm_category=f"prohibited_phrase:{phrase}",
            )
            _log_blocked(result, brand_id, user_id, request_type)
            return result

    return FilterResult(passed=True, text=text)


def _log_blocked(result: FilterResult, brand_id: str, user_id: str, request_type: str) -> None:
    content_hash = hashlib.sha256(result.text.encode()).hexdigest()[:16]
    logger.warning(
        "Content blocked",
        extra={
            "json_fields": {
                "brand_id": brand_id,
                "user_id": user_id,
                "category": result.harm_category,
                "reason": result.blocked_reason,
                "content_hash": content_hash,
            }
        },
    )
    # Async log to BigQuery (best effort — import here to avoid circular deps)
    try:
        from backend.app.services.analytics.audit_logger import log_safety_event
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(
                log_safety_event(
                    brand_id=brand_id,
                    user_id=user_id,
                    category=result.harm_category,
                    severity=result.blocked_reason,
                    content_hash=content_hash,
                    blocked=True,
                )
            )
    except Exception:
        pass
