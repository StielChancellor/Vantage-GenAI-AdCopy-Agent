"""Shortlist generator for Campaign Ideation (v2.7).

Single Gemini call that — given the critique transcript + scope + retrieved
visual-inspiration captions — produces EXACTLY 10 campaign concepts. Each
concept has a name, tagline, story-line, and prompt-ready visual direction.

Loyalty mode (Club ITC / `is_loyalty=True`) re-anonymizes the visual_direction
text so partner-brand specifics never leak into the output.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("vantage.ideation.shortlist")


_SYSTEM_PROMPT = """You are the creative director of a luxury hospitality group's in-house agency.

GOAL
Produce EXACTLY 10 campaign concepts grounded in the brief and in the visual identity established by the supplied past creative captions. Each concept must be distinct — vary tone, hero subject, narrative angle, and creative device. Do not produce near-duplicates.

REQUIREMENTS PER ITEM
- name             — ≤ 8 words, evocative, ownable (not generic like "Summer Sale").
- tagline          — ≤ 12 words. Sharp. No exclamation marks.
- story_line       — 2–4 sentences telling the campaign narrative.
- visual_direction — 3–6 sentence paragraph that doubles as an image-generation prompt. Reference palette tokens, motifs, logo unit placement, photography style, and mood drawn from the past creative captions provided. Be concrete.
- inspiration_asset_ids — list of 0–3 asset IDs from the supplied references that most informed this concept.

OUTPUT — return ONLY valid JSON in exactly this schema:
{
  "items": [
    {
      "name": "",
      "tagline": "",
      "story_line": "",
      "visual_direction": "",
      "inspiration_asset_ids": []
    }
    // ... 10 items total
  ]
}
"""


async def generate_shortlist(
    theme_text: str,
    date_start: str,
    date_end: str,
    scope_summary: str,
    captured: dict,
    is_loyalty: bool,
    inspiration: dict | None = None,
) -> dict:
    """Run the shortlist call.

    Returns {items: [...], tokens_used, model_used}.
    """
    from backend.app.core.vertex_client import (
        get_generative_model, extract_token_counts,
    )
    from backend.app.services.rag_engine import _anonymize_passage

    inspiration = inspiration or {}
    assets = inspiration.get("assets") or []

    user_prompt = _build_user_prompt(
        theme_text=theme_text,
        date_start=date_start,
        date_end=date_end,
        scope_summary=scope_summary,
        captured=captured or {},
        assets=assets,
        is_loyalty=is_loyalty,
    )

    try:
        model = get_generative_model(system_instruction=_SYSTEM_PROMPT)
        response = model.generate_content(user_prompt)
        raw = getattr(response, "text", "") or ""
        in_tok, out_tok = extract_token_counts(response)
        model_name = getattr(model, "_model_name", "") or "gemini-3.1-pro-preview"
    except Exception as exc:
        logger.warning("shortlist LLM call failed: %s", exc)
        return {"items": _fallback_items(theme_text, captured), "tokens_used": 0, "model_used": "fallback"}

    parsed = _parse_json(raw)
    items_raw = (parsed or {}).get("items") or []

    items: list[dict] = []
    for it in items_raw[:10]:
        item = {
            "name": _clip(it.get("name"), 80),
            "tagline": _clip(it.get("tagline"), 140),
            "story_line": _clip(it.get("story_line"), 800),
            "visual_direction": _clip(it.get("visual_direction"), 1400),
            "inspiration_asset_ids": [str(x) for x in (it.get("inspiration_asset_ids") or [])][:3],
        }
        if is_loyalty:
            # Anonymize visual_direction so partner-brand specifics never bleed through.
            shadow = _anonymize_passage({
                "headline": "",
                "description": item["visual_direction"],
            })
            item["visual_direction"] = (shadow.get("description") or "").strip() or item["visual_direction"]
        items.append(item)

    if len(items) < 10:
        items.extend(_fallback_items(theme_text, captured)[: (10 - len(items))])

    return {
        "items": items,
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
    captured: dict,
    assets: list[dict],
    is_loyalty: bool,
) -> str:
    parts: list[str] = []
    parts.append(f"THEME: {theme_text}")
    if date_start or date_end:
        parts.append(f"DATES: {date_start or '?'} → {date_end or '?'}")
    if scope_summary:
        parts.append(f"SCOPE: {scope_summary}")
    if is_loyalty:
        parts.append("MODE: LOYALTY — do NOT name partner brands or specific properties.")
    parts.append("BRIEF (captured during critique):")
    parts.append(json.dumps(captured, indent=2))

    if assets:
        parts.append("\nPAST CREATIVE REFERENCES (use to derive visual_direction):")
        for a in assets[:8]:
            cap = a.get("caption_json") or {}
            motifs = ", ".join(cap.get("motifs") or []) if isinstance(cap.get("motifs"), list) else ""
            palette = ", ".join(cap.get("palette_tokens") or []) if isinstance(cap.get("palette_tokens"), list) else ""
            parts.append(
                f"- id={a.get('id')} | campaign={a.get('campaign_name', '')} | "
                f"season={cap.get('season_hint', a.get('season', ''))} | "
                f"mood={cap.get('mood', '')} | hero={cap.get('hero_subject', '')} | "
                f"palette=[{palette}] | motifs=[{motifs}] | "
                f"photo={cap.get('photography_style', '')} | "
                f"logo={cap.get('logo_unit_placement', '')} | "
                f"headline=\"{a.get('headline', '')}\""
            )
    else:
        parts.append("\nPAST CREATIVE REFERENCES: (none available — derive visual direction from theme + general luxury-hospitality vocabulary)")

    parts.append(
        "\nProduce exactly 10 distinct concepts. JSON only — no preamble, no markdown."
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
        logger.debug("shortlist JSON parse failed; raw=%s", raw[:300])
    return {}


def _clip(v, n: int) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s[:n]


def _fallback_items(theme_text: str, captured: dict) -> list[dict]:
    """Last-resort filler so the contract (10 items) always holds."""
    base = (theme_text or "Campaign").strip().title()
    tone = (captured or {}).get("tone") or "refined"
    out: list[dict] = []
    for i in range(10):
        out.append({
            "name": f"{base} — Concept {i+1}",
            "tagline": f"A {tone} take on {base.lower()}",
            "story_line": (
                f"A {tone} narrative built around {base.lower()}. "
                "Replace with model-generated content when LLM output is unavailable."
            ),
            "visual_direction": (
                "Warm natural light, restrained palette, generous negative space, "
                "logo unit bottom-left, motifs drawn from local craft. Photography style: "
                "editorial, shallow depth of field, candid moments over staged portraits."
            ),
            "inspiration_asset_ids": [],
        })
    return out
