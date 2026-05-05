"""Vertex AI singleton client for Vantage v2.0.

Replaces google-generativeai SDK. All services call get_generative_model()
instead of genai.GenerativeModel(). Uses Application Default Credentials
(no API key) — auth is handled by the Cloud Run service account.
"""
import os
import threading
from functools import lru_cache

import vertexai
from vertexai.generative_models import GenerativeModel

_init_lock = threading.Lock()
_initialized = False


def _ensure_init() -> None:
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        project = os.environ.get("GCP_PROJECT_ID", "supple-moon-495404-b0")
        location = os.environ.get("VERTEX_AI_LOCATION", "us-central1")
        vertexai.init(project=project, location=location)
        _initialized = True


def get_generative_model(
    model_name: str | None = None,
    system_instruction: str | None = None,
    **kwargs,
) -> GenerativeModel:
    """Return a configured GenerativeModel instance.

    Args:
        model_name: Override model. Defaults to GEMINI_MODEL env var
                    (gemini-3.1-pro-preview).
        system_instruction: Optional system prompt string.
        **kwargs: Additional GenerativeModel constructor kwargs.
    """
    _ensure_init()

    if model_name is None:
        model_name = _resolve_model()

    init_kwargs = dict(kwargs)
    if system_instruction:
        init_kwargs["system_instruction"] = system_instruction

    return GenerativeModel(model_name, **init_kwargs)


@lru_cache(maxsize=1)
def _resolve_model() -> str:
    """Resolve the default model from Firestore admin settings, fall back to env."""
    default = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
    try:
        # Lazy import to avoid circular dependency
        from backend.app.core.database import get_firestore
        db = get_firestore()
        doc = db.collection("admin_settings").document("config").get()
        if doc.exists:
            stored = doc.to_dict().get("default_model")
            if stored:
                return stored
    except Exception:
        pass
    return default


def invalidate_model_cache() -> None:
    """Call after admin updates the default model setting."""
    _resolve_model.cache_clear()


# Pricing per million tokens (USD) — updated for Gemini 3.x models
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gemini-3.1-pro-preview": {"input": 3.50, "output": 14.00},
    "gemini-2.5-pro-preview": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-pro": {"input": 3.50, "output": 10.50},
}

USD_TO_INR = 85


def calculate_cost_inr(model_name: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model_name, MODEL_PRICING["gemini-3.1-pro-preview"])
    cost_usd = (
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"]
    )
    return round(cost_usd * USD_TO_INR, 4)


def extract_token_counts(response) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from a GenerateContentResponse."""
    try:
        meta = response.usage_metadata
        return meta.prompt_token_count or 0, meta.candidates_token_count or 0
    except Exception:
        return 0, 0
