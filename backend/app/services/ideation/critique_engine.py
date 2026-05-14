"""Critique engine for Campaign Ideation (v2.7).

Acts as a senior brand-marketing critique partner. Given the user's theme +
existing Q/A turns, returns ONE next question (or marks ready_for_shortlist).
Required topics covered before completion: audience, hero_offer, tone,
must_mention, must_avoid. Remainder filled dynamically. Hard cap at 7 turns.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("vantage.ideation.critique")


_REQUIRED_TOPICS = ("audience", "hero_offer", "tone", "must_mention", "must_avoid")
_MAX_TURNS = 7


_SYSTEM_PROMPT = """You are a senior brand-marketing critique partner for a luxury hospitality group.

GOAL
Sharpen a campaign brief through ONE focused question at a time. Be incisive but warm. Never deliver more than one question per turn. Never ask about anything that has already been answered.

REQUIRED TOPICS (every brief must cover before completion):
- audience       — who the campaign is for (segment, age, traveller type)
- hero_offer     — the single most compelling element of the offer
- tone           — voice register (e.g., refined, playful, indulgent)
- must_mention   — non-negotiable elements/USPs to surface
- must_avoid     — claims, themes, or wording to keep out

GUARDRAILS
- Hard cap: 7 total questions across the whole conversation.
- If all required topics are captured AND you have enough texture for a creative team, set ready_for_shortlist=true and leave next_question empty.
- Adapt remaining questions to the theme (e.g., for "Monsoon" ask about visual atmosphere; for "Independence Day" ask about respectful framing).
- Update the `captured` object with anything you can infer from the user's most recent answer. Use "" when not yet captured.

OUTPUT — return ONLY valid JSON in exactly this schema:
{
  "next_question": "single question, ≤ 28 words, OR empty string if ready",
  "ready_for_shortlist": false,
  "captured": {
    "audience": "",
    "hero_offer": "",
    "tone": "",
    "must_mention": "",
    "must_avoid": "",
    "extras": ""
  }
}
"""


async def next_critique_turn(
    theme_text: str,
    date_start: str | None,
    date_end: str | None,
    scope_summary: str,
    turns: list[dict],
    captured: dict | None = None,
) -> dict:
    """Drive one critique turn. `turns` is the accumulated list of {q, a} pairs.

    Returns {next_question, ready_for_shortlist, captured, tokens_used, model_used}.
    """
    from backend.app.core.vertex_client import (
        get_generative_model, extract_token_counts,
    )

    captured = captured or {}
    turns = turns or []

    # Force-end if we've already hit the hard cap.
    answered = sum(1 for t in turns if (t.get("a") or "").strip())
    if answered >= _MAX_TURNS:
        return {
            "next_question": "",
            "ready_for_shortlist": True,
            "captured": captured,
            "tokens_used": 0,
            "model_used": "",
        }

    user_prompt = _build_user_prompt(
        theme_text=theme_text,
        date_start=date_start or "",
        date_end=date_end or "",
        scope_summary=scope_summary or "",
        turns=turns,
        captured=captured,
        questions_so_far=len(turns),
    )

    try:
        model = get_generative_model(system_instruction=_SYSTEM_PROMPT)
        response = model.generate_content(user_prompt)
        raw = getattr(response, "text", "") or ""
        in_tok, out_tok = extract_token_counts(response)
        model_name = getattr(model, "_model_name", "") or "gemini-3.1-pro-preview"
    except Exception as exc:
        logger.warning("critique LLM call failed: %s", exc)
        return _fallback_turn(turns, captured)

    parsed = _parse_json(raw)
    if not parsed:
        return _fallback_turn(turns, captured)

    # Merge captured: never let an existing non-empty value get overwritten by "".
    merged: dict = dict(captured)
    for k, v in (parsed.get("captured") or {}).items():
        if isinstance(v, str) and v.strip():
            merged[k] = v.strip()
        elif k not in merged:
            merged[k] = ""

    ready = bool(parsed.get("ready_for_shortlist", False))
    next_q = (parsed.get("next_question") or "").strip()

    # Force ready when the model returns no follow-up and the required topics are present.
    if not next_q and all(merged.get(t) for t in _REQUIRED_TOPICS):
        ready = True

    # Force ready at the hard cap, regardless of model output.
    if len(turns) + (0 if ready or not next_q else 1) >= _MAX_TURNS and all(merged.get(t) for t in _REQUIRED_TOPICS):
        ready = True
        next_q = ""

    return {
        "next_question": "" if ready else next_q,
        "ready_for_shortlist": ready,
        "captured": merged,
        "tokens_used": in_tok + out_tok,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "model_used": model_name,
    }


def _build_user_prompt(
    theme_text: str,
    date_start: str,
    date_end: str,
    scope_summary: str,
    turns: list[dict],
    captured: dict,
    questions_so_far: int,
) -> str:
    parts: list[str] = []
    parts.append(f"THEME: {theme_text}")
    if date_start or date_end:
        parts.append(f"DATES: {date_start or '?'} → {date_end or '?'}")
    if scope_summary:
        parts.append(f"SCOPE: {scope_summary}")
    parts.append(f"QUESTIONS ASKED SO FAR: {questions_so_far} (cap: {_MAX_TURNS})")
    parts.append(f"CAPTURED SO FAR:\n{json.dumps(captured, indent=2)}")

    if turns:
        parts.append("CONVERSATION HISTORY:")
        for i, t in enumerate(turns, 1):
            parts.append(f"Q{i}: {t.get('q', '')}")
            parts.append(f"A{i}: {t.get('a', '')}")
    else:
        parts.append("CONVERSATION HISTORY: (none yet — produce the FIRST critique question)")

    parts.append(
        "\nRespond with the next single question that most sharpens the brief, "
        "or set ready_for_shortlist=true if all required topics are captured. "
        "Return JSON only."
    )
    return "\n".join(parts)


def _parse_json(text: str) -> dict:
    if not text:
        return {}
    raw = text.strip()
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in raw:
        raw = raw.split("```", 1)[1].split("```", 1)[0]
    try:
        data = json.loads(raw.strip())
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        logger.debug("critique JSON parse failed; raw=%s", raw[:300])
    return {}


def _fallback_turn(turns: list[dict], captured: dict) -> dict:
    """Deterministic fallback — walk the required topics that haven't been captured."""
    for t in _REQUIRED_TOPICS:
        if not (captured or {}).get(t):
            qmap = {
                "audience": "Who is this campaign primarily for — describe the traveller in one sentence?",
                "hero_offer": "What's the single most compelling element of the offer or experience?",
                "tone": "What tone should the copy strike — refined, playful, indulgent, urgent, or something else?",
                "must_mention": "Are there non-negotiable USPs or elements that must appear in every concept?",
                "must_avoid": "Anything we must NOT say or imply — claims, themes, wording?",
            }
            return {
                "next_question": qmap.get(t, "Tell me more about what success looks like here."),
                "ready_for_shortlist": False,
                "captured": captured,
                "tokens_used": 0,
                "model_used": "fallback",
            }
    return {
        "next_question": "",
        "ready_for_shortlist": True,
        "captured": captured,
        "tokens_used": 0,
        "model_used": "fallback",
    }
