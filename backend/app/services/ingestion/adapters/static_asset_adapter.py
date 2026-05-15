"""Static-asset ingestion adapter (v2.7) — Campaign Ideation training corpus.

A 'campaign pack' is a zip whose root (or single top-level folder) contains:
  img_01.jpg, img_02.jpg, ...
  ad_copies.xlsx        # rows mapped to images via `image_filename`
  pack.yaml             # optional metadata defaults

Pipeline:
  1. Unpack zip in-memory, locate images + manifest.
  2. For each manifest row → upload image to GCS, run Gemini Vision caption pass,
     embed (caption + headline + body), and write a `creative_assets/{id}` doc.
  3. Progress is reported via `ingestion_progress/{run_id}` so the existing
     training UI polls it transparently.

All Gemini and embedding calls are async — must be awaited.
"""
from __future__ import annotations

import io
import json
import logging
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger("vantage.ingestion.static_asset")


_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
_MANIFEST_NAMES = ("ad_copies.xlsx", "ad-copies.xlsx", "manifest.xlsx")
_OPTIONAL_YAML = ("pack.yaml", "pack.yml")

_REQUIRED_MANIFEST_COLS = {"image_filename", "headline", "body"}
_OPTIONAL_MANIFEST_COLS = {
    "cta", "platform", "persona", "hero_offer",
    "campaign_name", "season", "theme", "date_start", "date_end",
}


# ─────────────────────────────────────────────────────────────────────────
# Zip parsing
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class PackContents:
    images: dict[str, bytes]            # {basename: bytes}
    manifest_rows: list[dict]
    defaults: dict                       # parsed from pack.yaml (best-effort)
    errors: list[str]


def parse_pack_zip(zip_bytes: bytes) -> PackContents:
    """Unpack a campaign pack zip in-memory. Tolerant of:
      - a single top-level folder wrapper (common in mac/windows zips)
      - case-mismatched filenames between manifest and images
      - missing pack.yaml (treated as no defaults)
    """
    errors: list[str] = []
    images: dict[str, bytes] = {}
    manifest_bytes: bytes | None = None
    yaml_bytes: bytes | None = None

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        return PackContents({}, [], {}, [f"Not a valid zip: {exc}"])

    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename
        base = name.rsplit("/", 1)[-1]
        lower = base.lower()
        if not base or base.startswith("."):
            continue
        if lower in _MANIFEST_NAMES:
            manifest_bytes = zf.read(info)
            continue
        if lower in _OPTIONAL_YAML:
            yaml_bytes = zf.read(info)
            continue
        if lower.endswith(_IMAGE_EXTS):
            images[base] = zf.read(info)

    if manifest_bytes is None:
        errors.append("ad_copies.xlsx not found in zip root.")
        return PackContents(images, [], {}, errors)

    try:
        rows = _read_manifest_xlsx(manifest_bytes)
    except Exception as exc:
        errors.append(f"Manifest parse failed: {exc}")
        return PackContents(images, [], {}, errors)

    if not rows:
        errors.append("Manifest is empty.")
        return PackContents(images, [], {}, errors)

    missing_cols = _REQUIRED_MANIFEST_COLS - set(rows[0].keys())
    if missing_cols:
        errors.append(f"Manifest missing required columns: {sorted(missing_cols)}")
        return PackContents(images, [], {}, errors)

    defaults: dict = {}
    if yaml_bytes is not None:
        defaults = _parse_yaml_defaults(yaml_bytes)

    return PackContents(images, rows, defaults, errors)


def _read_manifest_xlsx(content: bytes) -> list[dict]:
    """Read xlsx into normalized dicts. Lower-cases header names, strips spaces."""
    import pandas as pd

    df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    rows: list[dict] = []
    for _, row in df.iterrows():
        d = {}
        for k, v in row.items():
            if v is None:
                d[k] = ""
                continue
            # pandas NaN guard without importing math
            try:
                if v != v:  # NaN
                    d[k] = ""
                    continue
            except Exception:
                pass
            d[k] = str(v).strip() if not isinstance(v, (int, float)) else v
        if not any(str(v).strip() for v in d.values() if v != ""):
            continue
        rows.append(d)
    return rows


def _parse_yaml_defaults(content: bytes) -> dict:
    """Best-effort YAML parse — pyyaml is not a hard dep so fall back to
    a tiny `key: value` line parser."""
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(content.decode("utf-8", errors="ignore")) or {}
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items()}
    except Exception:
        pass
    out: dict = {}
    try:
        text = content.decode("utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, _, v = line.partition(":")
            out[k.strip().lower()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


# ─────────────────────────────────────────────────────────────────────────
# Vision captioning
# ─────────────────────────────────────────────────────────────────────────

_CAPTION_SYSTEM = (
    "You are a senior creative director auditing a hospitality advertising image. "
    "Describe ONLY what the image visually contains — palette, motifs, logo unit "
    "placement, typography style, photography style, mood, hero subject. Do NOT "
    "invent facts about the property. Return ONLY valid JSON matching the schema."
)

_CAPTION_SCHEMA_HINT = {
    "logo_unit_placement": "top-left | top-right | top-center | bottom-left | bottom-right | bottom-center | center | none",
    "palette_tokens": ["short", "human", "tokens"],
    "dominant_colors_hex": ["#RRGGBB", "..."],
    "typography_style": "free text (≤ 80 chars)",
    "photography_style": "free text (≤ 80 chars)",
    "motifs": ["arches", "linen", "..."],
    "mood": "free text (≤ 60 chars)",
    "season_hint": "summer | monsoon | autumn | winter | spring | unspecified",
    "theme_hint": "free text (≤ 40 chars)",
    "hero_subject": "free text (≤ 80 chars)",
    "copy_overlay_density": "low | medium | high",
}


_CAPTION_MODEL = "gemini-2.5-flash"


async def caption_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> tuple[dict, int, int]:
    """Single Gemini Vision call returning (caption_json, input_tokens, output_tokens).

    Robust to malformed output — falls back to ({}, 0, 0) on any error so the
    pipeline keeps moving even when one image trips the model.
    """
    try:
        from vertexai.generative_models import Part
        from backend.app.core.vertex_client import (
            get_generative_model, extract_token_counts,
        )

        # Captioning is multimodal — pin to a Gemini vision model regardless of
        # the admin-selected default (Claude adapter is text-only on this path).
        # Captioning is multimodal — pin to a Gemini vision model. _CAPTION_MODEL
        # is a real Vertex publisher id (2.5-flash supports vision).
        model = get_generative_model(
            model_name=_CAPTION_MODEL,
            system_instruction=_CAPTION_SYSTEM,
        )
        prompt = (
            "Caption this image as JSON exactly matching the schema below. "
            "Use null only when the field truly is not present. Output ONLY JSON.\n\n"
            f"Schema:\n{json.dumps(_CAPTION_SCHEMA_HINT)}\n"
        )
        image_part = Part.from_data(data=image_bytes, mime_type=mime_type)
        response = model.generate_content([image_part, prompt])
        text = getattr(response, "text", "") or ""
        in_tok, out_tok = extract_token_counts(response)
    except Exception as exc:
        logger.warning("caption_image vision call failed: %s", exc)
        return {}, 0, 0

    return _parse_caption_json(text), int(in_tok), int(out_tok)


def _parse_caption_json(text: str) -> dict:
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
        logger.debug("caption JSON parse failed; raw=%s", raw[:300])
    return {}


# ─────────────────────────────────────────────────────────────────────────
# Top-level pipeline
# ─────────────────────────────────────────────────────────────────────────

async def ingest_creative_pack(
    zip_bytes: bytes,
    brand_id: str,
    user_id: str,
    user_email: str,
    run_id: str,
    pack_id: str | None = None,
    progress_cb=None,
) -> dict:
    """Run the full pack-ingestion pipeline and return a summary dict.

    Writes one `creative_assets/{auto}` doc per matched image. Designed to be
    called from `routers.training` after auth gating.
    """
    from backend.app.core.database import get_firestore
    from backend.app.services.storage.gcs_client import (
        upload_bytes, guess_content_type,
    )
    from backend.app.services.embedding.vertex_embedder import embed_texts

    def _emit(phase: str, percent: int, message: str, processed: int = 0, total: int = 0, status: str = "running"):
        if progress_cb:
            try:
                progress_cb(phase, percent, message, processed=processed, total=total, status=status)
            except Exception:
                pass

    pack_id = pack_id or uuid.uuid4().hex[:12]
    _emit("parsing", 5, "Unpacking zip...")
    contents = parse_pack_zip(zip_bytes)
    if contents.errors and not contents.manifest_rows:
        _emit("failed", 0, "; ".join(contents.errors), status="failed")
        return {
            "pack_id": pack_id, "brand_id": brand_id,
            "images_found": len(contents.images),
            "rows_in_manifest": 0,
            "written": 0,
            "errors": contents.errors,
            "status": "failed",
        }

    defaults = contents.defaults or {}
    total_rows = len(contents.manifest_rows)
    _emit("parsing", 10, f"Found {len(contents.images)} images / {total_rows} manifest rows.", total=total_rows)

    db = get_firestore()
    written = 0
    errors: list[str] = list(contents.errors)
    # Token + char accounting so the parent can persist a Sessions row with
    # cost_inr / input_tokens like every other v2.1 training run.
    total_in_tokens = 0
    total_out_tokens = 0
    total_embed_chars = 0

    # Match images case-insensitively for resilience.
    image_index = {name.lower(): (name, data) for name, data in contents.images.items()}

    for i, row in enumerate(contents.manifest_rows):
        fname_raw = str(row.get("image_filename", "")).strip()
        if not fname_raw:
            errors.append(f"row {i+1}: missing image_filename")
            continue
        matched = image_index.get(fname_raw.lower())
        if not matched:
            errors.append(f"row {i+1}: image '{fname_raw}' not in zip")
            continue
        real_name, img_bytes = matched

        try:
            content_type = guess_content_type(real_name)
            gcs_path = upload_bytes(brand_id, pack_id, real_name, img_bytes, content_type=content_type)
        except Exception as exc:
            errors.append(f"row {i+1}: GCS upload failed: {exc}")
            continue

        try:
            caption, cap_in, cap_out = await caption_image(img_bytes, mime_type=content_type)
            total_in_tokens += cap_in
            total_out_tokens += cap_out
        except Exception as exc:
            logger.warning("caption call raised: %s", exc)
            caption = {}

        headline = str(row.get("headline") or "").strip()
        body = str(row.get("body") or "").strip()
        cta = str(row.get("cta") or "").strip()

        embed_text = _build_embedding_text(caption, headline, body)
        total_embed_chars += len(embed_text)
        embedding_id = ""
        try:
            docs = await embed_texts([embed_text], use_cache=True)
            if docs:
                embedding_id = docs[0].id
                _persist_embedding_cache(
                    db, docs[0].id, embed_text, caption,
                    headline=headline, body=body, brand_id=brand_id,
                )
        except Exception as exc:
            logger.debug("embedding failed (non-fatal): %s", exc)

        asset_id = uuid.uuid4().hex[:20]
        try:
            db.collection("creative_assets").document(asset_id).set({
                "brand_id": brand_id,
                "hotel_id": _resolve_hotel_id(row, defaults),
                "pack_id": pack_id,
                "run_id": run_id,
                "image_filename": real_name,
                "gcs_path": gcs_path,
                "campaign_name": _first(row, defaults, "campaign_name"),
                "season": _first(row, defaults, "season"),
                "theme": _first(row, defaults, "theme"),
                "date_start": _first(row, defaults, "date_start"),
                "date_end": _first(row, defaults, "date_end"),
                "headline": headline,
                "body": body,
                "cta": cta,
                "platform": str(row.get("platform") or "").strip(),
                "persona": str(row.get("persona") or "").strip(),
                "hero_offer": str(row.get("hero_offer") or "").strip(),
                "caption_json": caption,
                "embedding_id": embedding_id,
                "ingested_by": user_email or user_id,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            })
            written += 1
        except Exception as exc:
            errors.append(f"row {i+1}: Firestore write failed: {exc}")
            continue

        pct = 10 + int(85 * (i + 1) / max(total_rows, 1))
        _emit("captioning", min(95, pct), f"Captioned & embedded {written}/{total_rows}", processed=written, total=total_rows)

    _emit(
        "completed", 100,
        f"Done — {written}/{total_rows} assets ingested. {len(errors)} warning(s).",
        processed=written, total=total_rows, status="completed",
    )

    return {
        "pack_id": pack_id,
        "brand_id": brand_id,
        "images_found": len(contents.images),
        "rows_in_manifest": total_rows,
        "written": written,
        "errors": errors[:20],
        "status": "completed",
        # Token + char accounting for the Sessions table cost rollup.
        "caption_input_tokens": int(total_in_tokens),
        "caption_output_tokens": int(total_out_tokens),
        "caption_model": _CAPTION_MODEL,
        "embed_chars": int(total_embed_chars),
    }


def _resolve_hotel_id(row: dict, defaults: dict) -> str:
    return str(row.get("hotel_id") or defaults.get("hotel_id") or "").strip()


def _first(row: dict, defaults: dict, key: str) -> str:
    v = row.get(key)
    if v not in (None, ""):
        return str(v).strip()
    v = defaults.get(key)
    return str(v).strip() if v not in (None, "") else ""


def _build_embedding_text(caption: dict, headline: str, body: str) -> str:
    pieces: list[str] = []
    if caption:
        motifs = ", ".join(caption.get("motifs") or []) if isinstance(caption.get("motifs"), list) else ""
        palette = ", ".join(caption.get("palette_tokens") or []) if isinstance(caption.get("palette_tokens"), list) else ""
        pieces.append(
            f"mood: {caption.get('mood', '')} | hero: {caption.get('hero_subject', '')} | "
            f"palette: {palette} | motifs: {motifs} | "
            f"photo: {caption.get('photography_style', '')} | logo: {caption.get('logo_unit_placement', '')}"
        )
    if headline:
        pieces.append(f"headline: {headline}")
    if body:
        pieces.append(f"body: {body[:400]}")
    return " || ".join(p for p in pieces if p).strip()


def _persist_embedding_cache(
    db,
    embed_id: str,
    text: str,
    caption: dict,
    headline: str,
    body: str,
    brand_id: str,
) -> None:
    """Mirror existing pattern: write text + metadata to embedding_cache so
    rag_engine._fetch_documents_by_ids returns rich context."""
    try:
        db.collection("embedding_cache").document(embed_id).set({
            "text": text,
            "headline": headline,
            "description": body,
            "campaign_type": "creative_asset",
            "section_type": "creative_assets",
            "brand_id": brand_id,
            "caption_json": caption,
            "performance_score": 1.0,    # creative assets are curated, not scored
        }, merge=True)
    except Exception as exc:
        logger.debug("creative_asset embedding_cache write failed: %s", exc)
