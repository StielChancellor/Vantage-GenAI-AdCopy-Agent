"""Final-10 exporters for Campaign Ideation (v2.9).

Three formats:
- CSV    — one row per concept; quoted, RFC 4180-style.
- HTML   — single-page printable layout that renders palette swatches as
           coloured boxes and motifs as chips. Designed for Cmd/Ctrl+P → PDF
           so we don't need a server-side PDF dependency.
- JSON   — raw concepts blob, useful for power users / data ops.
"""
from __future__ import annotations

import csv
import html
import io
import json
from datetime import datetime, timezone


_CSV_COLUMNS = [
    "campaign_id", "rank", "name", "justification", "story_line",
    "palette", "motifs", "mood", "photography_style", "logo_placement",
]


def _latest_final_iteration(state: dict) -> dict | None:
    for it in reversed(state.get("iterations") or []):
        if it.get("kind") == "final" and it.get("final"):
            return it
    return None


def to_json(state: dict) -> dict:
    """Raw concepts blob — includes campaign_id, offer name, all final concepts."""
    inputs = state.get("inputs") or {}
    final = _latest_final_iteration(state) or {}
    return {
        "campaign_id": state.get("campaign_id"),
        "ideation_id": state.get("id"),
        "offer_name": inputs.get("offer_name"),
        "discount": inputs.get("discount"),
        "audience_axis": inputs.get("audience_axis"),
        "tone_axis": inputs.get("tone_axis"),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "concepts": final.get("final") or [],
    }


def to_csv(state: dict) -> str:
    """One row per concept. Columns: campaign_id, rank, name, justification,
    story_line, palette, motifs, mood, photography_style, logo_placement."""
    final = _latest_final_iteration(state) or {}
    concepts = final.get("final") or []
    cid = state.get("campaign_id") or ""

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for i, c in enumerate(concepts, 1):
        vc = c.get("visual_cue") or {}
        writer.writerow({
            "campaign_id": cid,
            "rank": i,
            "name": c.get("name", ""),
            "justification": c.get("justification", ""),
            "story_line": c.get("story_line", ""),
            "palette": ", ".join(vc.get("palette") or []),
            "motifs": ", ".join(vc.get("motifs") or []),
            "mood": vc.get("mood", ""),
            "photography_style": vc.get("photography_style", ""),
            "logo_placement": vc.get("logo_placement", ""),
        })
    return buf.getvalue()


# Common palette-token to hex map; matches the frontend's `inferSwatch`.
_SWATCH_HEX: dict[str, str] = {
    "mist": "#D8E2DC", "slate": "#3F4C4F", "moss": "#5C6B5A", "ivory": "#F5EFE6",
    "ochre": "#C99B57", "sand": "#D9B382", "linen": "#E8E0D3", "amber": "#C28A3F",
    "teal": "#356A77", "cobalt": "#1F3B6E", "rose": "#C99097", "plum": "#5A3050",
    "saffron": "#E2A937", "emerald": "#2C715A", "stone": "#88827A", "pine": "#33502E",
    "sage": "#9CAB8A", "cream": "#F0E9DD", "clay": "#B07A5A", "smoke": "#7F8A8C",
    "midnight": "#101428", "sunset": "#C6604D", "salt": "#EDEDEB", "shore": "#A8B8B0",
    "fog": "#C8CFD4", "bronze": "#A06F3A", "ruby": "#73223A", "jade": "#3D8B71",
}


def _swatch(tok: str) -> str:
    s = (tok or "").strip().lower()
    # Hex passthrough.
    for piece in s.split():
        if piece.startswith("#") and len(piece) in (4, 7):
            return piece
    for k, hexv in _SWATCH_HEX.items():
        if k in s:
            return hexv
    return "#D4CFC2"


def to_html(state: dict) -> str:
    """Single-page printable HTML deck. Cmd/Ctrl+P in browser → PDF.
    Embedded styles only; no external assets so the page works offline."""
    inputs = state.get("inputs") or {}
    final = _latest_final_iteration(state) or {}
    concepts = final.get("final") or []
    cid = state.get("campaign_id") or ""

    offer = html.escape(inputs.get("offer_name") or "Untitled campaign")
    discount_notes = html.escape((inputs.get("discount") or {}).get("notes") or "")
    audience = html.escape((inputs.get("audience_axis") or "").replace("_", " "))
    tone = html.escape(inputs.get("tone_axis") or "")
    exported_at = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    concept_cards = []
    for i, c in enumerate(concepts, 1):
        vc = c.get("visual_cue") or {}
        palette = vc.get("palette") or []
        motifs = vc.get("motifs") or []
        swatch_html = "".join(
            f'<span class="swatch" title="{html.escape(str(p))}">'
            f'<span class="dot" style="background:{_swatch(p)}"></span>{html.escape(str(p))}</span>'
            for p in palette
        )
        motif_chips = "".join(f'<span class="chip">{html.escape(str(m))}</span>' for m in motifs)
        concept_cards.append(f"""
        <article class="concept">
          <header>
            <span class="rank">#{i}</span>
            <h2>{html.escape(c.get("name", ""))}</h2>
          </header>
          <p class="just">{html.escape(c.get("justification", ""))}</p>
          {f'<p class="story">{html.escape(c.get("story_line", ""))}</p>' if c.get("story_line") else ''}
          <section class="cue">
            <div class="cue-label">Palette</div><div class="cue-val swatches">{swatch_html or "&mdash;"}</div>
            <div class="cue-label">Motifs</div><div class="cue-val">{motif_chips or "&mdash;"}</div>
            <div class="cue-label">Mood</div><div class="cue-val">{html.escape(vc.get("mood", "") or "—")}</div>
            <div class="cue-label">Photography</div><div class="cue-val">{html.escape(vc.get("photography_style", "") or "—")}</div>
            <div class="cue-label">Logo placement</div><div class="cue-val">{html.escape(vc.get("logo_placement", "") or "—")}</div>
          </section>
        </article>
        """)

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Campaign Ideation #{html.escape(cid)} — {offer}</title>
<style>
  :root {{
    --ink: #1f1d1a; --ink-soft: #6e6a62; --ink-faint: #d8d2c8;
    --bg: #ffffff; --bg-soft: #faf7f2; --accent: #a93226;
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: ui-sans-serif, system-ui, "Segoe UI", sans-serif; color: var(--ink); background: var(--bg);
    margin: 0; padding: 32px 48px; line-height: 1.45; }}
  header.cover {{ border-bottom: 1px solid var(--ink-faint); padding-bottom: 16px; margin-bottom: 28px; }}
  .id-chip {{ font-family: ui-monospace, "JetBrains Mono", monospace; font-size: 12px;
    letter-spacing: 0.06em; color: var(--accent); background: rgba(169,50,38,0.08);
    padding: 4px 9px; border-radius: 10px; display: inline-block; }}
  h1 {{ font-size: 28px; margin: 8px 0 6px; font-weight: 600; }}
  .meta {{ color: var(--ink-soft); font-size: 13px; }}
  .meta span + span {{ margin-left: 18px; }}
  .grid {{ display: grid; grid-template-columns: 1fr; gap: 24px; }}
  .concept {{ border: 1px solid var(--ink-faint); border-radius: 8px;
    padding: 20px 22px; page-break-inside: avoid; background: var(--bg-soft); }}
  .concept header {{ display: flex; align-items: baseline; gap: 10px; margin-bottom: 6px; }}
  .rank {{ font-family: ui-monospace, monospace; font-size: 11px; color: var(--ink-soft); }}
  .concept h2 {{ font-size: 18px; margin: 0; font-weight: 600; }}
  .just {{ font-style: italic; color: var(--ink); margin: 4px 0 8px; }}
  .story {{ color: var(--ink-soft); margin: 0 0 10px; }}
  .cue {{ display: grid; grid-template-columns: 130px 1fr; gap: 6px 16px; font-size: 13px;
    border-top: 1px dashed var(--ink-faint); padding-top: 10px; }}
  .cue-label {{ font-family: ui-monospace, monospace; font-size: 10px;
    text-transform: uppercase; color: var(--ink-soft); letter-spacing: 0.06em; padding-top: 3px; }}
  .cue-val {{ color: var(--ink); }}
  .chip {{ display: inline-block; padding: 2px 8px; margin: 2px 4px 2px 0;
    background: rgba(0,0,0,0.04); border-radius: 10px; font-size: 12px; }}
  .swatch {{ display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px 2px 6px;
    margin: 2px 4px 2px 0; background: rgba(0,0,0,0.04); border-radius: 10px; font-size: 12px; }}
  .swatch .dot {{ width: 12px; height: 12px; border-radius: 50%;
    border: 1px solid rgba(0,0,0,0.1); }}
  footer {{ margin-top: 40px; padding-top: 18px; border-top: 1px solid var(--ink-faint);
    font-size: 11px; color: var(--ink-soft); }}
  @media print {{
    body {{ padding: 0; }}
    .concept {{ break-inside: avoid; }}
  }}
</style>
</head><body>
  <header class="cover">
    <span class="id-chip">#{html.escape(cid) or "DRAFT"}</span>
    <h1>{offer}</h1>
    <p class="meta">
      <span><strong>Audience</strong> · {audience or "—"}</span>
      <span><strong>Tone</strong> · {tone or "—"}</span>
      <span><strong>Discount</strong> · {discount_notes or "—"}</span>
    </p>
  </header>
  <section class="grid">
    {''.join(concept_cards) or '<p>No concepts yet.</p>'}
  </section>
  <footer>Exported {exported_at} · Vantage GenAI</footer>
</body></html>
"""
