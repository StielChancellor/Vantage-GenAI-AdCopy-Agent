"""Vertex AI Vector Search (ANN) index manager — v2.1.

Restricts namespaces written by upsert and accepted by query:
    brand_id, training_run_id, section_type, campaign_type,
    season, month, impression_bucket

Numeric restricts (used for "≥ N" style filters):
    performance_score
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger("vantage.vector_search")

_INDEX_ENDPOINT_ID = os.environ.get("VECTOR_SEARCH_INDEX_ENDPOINT", "")
_DEPLOYED_INDEX_ID = os.environ.get("VECTOR_SEARCH_DEPLOYED_INDEX_ID", "vantage_ads")
_PROJECT = os.environ.get("GCP_PROJECT_ID", "supple-moon-495404-b0")
_LOCATION = os.environ.get("VERTEX_AI_LOCATION", "us-central1")

_endpoint = None

# Categorical metadata namespaces written to every vector
_CATEGORICAL_NAMESPACES = [
    "brand_id", "training_run_id", "section_type",
    "campaign_type", "season", "month", "impression_bucket",
    "ad_strength",
]


def _get_endpoint():
    global _endpoint
    if _endpoint is None and _INDEX_ENDPOINT_ID:
        from google.cloud.aiplatform import MatchingEngineIndexEndpoint
        _endpoint = MatchingEngineIndexEndpoint(
            index_endpoint_name=_INDEX_ENDPOINT_ID,
            project=_PROJECT,
            location=_LOCATION,
        )
    return _endpoint


async def upsert_vectors(docs: list) -> None:
    """Upsert embedded documents with rich restricts."""
    endpoint = _get_endpoint()
    if endpoint is None:
        logger.warning(
            "VECTOR_SEARCH_INDEX_ENDPOINT not set — skipping vector upsert. "
            "Semantic RAG will fall back to Firestore keyword search."
        )
        return

    try:
        datapoints = []
        for doc in docs:
            md = doc.metadata or {}
            restricts = []
            for ns in _CATEGORICAL_NAMESPACES:
                v = md.get(ns)
                if v in (None, "", []):
                    continue
                if isinstance(v, list):
                    allow = [str(x) for x in v if x not in (None, "")]
                else:
                    allow = [str(v)]
                if allow:
                    restricts.append({"namespace": ns, "allow_list": allow})
            # Always tag brand with a fallback so global lookups work
            if not any(r["namespace"] == "brand_id" for r in restricts):
                restricts.append({"namespace": "brand_id", "allow_list": ["_global"]})

            numeric_restricts = []
            ps = md.get("performance_score")
            if isinstance(ps, (int, float)):
                numeric_restricts.append({
                    "namespace": "performance_score",
                    "value_float": float(ps),
                })

            datapoints.append({
                "id": doc.id,
                "feature_vector": doc.embedding,
                "restricts": restricts,
                "numeric_restricts": numeric_restricts,
            })

        endpoint.upsert_datapoints(datapoints=datapoints, deployed_index_id=_DEPLOYED_INDEX_ID)
        logger.info("Upserted %d vectors to Vector Search.", len(docs))
    except Exception as exc:
        logger.error("Vector Search upsert failed: %s", exc)
        raise


async def query_similar(
    query_embedding: list[float],
    top_k: int = 10,
    brand_id: str = "_global",
    section_type: str | None = None,
    campaign_type: str | None = None,
    season: str | None = None,
    month: int | str | None = None,
    min_impression_bucket: str | None = None,
) -> list[dict]:
    """Find the top_k most similar vectors with optional metadata filters.

    min_impression_bucket: 'low' | 'mid' | 'high' | 'mass' — when set, only
    vectors at that bucket OR HIGHER are returned (e.g. 'mid' allows mid+high+mass).
    """
    endpoint = _get_endpoint()
    if endpoint is None:
        # Option D fallback: cosine similarity over Firestore-stored embeddings.
        # Works at zero compute cost up to ~10K records per brand.
        return await _firestore_similarity_search(
            query_embedding=query_embedding,
            top_k=top_k,
            brand_id=brand_id,
            section_type=section_type,
            campaign_type=campaign_type,
            season=season,
            month=month,
            min_impression_bucket=min_impression_bucket,
        )

    try:
        restricts = [{"namespace": "brand_id", "allow_list": [brand_id, "_global"]}]
        if section_type:
            restricts.append({"namespace": "section_type", "allow_list": [section_type]})
        if campaign_type:
            restricts.append({"namespace": "campaign_type", "allow_list": [campaign_type]})
        if season:
            restricts.append({"namespace": "season", "allow_list": [season]})
        if month is not None:
            restricts.append({"namespace": "month", "allow_list": [str(month)]})
        if min_impression_bucket:
            buckets = ["low", "mid", "high", "mass"]
            if min_impression_bucket in buckets:
                allow = buckets[buckets.index(min_impression_bucket):]
                restricts.append({"namespace": "impression_bucket", "allow_list": allow})

        response = endpoint.find_neighbors(
            deployed_index_id=_DEPLOYED_INDEX_ID,
            queries=[query_embedding],
            num_neighbors=top_k,
            restricts=restricts,
        )

        neighbors = []
        if response and response[0]:
            for neighbor in response[0]:
                neighbors.append({"id": neighbor.id, "distance": neighbor.distance})
        return neighbors
    except Exception as exc:
        logger.warning("Vector Search query failed: %s", exc)
        return []


# ===========================================================================
# Option D — Firestore-backed cosine similarity (no VM, $0/mo).
# ===========================================================================

# Bounded fetch — we never scan more than this many docs per brand. Tune up
# when training data grows beyond a few thousand records.
_FIRESTORE_MAX_SCAN = 5000

_BUCKET_ORDER = ["low", "mid", "high", "mass"]


async def _firestore_similarity_search(
    query_embedding: list[float],
    top_k: int,
    brand_id: str,
    section_type: str | None,
    campaign_type: str | None,
    season: str | None,
    month: int | str | None,
    min_impression_bucket: str | None,
) -> list[dict]:
    """Compute cosine similarity in-process over embeddings stored in Firestore.

    Uses the same metadata filters as Vector Search would. Excludes records
    with performance_score == 0 (i.e. below the impression floor).
    """
    try:
        import numpy as np
        from backend.app.core.database import get_firestore
    except Exception as exc:
        logger.warning("Firestore similarity fallback unavailable (numpy missing?): %s", exc)
        return []

    db = get_firestore()
    coll = db.collection("embedding_cache")

    # Fetch by brand. Firestore composite-index limits make stacking equality
    # filters fragile across deployments, so we only constrain on brand server-
    # side and apply the rest of the filters client-side.
    try:
        query = coll.where("brand_id", "==", brand_id).limit(_FIRESTORE_MAX_SCAN)
        docs = list(query.stream())
        # Also include _global brand entries (cross-brand baselines)
        if brand_id != "_global":
            global_q = coll.where("brand_id", "==", "_global").limit(500)
            docs.extend(list(global_q.stream()))
    except Exception as exc:
        logger.warning("Firestore similarity fetch failed: %s", exc)
        return []

    if not docs:
        return []

    try:
        q = np.asarray(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []
    except Exception:
        return []

    min_bucket_idx = (
        _BUCKET_ORDER.index(min_impression_bucket)
        if min_impression_bucket in _BUCKET_ORDER else 0
    )

    candidates: list[tuple[float, str]] = []
    skipped_no_embedding = 0

    for d in docs:
        data = d.to_dict() or {}
        emb = data.get("embedding")
        if not emb:
            skipped_no_embedding += 1
            continue

        # Filter chain — same semantics as Vector Search restricts
        if section_type and data.get("section_type") and data["section_type"] != section_type:
            continue
        if campaign_type and data.get("campaign_type") != campaign_type:
            continue
        if season and data.get("season") and data["season"] != season:
            continue
        if month is not None and data.get("month") not in (None, "", str(month), int(month) if str(month).isdigit() else month):
            continue

        if min_impression_bucket:
            bucket = _bucket_for(data.get("impressions", 0))
            if _BUCKET_ORDER.index(bucket) < min_bucket_idx:
                continue

        # Performance floor — never recommend an ad that scored 0
        if (data.get("performance_score") or 0) <= 0:
            continue

        try:
            v = np.asarray(emb, dtype=np.float32)
            v_norm = np.linalg.norm(v)
            if v_norm == 0:
                continue
            sim = float(np.dot(q, v) / (q_norm * v_norm))
        except Exception:
            continue

        # We return "distance" to mirror Vector Search shape. Cosine distance
        # = 1 - cosine similarity (so smaller = more similar, just like ANN).
        distance = 1.0 - sim
        candidates.append((distance, d.id))

    candidates.sort(key=lambda x: x[0])
    if skipped_no_embedding:
        logger.debug("Firestore similarity: skipped %d docs missing embeddings", skipped_no_embedding)
    logger.info(
        "Firestore similarity: %d candidates after filters → top_k=%d (brand=%s, ct=%s, season=%s)",
        len(candidates), top_k, brand_id, campaign_type, season,
    )
    return [{"id": doc_id, "distance": dist} for dist, doc_id in candidates[:top_k]]


def _bucket_for(impressions) -> str:
    try:
        n = int(impressions or 0)
    except (TypeError, ValueError):
        n = 0
    if n >= 100_000:
        return "mass"
    if n >= 10_000:
        return "high"
    if n >= 1_000:
        return "mid"
    return "low"
