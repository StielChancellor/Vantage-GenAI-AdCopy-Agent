"""Direction generator for Campaign Ideation v2.8.

Given the structured Step-1 inputs (and optional prior-iteration seed),
returns 3–5 distinct creative directions. Each direction has a title,
rationale, a visual cue, and 5 named concepts with one-line justifications.

Loyalty mode (Club ITC) calls `rag_engine.retrieve_visual_inspiration`
to ground visual cues in cross-brand-anonymised past creative.
"""
from __future__ import annotations

import json
import logging
import uuid

logger = logging.getLogger("vantage.ideation.directions")


_SYSTEM_PROMPT = """You are the creative director of a luxury hospitality group's in-house agency, briefing your team. The marketer has given you a concrete brief. Produce 3–5 distinct CREATIVE DIRECTIONS — not 10 names. Each direction is a sharp angle a small team could spend a week building out.

RULES
1. Pick 3 to 5 directions (model's choice — base it on how rich the brief is). Five maximum.
2. Each direction must be genuinely distinct in angle, tone, or visual approach. No near-duplicates.
3. Honor the marketer's chosen axes:
   - audience_axis ∈ business / in_between / leisure — directions should map across or pick a stance.
   - tone_axis ∈ tactical / hybrid / aspirational — tactical = price/inclusion-led, easy-to-relate names; aspirational = thought-provoking, sensorial, emotion-evoking; hybrid = lyrical but anchored to the offer.
4. For a HILL hotel offer, an aspirational name should evoke mountains — synonyms, weather, light, stillness, breath, ridge, altitude. For a COAST property, lean salt, swell, horizon. For a CITY property, lean texture, threshold, rhythm. Use the participating hotels' cities/brand to ground the imagery.
5. Each direction has EXACTLY 5 concepts. A concept = {name (≤ 8 words), justification (one line, ≤ 20 words)}.
6. Each direction has a visual_cue object describing the look-and-feel team should chase: palette tokens (3–5 short tokens), motifs (3–5 short phrases), photography_style (≤ 80 chars), mood (≤ 60 chars), logo_placement (one phrase).
7. Tactical-leaning directions get concept names that are easy-to-relate ("Mountain Escape — 25% Off" style); aspirational ones get names that feel like book titles or essay titles.
8. NEVER repeat a direction title, rationale or concept across iterations — if prior-iteration concepts are listed, treat them as anti-examples to avoid.

OUTPUT — return ONLY valid JSON in exactly this schema:
{
  "directions": [
    {
      "id": "dir_slug_lowercase",
      "title": "Tone — Theme",
      "rationale": "One sentence explaining why this angle fits this brief.",
      "visual_cue": {
        "palette": ["token1", "token2", "..."],
        "motifs": ["motif1", "motif2", "..."],
        "photography_style": "...",
        "mood": "...",
        "logo_placement": "..."
      },
      "concepts": [
        { "id": "c_slug", "name": "...", "justification": "..." }
        // exactly 5
      ]
    }
    // 3 to 5 directions total
  ]
}
"""


async def generate_directions(
    inputs: dict,
    iteration_seed: dict | None = None,
    iteration_number: int = 1,
    hotel_context: list[dict] | None = None,
) -> dict:
    """Run a single Gemini call. Returns {directions, tokens_used, model_used}.

    `inputs` is the IdeationInputs payload as a dict.
    `iteration_seed` (optional) carries refinement signals from prior iteration:
        { selected_direction_id?, selected_concept_ids[], freetext_steer, prior_concept_names[], prior_direction_titles[] }
    `hotel_context` is a short list of {name, brand, city} dicts for naming inspiration.
    """
    from backend.app.core.vertex_client import (
        get_generative_model, extract_token_counts,
    )
    from backend.app.services.rag_engine import retrieve_visual_inspiration

    iteration_seed = iteration_seed or {}
    hotel_context = hotel_context or []

    is_loyalty = bool((inputs.get("hotels_resolution") or {}).get("is_loyalty"))

    # Loyalty grounding — pull past creative as anonymised inspiration.
    inspiration: dict = {}
    if is_loyalty:
        try:
            inspiration = await retrieve_visual_inspiration(
                theme_text=inputs.get("offer_name") or "",
                selection={
                    "scope": "loyalty",
                    "is_loyalty": True,
                    "brand_ids": (inputs.get("hotels_resolution") or {}).get("resolved_brand_ids") or [],
                },
                top_k=6,
            )
        except Exception as exc:
            logger.debug("retrieve_visual_inspiration (loyalty) failed: %s", exc)

    user_prompt = _build_user_prompt(inputs, iteration_seed, iteration_number, hotel_context, inspiration)

    try:
        model = get_generative_model(system_instruction=_SYSTEM_PROMPT)
        response = model.generate_content(user_prompt)
        raw = getattr(response, "text", "") or ""
        in_tok, out_tok = extract_token_counts(response)
        model_name = getattr(model, "_model_name", "") or "gemini-3.1-pro-preview"
    except Exception as exc:
        logger.warning("directions LLM call failed: %s", exc)
        return {"directions": [], "tokens_used": 0, "model_used": "error"}

    parsed = _parse_json(raw)
    raw_dirs = (parsed or {}).get("directions") or []

    cleaned: list[dict] = []
    seen_titles: set = set()
    for d in raw_dirs:
        if not isinstance(d, dict):
            continue
        title = (d.get("title") or "").strip()
        if not title or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        concepts = []
        for c in (d.get("concepts") or [])[:5]:
            if not isinstance(c, dict):
                continue
            name = (c.get("name") or "").strip()
            just = (c.get("justification") or "").strip()
            if not name:
                continue
            concepts.append({
                "id": _clean_id(c.get("id"), prefix=f"c{len(cleaned)+1}"),
                "name": name[:80],
                "justification": just[:200],
            })

        # Pad to 5 if model under-delivered.
        while len(concepts) < 5:
            concepts.append({
                "id": _clean_id(None, prefix=f"pad_{len(concepts)+1}"),
                "name": f"Concept {len(concepts)+1}",
                "justification": "Filler — model returned fewer than 5 names; replace by regenerating.",
            })

        vc = d.get("visual_cue") or {}
        cleaned.append({
            "id": _clean_id(d.get("id"), prefix=f"dir{len(cleaned)+1}"),
            "title": title[:120],
            "rationale": (d.get("rationale") or "").strip()[:300],
            "visual_cue": {
                "palette": _to_str_list(vc.get("palette"), 6),
                "motifs": _to_str_list(vc.get("motifs"), 8),
                "photography_style": _clip(vc.get("photography_style"), 200),
                "mood": _clip(vc.get("mood"), 120),
                "logo_placement": _clip(vc.get("logo_placement"), 120),
            },
            "concepts": concepts,
        })

        if len(cleaned) >= 5:
            break

    # Enforce min 3 — if model gave fewer, append filler so the contract holds.
    while len(cleaned) < 3:
        cleaned.append(_filler_direction(len(cleaned) + 1))

    return {
        "directions": cleaned,
        "tokens_used": in_tok + out_tok,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "model_used": model_name,
    }


def _build_user_prompt(
    inputs: dict,
    seed: dict,
    iter_n: int,
    hotel_context: list[dict],
    inspiration: dict,
) -> str:
    parts: list[str] = []
    parts.append(f"ITERATION: {iter_n}")
    parts.append("BRIEF:")
    parts.append(json.dumps({
        "offer_name": inputs.get("offer_name"),
        "inclusions": inputs.get("inclusions"),
        "discount": inputs.get("discount"),
        "audience_axis": inputs.get("audience_axis"),
        "tone_axis": inputs.get("tone_axis"),
    }, indent=2))

    if hotel_context:
        parts.append("PARTICIPATING HOTELS (use for naming inspiration — place, brand, character):")
        parts.append(json.dumps(hotel_context[:30], indent=2))

    hr = inputs.get("hotels_resolution") or {}
    if hr.get("is_loyalty"):
        parts.append("MODE: LOYALTY — anonymise visual cues across partner brands. Do NOT name a specific property.")
    if hr.get("phrase"):
        parts.append(f"HOTEL DESCRIPTION FROM USER: \"{hr['phrase']}\"")

    if inspiration and inspiration.get("assets"):
        parts.append("PAST CREATIVE GROUNDING (anonymised — use for palette / motif inspiration only):")
        for a in inspiration["assets"][:5]:
            cap = a.get("caption_json") or {}
            parts.append(
                f"- mood={cap.get('mood','?')} | palette={cap.get('palette_tokens','?')} | "
                f"motifs={cap.get('motifs','?')} | photo={cap.get('photography_style','?')}"
            )

    if seed.get("freetext_steer"):
        parts.append(f"USER STEER: \"{seed['freetext_steer']}\"")
    if seed.get("selected_direction_id"):
        parts.append(f"USER PICKED PRIOR DIRECTION: {seed['selected_direction_id']} — lean into this angle, push further.")
    if seed.get("selected_concept_ids"):
        parts.append(f"USER LIKED THESE CONCEPTS (use as seed, push variation): {seed['selected_concept_ids']}")
    if seed.get("prior_direction_titles"):
        parts.append(
            f"ANTI-EXAMPLES (do NOT propose the same titles again — produce new angles): "
            f"{seed['prior_direction_titles']}"
        )
    if seed.get("prior_concept_names"):
        parts.append(
            f"ANTI-EXAMPLES (do NOT propose the same concept names): "
            f"{seed['prior_concept_names'][:30]}"
        )

    parts.append("\nProduce 3 to 5 distinct directions. JSON only — no preamble, no markdown.")
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
        logger.debug("directions JSON parse failed; raw=%s", raw[:300])
    return {}


def _clean_id(v, prefix: str = "id") -> str:
    s = (v or "").strip().lower()
    s = "".join(ch for ch in s if ch.isalnum() or ch == "_") if s else ""
    if not s:
        s = f"{prefix}_{uuid.uuid4().hex[:6]}"
    return s[:48]


def _to_str_list(v, cap: int) -> list[str]:
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for x in v:
        s = str(x).strip()
        if s:
            out.append(s[:60])
        if len(out) >= cap:
            break
    return out


def _clip(v, n: int) -> str:
    if v is None:
        return ""
    return str(v).strip()[:n]


def _filler_direction(idx: int) -> dict:
    return {
        "id": f"dir_filler_{idx}",
        "title": f"Direction {idx} (filler)",
        "rationale": "Filler entry — regenerate to replace.",
        "visual_cue": {
            "palette": ["warm", "linen", "ivory"],
            "motifs": ["clean lines", "candid moment", "negative space"],
            "photography_style": "editorial, natural light",
            "mood": "considered",
            "logo_placement": "bottom-left hairline",
        },
        "concepts": [
            {"id": f"f_{idx}_{i}", "name": f"Filler concept {i+1}",
             "justification": "Filler — regenerate."}
            for i in range(5)
        ],
    }
