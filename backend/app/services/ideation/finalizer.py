"""Final-10 generator for Campaign Ideation v2.8.

Takes the persisted inputs + iteration history + (optionally) the user's
seed selections and free-text steer, and produces EXACTLY 10 polished
named concepts with detailed visual cues.

Loyalty mode runs `_anonymize_passage` over every visual_cue motif/mood
string so partner-brand specifics never leak.
"""
from __future__ import annotations

import json
import logging
import uuid

logger = logging.getLogger("vantage.ideation.finalizer")


_SYSTEM_PROMPT = """You are the creative director compressing a week of divergent thinking into a finalist set. Produce EXACTLY 10 polished named concepts, distilled from the brief + the directions explored + the user's seed selections.

REQUIREMENTS PER CONCEPT
- name             — ≤ 8 words, ownable, evocative. Not generic ("Summer Sale", "Festive Offer" are banned).
- justification    — ONE crisp line (≤ 18 words) explaining why the name works for this brief.
- visual_cue       — concrete, prompt-ready:
    - palette: 3–5 tokens. Use evocative names AND hex codes when you can ("#D8E2DC mist").
    - motifs: 3–5 short phrases.
    - photography_style: one phrase, ≤ 100 chars.
    - mood: one phrase, ≤ 60 chars.
    - logo_placement: one phrase.

ABSOLUTE RULES
1. Vary tone, hero subject, narrative angle, and creative device. No near-duplicates.
2. If seed_concept_ids were provided, treat them as inspiration to remix — produce variations that blend their best elements with new ideas. Don't just rename the seeds.
3. If a freetext_steer is present, every concept should respect it.
4. LOYALTY mode (when stated below): never name a specific property or city. Use generic categories ("the property", "a mountain retreat").
5. If past creative captions are listed, draw palette/motif inspiration from them but do not copy them wholesale.

OUTPUT — return ONLY valid JSON in exactly this schema:
{
  "concepts": [
    {
      "id": "c_slug",
      "name": "...",
      "justification": "...",
      "visual_cue": {
        "palette": ["..."],
        "motifs": ["..."],
        "photography_style": "...",
        "mood": "...",
        "logo_placement": "..."
      },
      "inspiration_asset_ids": ["..."]
    }
    // exactly 10
  ]
}
"""


async def generate_final_concepts(
    inputs: dict,
    iterations: list[dict] | None = None,
    seed_concept_ids: list[str] | None = None,
    freetext_steer: str = "",
    hotel_context: list[dict] | None = None,
) -> dict:
    from backend.app.core.vertex_client import (
        get_generative_model, extract_token_counts,
    )
    from backend.app.services.rag_engine import retrieve_visual_inspiration, _anonymize_passage

    iterations = iterations or []
    seed_concept_ids = seed_concept_ids or []
    hotel_context = hotel_context or []
    is_loyalty = bool((inputs.get("hotels_resolution") or {}).get("is_loyalty"))

    # Pull RAG inspiration (always, not just loyalty — past creative
    # captions sharpen visual cue text whether anonymised or not).
    inspiration: dict = {}
    try:
        inspiration = await retrieve_visual_inspiration(
            theme_text=inputs.get("offer_name") or "",
            selection={
                "scope": "loyalty" if is_loyalty else "brand",
                "is_loyalty": is_loyalty,
                "brand_ids": (inputs.get("hotels_resolution") or {}).get("resolved_brand_ids") or [],
                "hotel_ids": (inputs.get("hotels_resolution") or {}).get("resolved_hotel_ids") or [],
            },
            top_k=8,
        )
    except Exception as exc:
        logger.debug("retrieve_visual_inspiration (final) failed: %s", exc)

    seeds: list[dict] = _gather_seeds(iterations, seed_concept_ids)

    user_prompt = _build_user_prompt(
        inputs=inputs,
        iterations=iterations,
        seeds=seeds,
        freetext_steer=freetext_steer,
        hotel_context=hotel_context,
        is_loyalty=is_loyalty,
        inspiration=inspiration,
    )

    try:
        model = get_generative_model(system_instruction=_SYSTEM_PROMPT)
        response = model.generate_content(user_prompt)
        raw = getattr(response, "text", "") or ""
        in_tok, out_tok = extract_token_counts(response)
        model_name = getattr(model, "_model_name", "") or "gemini-3.1-pro-preview"
    except Exception as exc:
        logger.warning("finalize LLM call failed: %s", exc)
        return {"concepts": _filler_concepts(inputs.get("offer_name") or ""), "tokens_used": 0, "model_used": "error"}

    parsed = _parse_json(raw)
    raw_concepts = (parsed or {}).get("concepts") or []

    cleaned: list[dict] = []
    for c in raw_concepts[:10]:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip()
        if not name:
            continue
        vc = c.get("visual_cue") or {}
        cleaned_vc = {
            "palette": _to_str_list(vc.get("palette"), 6),
            "motifs": _to_str_list(vc.get("motifs"), 6),
            "photography_style": _clip(vc.get("photography_style"), 200),
            "mood": _clip(vc.get("mood"), 120),
            "logo_placement": _clip(vc.get("logo_placement"), 120),
        }
        if is_loyalty:
            cleaned_vc = _anonymize_visual_cue(cleaned_vc, _anonymize_passage)
        cleaned.append({
            "id": _clean_id(c.get("id"), prefix=f"f{len(cleaned)+1}"),
            "name": name[:80],
            "justification": _clip(c.get("justification"), 220),
            "visual_cue": cleaned_vc,
            "inspiration_asset_ids": [str(x)[:64] for x in (c.get("inspiration_asset_ids") or [])][:5],
        })

    while len(cleaned) < 10:
        cleaned.append(_filler_concept(len(cleaned) + 1))

    return {
        "concepts": cleaned[:10],
        "tokens_used": in_tok + out_tok,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "model_used": model_name,
    }


def _gather_seeds(iterations: list[dict], seed_ids: list[str]) -> list[dict]:
    """Find the concept dicts whose ids match seed_ids across all prior iterations."""
    if not seed_ids:
        return []
    wanted = set(seed_ids)
    out: list[dict] = []
    for it in iterations:
        for c in (it.get("directions") or []):
            for cc in (c.get("concepts") or []):
                if cc.get("id") in wanted:
                    out.append({
                        "id": cc.get("id"),
                        "name": cc.get("name"),
                        "justification": cc.get("justification"),
                        "direction_title": c.get("title"),
                        "visual_cue": c.get("visual_cue"),
                    })
        for f in (it.get("final") or []):
            if f.get("id") in wanted:
                out.append({
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "justification": f.get("justification"),
                    "visual_cue": f.get("visual_cue"),
                })
    return out[:10]


def _build_user_prompt(
    inputs: dict,
    iterations: list[dict],
    seeds: list[dict],
    freetext_steer: str,
    hotel_context: list[dict],
    is_loyalty: bool,
    inspiration: dict,
) -> str:
    parts: list[str] = []
    parts.append("BRIEF:")
    parts.append(json.dumps({
        "offer_name": inputs.get("offer_name"),
        "inclusions": inputs.get("inclusions"),
        "discount": inputs.get("discount"),
        "audience_axis": inputs.get("audience_axis"),
        "tone_axis": inputs.get("tone_axis"),
    }, indent=2))

    if hotel_context:
        parts.append("PARTICIPATING HOTELS (use for naming inspiration):")
        parts.append(json.dumps(hotel_context[:30], indent=2))

    if is_loyalty:
        parts.append("MODE: LOYALTY — generic / categorical references only. No property names.")

    if seeds:
        parts.append("USER-SELECTED SEEDS (remix, don't copy):")
        parts.append(json.dumps(seeds, indent=2))

    if freetext_steer:
        parts.append(f"USER STEER: \"{freetext_steer}\"")

    if iterations:
        # Pass titles + names from prior iterations as anti-examples (avoid duplicates).
        prior_titles: list[str] = []
        prior_names: list[str] = []
        for it in iterations:
            for d in (it.get("directions") or []):
                prior_titles.append(d.get("title", ""))
                for cc in (d.get("concepts") or []):
                    prior_names.append(cc.get("name", ""))
            for f in (it.get("final") or []):
                prior_names.append(f.get("name", ""))
        if prior_titles:
            parts.append(f"PRIOR DIRECTION TITLES (do not reuse): {prior_titles[:20]}")
        if prior_names:
            parts.append(f"PRIOR CONCEPT NAMES (do not reuse verbatim): {prior_names[:30]}")

    if inspiration and inspiration.get("assets"):
        parts.append("PAST CREATIVE CAPTIONS (anonymised; for palette / motif inspiration):")
        for a in inspiration["assets"][:6]:
            cap = a.get("caption_json") or {}
            parts.append(
                f"- mood={cap.get('mood','?')} | palette={cap.get('palette_tokens','?')} | "
                f"motifs={cap.get('motifs','?')} | photo={cap.get('photography_style','?')}"
            )

    parts.append("\nProduce EXACTLY 10 polished concepts. JSON only.")
    return "\n".join(parts)


def _anonymize_visual_cue(vc: dict, anonymise_fn) -> dict:
    """Run anonymisation over the strings in a visual_cue object."""
    out = dict(vc)
    def _clean_text(s: str) -> str:
        if not s:
            return s
        shadow = anonymise_fn({"headline": "", "description": s})
        return (shadow.get("description") or "").strip() or s
    for key in ("photography_style", "mood", "logo_placement"):
        out[key] = _clean_text(out.get(key, ""))
    out["motifs"] = [_clean_text(m) for m in out.get("motifs", [])]
    return out


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
        logger.debug("finalizer JSON parse failed; raw=%s", raw[:300])
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


def _filler_concepts(seed: str) -> list[dict]:
    return [_filler_concept(i + 1) for i in range(10)]


def _filler_concept(i: int) -> dict:
    return {
        "id": f"f_filler_{i}",
        "name": f"Concept {i} (filler)",
        "justification": "Filler — model returned fewer than 10 concepts. Regenerate to replace.",
        "visual_cue": {
            "palette": ["ivory", "linen", "ochre"],
            "motifs": ["candid moment", "negative space", "natural light"],
            "photography_style": "editorial, warm-balanced",
            "mood": "considered",
            "logo_placement": "bottom-left hairline",
        },
        "inspiration_asset_ids": [],
    }
