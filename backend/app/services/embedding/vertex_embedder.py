"""Vertex AI text embedding service with content-hash caching.

Uses text-embedding-005 (768-dimensional). Caches embeddings in Firestore
by content hash to avoid re-embedding identical text across training runs.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("vantage.embedding")

_EMBEDDING_MODEL = "text-embedding-005"
_EMBEDDING_DIM = 768

_embed_model = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from vertexai.language_models import TextEmbeddingModel
        from backend.app.core.vertex_client import _ensure_init
        _ensure_init()
        _embed_model = TextEmbeddingModel.from_pretrained(_EMBEDDING_MODEL)
    return _embed_model


@dataclass
class EmbeddedDocument:
    id: str
    text: str
    embedding: list[float]
    metadata: dict


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def embed_texts(
    texts: list[str],
    metadata_list: list[dict] | None = None,
    use_cache: bool = True,
) -> list[EmbeddedDocument]:
    """Embed a list of texts. Returns EmbeddedDocument list with IDs and embeddings.

    Checks Firestore content-hash cache before calling Vertex AI.
    """
    if not texts:
        return []

    metadata_list = metadata_list or [{} for _ in texts]
    results: list[EmbeddedDocument] = []
    to_embed_indices: list[int] = []
    to_embed_texts: list[str] = []

    # Check cache for each text
    if use_cache:
        db = _get_firestore()
        for i, text in enumerate(texts):
            content_hash = _hash_text(text)
            cached = _get_cached_embedding(db, content_hash)
            if cached:
                results.append(EmbeddedDocument(
                    id=content_hash,
                    text=text,
                    embedding=cached,
                    metadata=metadata_list[i],
                ))
            else:
                to_embed_indices.append(i)
                to_embed_texts.append(text)
    else:
        to_embed_indices = list(range(len(texts)))
        to_embed_texts = texts

    # Embed uncached texts
    if to_embed_texts:
        model = _get_embed_model()
        embeddings = model.get_embeddings(to_embed_texts)

        if use_cache:
            db = _get_firestore()

        for pos, (orig_idx, emb_result) in enumerate(zip(to_embed_indices, embeddings)):
            text = texts[orig_idx]
            content_hash = _hash_text(text)
            embedding_values = emb_result.values

            if use_cache:
                _cache_embedding(db, content_hash, embedding_values)

            results.insert(
                orig_idx,
                EmbeddedDocument(
                    id=content_hash,
                    text=text,
                    embedding=embedding_values,
                    metadata=metadata_list[orig_idx],
                ),
            )

    return results


async def embed_dataframe_chunk(
    texts: list[str],
    brand_id: str = "",
    training_run_id: str = "",
) -> list[EmbeddedDocument]:
    """Legacy wrapper — embeds raw text with minimal metadata.
    Use embed_records() for the v2.1 NormalizedAdRecord path.
    """
    metadata = [{"brand_id": brand_id, "training_run_id": training_run_id} for _ in texts]
    docs = await embed_texts(texts, metadata_list=metadata)
    if docs:
        try:
            from backend.app.services.embedding.vector_index_manager import upsert_vectors
            await upsert_vectors(docs)
        except Exception as exc:
            logger.warning("Vector Search upsert failed (non-fatal): %s", exc)
    return docs


async def embed_records(
    records: list,  # list[NormalizedAdRecord]
    brand_id: str,
    training_run_id: str,
    section_type: str,
) -> list[EmbeddedDocument]:
    """Embed NormalizedAdRecord list with full metadata for retrieval filtering.

    Records with performance_score == 0 (below impression floor) are SKIPPED —
    we keep them in BigQuery for archival but don't pollute the vector index
    with low-confidence noise.

    The text actually embedded is `[campaign_type] headline — description`
    so the embedding space naturally separates campaign sub-types.
    """
    if not records:
        return []

    eligible = [r for r in records if r.performance_score > 0]
    if not eligible:
        logger.info(
            "embed_records: 0/%d records eligible (all below impression floor)",
            len(records),
        )
        return []

    texts = [r.as_embedding_text() for r in eligible]
    metadata = [r.as_metadata(brand_id, training_run_id, section_type) for r in eligible]

    # Persist text + metadata in Firestore so RAG can fetch full context by ID.
    docs = await embed_texts(texts, metadata_list=metadata, use_cache=True)
    _persist_record_text(docs, eligible)

    # Push to Vector Search with rich restricts
    try:
        from backend.app.services.embedding.vector_index_manager import upsert_vectors
        await upsert_vectors(docs)
    except Exception as exc:
        logger.warning("Vector Search upsert failed (non-fatal): %s", exc)

    logger.info(
        "embed_records: embedded %d/%d records for brand=%s section=%s",
        len(docs), len(records), brand_id, section_type,
    )
    return docs


def _persist_record_text(docs: list[EmbeddedDocument], records: list) -> None:
    """Save each embedded record's text + metadata to Firestore embedding_cache
    so rag_engine._fetch_documents_by_ids can return rich context (not just embeddings)."""
    if not docs:
        return
    try:
        db = _get_firestore()
        for doc, rec in zip(docs, records):
            db.collection("embedding_cache").document(doc.id).set({
                "text": doc.text,
                "headline": rec.headline,
                "description": rec.description,
                "campaign_type": rec.campaign_type,
                "ad_strength": rec.ad_strength,
                "impressions": rec.impressions,
                "ctr": rec.ctr,
                "performance_score": rec.performance_score,
                "month": rec.month,
                "season": rec.season,
                "hour_of_day": rec.hour_of_day,
                "day_of_week": rec.day_of_week,
                "brand_id": doc.metadata.get("brand_id", ""),
                "section_type": doc.metadata.get("section_type", ""),
            }, merge=True)
    except Exception as exc:
        logger.debug("Firestore record-text persist failed: %s", exc)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _get_firestore():
    from backend.app.core.database import get_firestore
    return get_firestore()


def _get_cached_embedding(db, content_hash: str) -> list[float] | None:
    try:
        doc = db.collection("embedding_cache").document(content_hash).get()
        if doc.exists:
            return doc.to_dict().get("embedding")
    except Exception:
        pass
    return None


def _cache_embedding(db, content_hash: str, embedding: list[float]) -> None:
    try:
        db.collection("embedding_cache").document(content_hash).set({
            "embedding": embedding,
            "model": _EMBEDDING_MODEL,
        }, merge=True)
    except Exception:
        pass
