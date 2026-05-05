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
        return []

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
