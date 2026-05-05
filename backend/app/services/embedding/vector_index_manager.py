"""Vertex AI Vector Search (ANN) index manager.

Handles upsert and query operations against the Vector Search index.
Index must be pre-created in GCP Console or via gcloud, then deployed to
an IndexEndpoint. Configure endpoint ID via VECTOR_SEARCH_INDEX_ENDPOINT env var.
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
    """Upsert embedded documents to the Vector Search index.

    If the index endpoint is not configured, logs a warning and skips.
    This keeps the system working without Vector Search during initial setup.
    """
    endpoint = _get_endpoint()
    if endpoint is None:
        logger.warning(
            "VECTOR_SEARCH_INDEX_ENDPOINT not set — skipping vector upsert. "
            "Semantic RAG will fall back to Firestore keyword search."
        )
        return

    try:
        from google.cloud.aiplatform.matching_engine.matching_engine_index_endpoint import (
            NumericNamespace,
        )
        datapoints = []
        for doc in docs:
            dp = {
                "id": doc.id,
                "feature_vector": doc.embedding,
                "restricts": [
                    {
                        "namespace": "brand_id",
                        "allow_list": [doc.metadata.get("brand_id", "_global")],
                    }
                ],
                "numeric_restricts": [],
            }
            if doc.metadata.get("training_run_id"):
                dp["restricts"].append({
                    "namespace": "training_run_id",
                    "allow_list": [doc.metadata["training_run_id"]],
                })
            datapoints.append(dp)

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
) -> list[dict]:
    """Find the top_k most similar vectors for a given query embedding.

    Returns a list of {id, distance} dicts. The caller then fetches full
    document text from Firestore using the returned IDs.

    Falls back to empty list if Vector Search is not available.
    """
    endpoint = _get_endpoint()
    if endpoint is None:
        return []

    try:
        restricts = [{"namespace": "brand_id", "allow_list": [brand_id, "_global"]}]
        if section_type:
            restricts.append({"namespace": "section_type", "allow_list": [section_type]})

        response = endpoint.find_neighbors(
            deployed_index_id=_DEPLOYED_INDEX_ID,
            queries=[query_embedding],
            num_neighbors=top_k,
            restricts=restricts,
        )

        neighbors = []
        if response and response[0]:
            for neighbor in response[0]:
                neighbors.append({
                    "id": neighbor.id,
                    "distance": neighbor.distance,
                })
        return neighbors
    except Exception as exc:
        logger.warning("Vector Search query failed: %s", exc)
        return []
