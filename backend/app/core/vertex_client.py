"""Vertex AI singleton client for Vantage v2.0.

Replaces google-generativeai SDK. All services call get_generative_model()
instead of genai.GenerativeModel(). Uses Application Default Credentials
(no API key) — auth is handled by the Cloud Run service account.

v2.7 — supports Anthropic Claude via Vertex AI Model Garden. When the
resolved model name starts with `claude-`, an adapter that quacks like
`GenerativeModel` (text-only — same `.generate_content(prompt)` signature
and response shape) is returned. Vision and grounded-search call sites
must keep an explicit Gemini model name.
"""
import logging
import os
import threading
from functools import lru_cache

import vertexai
from vertexai.generative_models import GenerativeModel

logger = logging.getLogger("vantage.vertex")

_init_lock = threading.Lock()
_initialized = False
_anthropic_client = None
_anthropic_lock = threading.Lock()


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


# ── Anthropic Claude on Vertex AI Model Garden ────────────────────────
# Map user-facing model ids (kept stable in admin_settings) → Vertex
# publisher ids with the required dated suffix. Override any entry via the
# matching env var if Anthropic ships a newer revision.
_CLAUDE_VERTEX_IDS: dict[str, str] = {}


def _claude_vertex_id(model_name: str) -> str:
    """Resolve a friendly Claude id to the Vertex publisher id Anthropic
    actually accepts (e.g. `claude-opus-4-7@20251101`)."""
    if not _CLAUDE_VERTEX_IDS:
        _CLAUDE_VERTEX_IDS["claude-opus-4-7"] = os.environ.get(
            "CLAUDE_OPUS_4_7_VERTEX_ID", "claude-opus-4-7@20251101",
        )
        _CLAUDE_VERTEX_IDS["claude-sonnet-4-6"] = os.environ.get(
            "CLAUDE_SONNET_4_6_VERTEX_ID", "claude-sonnet-4-6@20251015",
        )
        _CLAUDE_VERTEX_IDS["claude-haiku-4-5"] = os.environ.get(
            "CLAUDE_HAIKU_4_5_VERTEX_ID", "claude-haiku-4-5-20251001",
        )
    return _CLAUDE_VERTEX_IDS.get(model_name, model_name)


def _get_anthropic_client():
    """Lazy-init the AnthropicVertex SDK. Claude on Vertex is available in
    `us-east5` / `europe-west1` / `asia-southeast1` — NOT in `us-central1`,
    so we keep a dedicated region pin."""
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    with _anthropic_lock:
        if _anthropic_client is not None:
            return _anthropic_client
        from anthropic import AnthropicVertex
        project = os.environ.get("GCP_PROJECT_ID", "supple-moon-495404-b0")
        region = os.environ.get("VERTEX_AI_CLAUDE_LOCATION", "us-east5")
        _anthropic_client = AnthropicVertex(region=region, project_id=project)
    return _anthropic_client


class _UsageMetadata:
    """Mimics vertexai.generative_models.UsageMetadata."""
    __slots__ = ("prompt_token_count", "candidates_token_count")

    def __init__(self, input_tokens: int, output_tokens: int):
        self.prompt_token_count = int(input_tokens or 0)
        self.candidates_token_count = int(output_tokens or 0)


class _AnthropicResponse:
    """Quacks like a vertexai GenerateContentResponse for downstream callers.

    Exposes `.text` (joined text blocks) and `.usage_metadata` with the same
    field names Vertex/Gemini uses, so `extract_token_counts(response)` and
    callers reading `response.text` work unchanged.
    """

    def __init__(self, raw):
        self._raw = raw
        # Anthropic returns a list of content blocks (text / tool_use / …).
        # For text-only generation we concat block.text from every text block.
        try:
            parts = []
            for block in (raw.content or []):
                btext = getattr(block, "text", None)
                if btext:
                    parts.append(btext)
            self.text = "".join(parts)
        except Exception:
            self.text = ""
        usage = getattr(raw, "usage", None)
        self.usage_metadata = _UsageMetadata(
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
        )


class _ClaudeModelAdapter:
    """Drop-in for `GenerativeModel` when the selected default is Claude.

    Supports `.generate_content(prompt)` where `prompt` is a string or a
    list of strings. NOT supported: multimodal Part inputs (image bytes,
    Google-search grounding tools). Vision and grounded callsites must
    keep an explicit Gemini model id — see `caption_image` in
    static_asset_adapter and `event_search`.
    """

    def __init__(self, model_name: str, system_instruction: str | None = None):
        self._model_name = model_name           # friendly id, e.g. claude-opus-4-7
        self._vertex_id = _claude_vertex_id(model_name)
        self._system = system_instruction or ""
        self._max_tokens = int(os.environ.get("CLAUDE_MAX_OUTPUT_TOKENS", "4096"))

    def generate_content(self, prompt):
        client = _get_anthropic_client()

        if isinstance(prompt, str):
            user_text = prompt
        elif isinstance(prompt, (list, tuple)):
            parts: list[str] = []
            for p in prompt:
                if isinstance(p, str):
                    parts.append(p)
                else:
                    raise NotImplementedError(
                        "Claude adapter does not support multimodal Parts. "
                        "Pin this callsite to a Gemini model id."
                    )
            user_text = "\n".join(parts)
        else:
            raise TypeError(f"Unsupported prompt type for Claude: {type(prompt)}")

        kwargs = {
            "model": self._vertex_id,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": user_text}],
        }
        if self._system:
            kwargs["system"] = self._system

        raw = client.messages.create(**kwargs)
        return _AnthropicResponse(raw)


def get_generative_model(
    model_name: str | None = None,
    system_instruction: str | None = None,
    **kwargs,
):
    """Return a configured generation client.

    For Gemini ids → returns a `vertexai.generative_models.GenerativeModel`.
    For Claude ids (anything starting with `claude-`) → returns a
    `_ClaudeModelAdapter` that exposes the same `.generate_content` and
    response shape (text-only).
    """
    _ensure_init()

    if model_name is None:
        model_name = _resolve_model()

    if isinstance(model_name, str) and model_name.startswith("claude-"):
        if kwargs:
            logger.debug("Claude adapter ignores extra kwargs: %s", list(kwargs))
        return _ClaudeModelAdapter(model_name, system_instruction=system_instruction)

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
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 3.50, "output": 10.50},
    # Anthropic Claude on Vertex AI Model Garden — billed per token.
    "claude-opus-4-7": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
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
