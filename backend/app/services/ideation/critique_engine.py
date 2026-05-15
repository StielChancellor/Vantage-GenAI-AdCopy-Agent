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

# Keywords used to infer which required topic a question was about, so we can
# always persist the user's most recent answer into the right slot — even when
# the model's structured-output extraction is weak.
_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "audience":     ("audience", "traveller", "traveler", "guest", "for who", "for whom", "demographic", "segment"),
    "hero_offer":   ("hero offer", "compelling element", "offer", "experience", "promotion", "deal", "incentive"),
    "tone":         ("tone", "voice", "register", "feel", "mood of the copy", "personality"),
    "must_mention": ("must mention", "must-mention", "non-negotiable", "must include", "always include", "have to mention", "usps"),
    "must_avoid":   ("must avoid", "must-avoid", "must not", "avoid", "never say", "exclude", "off-limits", "off limits"),
}


_SYSTEM_PROMPT = """You are a senior campaign coach for a luxury hospitality group. You are having a NORMAL CHAT with a marketing colleague — not running an interrogation.

VOICE
- Talk like a calm, experienced colleague — warm, brief, no jargon.
- Mirror the user's language. If they say "family", say "family" back, don't say "multi-generational traveller segment".
- Replies are 1–3 short sentences. ONE acknowledgement + ONE next nudge, max. No bullet points, no preamble, no role play.
- It's fine to skip the question entirely on a turn and just reflect what you heard, IF that moves the conversation forward better than a question would.

THE FIVE THINGS YOU NEED TO LEAVE THE CHAT WITH
(track silently — the user does not see these slot names)
- audience       — who the campaign is for (parents, couples, retirees, weddings, …)
- hero_offer     — the most compelling element of the experience or deal
- tone           — voice register (refined, playful, indulgent, urgent, celebratory …)
- must_mention   — anything non-negotiable that must surface in every concept
- must_avoid     — anything that must NEVER appear

ABSOLUTE RULES (violating any of these breaks the product)
1. Read the FULL conversation history below. Look at "TOPICS ALREADY COVERED" — NEVER ask another question whose intent maps to a covered topic. If audience is covered (even with one word like "family"), do not ask about audience again — move to a different slot.
2. Treat short answers as real signal. "family" IS an audience. "luxury" IS a tone. Capture it.
3. If you genuinely need a sharper version of an answer, do it ONCE per topic, then move on regardless of what you got. Never drill into the same topic twice.
4. When all five slots have ANY non-empty value, set ready_for_shortlist=true and write a one-line closer like "Got it — let me pull together ten directions." Do not ask another question.
5. Output is JSON only. No prose around it.

OUTPUT FORMAT — JSON only:
{
  "next_question": "your conversational reply (acknowledgement + next nudge), OR empty string if ready",
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

    # Always run capture-from-last-answer first: if the user just answered Q,
    # infer the topic Q was about and store the answer in captured[topic]
    # (unless already non-empty). This is the single most important defence
    # against the "model re-asks the same question" failure mode.
    safe_captured = _infer_captured_from_turns(turns, captured)

    if not parsed:
        return _fallback_turn(turns, safe_captured)

    # Merge captured: never let an existing non-empty value get overwritten by "".
    merged: dict = dict(safe_captured)
    for k, v in (parsed.get("captured") or {}).items():
        if isinstance(v, str) and v.strip():
            merged[k] = v.strip()
        elif k not in merged:
            merged[k] = ""

    ready = bool(parsed.get("ready_for_shortlist", False))
    next_q = (parsed.get("next_question") or "").strip()

    # Dup-guard v2: refuse any next-question whose topic is already covered
    # (captured non-empty OR previously asked). Catches paraphrases that the
    # plain text dup-check would miss. If a replacement is needed and every
    # topic is captured, we declare ready.
    asked_qs = [(t.get("q") or "").strip() for t in turns]
    if next_q:
        next_q_topic = _infer_topic_for_question(next_q)
        text_dup = _is_duplicate_question(next_q, asked_qs)
        covered_topics = (
            {k for k, v in (merged or {}).items() if isinstance(v, str) and v.strip()}
            | {_infer_topic_for_question(q) for q in asked_qs if _infer_topic_for_question(q)}
        )
        topic_already_covered = next_q_topic is not None and next_q_topic in covered_topics
        if text_dup or topic_already_covered:
            replacement = _next_unmet_question(merged, asked_qs)
            if replacement:
                logger.info(
                    "critique: replaced %s question (topic=%s)",
                    "duplicate" if text_dup else "already-covered",
                    next_q_topic,
                )
                next_q = replacement
            else:
                ready = True
                next_q = ""

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


def _infer_topic_for_question(question: str) -> str | None:
    """Match a question's text to a required-topic key via keyword overlap.
    Returns the first matching topic or None."""
    q = (question or "").lower()
    for topic, kws in _TOPIC_KEYWORDS.items():
        for kw in kws:
            if kw in q:
                return topic
    return None


def _infer_captured_from_turns(turns: list[dict], captured: dict) -> dict:
    """For every answered turn, if we can identify which required topic the
    question was about AND the slot is still empty in `captured`, store the
    user's answer there. Guarantees forward progress even when Gemini's
    structured extraction misses a slot."""
    out = dict(captured or {})
    for t in turns:
        q = (t.get("q") or "").strip()
        a = (t.get("a") or "").strip()
        if not q or not a:
            continue
        topic = _infer_topic_for_question(q)
        if not topic:
            continue
        if not (out.get(topic) or "").strip():
            out[topic] = a
    # Make sure every required key exists (empty string is fine).
    for t in _REQUIRED_TOPICS:
        out.setdefault(t, "")
    return out


def _normalise_q(s: str) -> str:
    """Lowercase + collapse whitespace + strip trailing punctuation for cheap dup-check."""
    import re
    return re.sub(r"\s+", " ", (s or "").lower().strip(" ?.!,;:—-"))


def _is_duplicate_question(new_q: str, asked_qs: list[str]) -> bool:
    """Return True if `new_q` is identical or a strong prefix match of any
    previously asked question (and vice versa)."""
    n = _normalise_q(new_q)
    if len(n) < 8:
        return False
    for prev in asked_qs:
        p = _normalise_q(prev)
        if not p:
            continue
        if n == p:
            return True
        # Treat as duplicate if one is a prefix of the other and they share
        # most of their length (handles minor rephrasings).
        shorter, longer = (n, p) if len(n) < len(p) else (p, n)
        if longer.startswith(shorter) and len(shorter) >= 0.7 * len(longer):
            return True
    return False


def _next_unmet_question(captured: dict, asked_qs: list[str]) -> str | None:
    """Pick the first required topic with an empty captured slot AND no prior
    question already covering it. Returns the deterministic question text."""
    asked_topics = set()
    for q in asked_qs:
        topic = _infer_topic_for_question(q)
        if topic:
            asked_topics.add(topic)
    for t in _REQUIRED_TOPICS:
        if (captured or {}).get(t):
            continue
        if t in asked_topics:
            # Already asked but not captured — drill deeper rather than re-ask.
            return _DRILL_DOWN_QUESTIONS.get(t)
        return _FIRST_PASS_QUESTIONS.get(t)
    return None


_FIRST_PASS_QUESTIONS: dict[str, str] = {
    "audience": "Who is this campaign primarily for — describe the traveller in one sentence?",
    "hero_offer": "What's the single most compelling element of the offer or experience?",
    "tone": "What tone should the copy strike — refined, playful, indulgent, urgent, or something else?",
    "must_mention": "Are there non-negotiable USPs or elements that must appear in every concept?",
    "must_avoid": "Anything we must NOT say or imply — claims, themes, wording?",
}

_DRILL_DOWN_QUESTIONS: dict[str, str] = {
    "audience": "Can you sharpen the traveller persona — age band, party composition (solo / couple / family / multi-gen), and what they value most?",
    "hero_offer": "What single experiential moment, if removed, would make this campaign feel hollow?",
    "tone": "Between two ends of luxury — restrained editorial vs warm celebratory — which side should the copy lean?",
    "must_mention": "Beyond the headline offer, which one detail (a ritual, an amenity, a chef, a view) must always surface?",
    "must_avoid": "Any words, claims, or imagery you've seen overused in this category that we should keep out?",
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
    parts.append(f"TURNS SO FAR: {questions_so_far} (soft cap: {_MAX_TURNS})")

    # Explicit "what's already covered" line — most important guard against
    # re-asking the same topic. Derived from captured AND inferred-from-questions
    # so the model can't accidentally re-ask audience just because Gemini
    # itself returned an empty audience field on the prior turn.
    asked_topics = set()
    for t in turns or []:
        topic = _infer_topic_for_question((t.get("q") or "").strip())
        if topic:
            asked_topics.add(topic)
    captured_topics = {k for k, v in (captured or {}).items() if isinstance(v, str) and v.strip()}
    covered = sorted(asked_topics | captured_topics)
    remaining = [t for t in _REQUIRED_TOPICS if t not in covered]
    parts.append(f"TOPICS ALREADY COVERED (do NOT ask about these again): {covered or 'none yet'}")
    parts.append(f"TOPICS STILL OPEN (pick your next nudge from here, or close out): {remaining or 'none — you should be ready'}")
    parts.append(f"CAPTURED SO FAR:\n{json.dumps(captured, indent=2)}")

    if turns:
        parts.append("\nCONVERSATION HISTORY (last message is the user's reply you need to respond to):")
        for i, t in enumerate(turns, 1):
            parts.append(f"YOU said: {t.get('q', '')}")
            parts.append(f"USER said: {t.get('a', '')}")
    else:
        parts.append("\nCONVERSATION HISTORY: (none yet — open the chat with a warm one-liner that picks up on the theme and asks about ONE of the open topics)")

    parts.append(
        "\nReply now. JSON only. Remember: covered topics are off-limits for new questions; "
        "if all five required slots have any non-empty captured value, set ready_for_shortlist=true "
        "and put a one-line closer in next_question (or leave it empty)."
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
    """Deterministic fallback — walk the required topics that haven't been
    captured AND haven't already been asked. Drill deeper if asked-but-empty."""
    asked_qs = [(t.get("q") or "").strip() for t in (turns or [])]
    replacement = _next_unmet_question(captured or {}, asked_qs)
    if replacement:
        return {
            "next_question": replacement,
            "ready_for_shortlist": False,
            "captured": captured,
            "tokens_used": 0,
            "model_used": "fallback",
        }
    # Legacy path (kept for backwards-compat — unreachable now that
    # _next_unmet_question handles every required topic).
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
