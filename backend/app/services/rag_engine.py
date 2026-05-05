"""Semantic RAG engine — v2.0 full rewrite.

Replaces keyword substring Firestore scan with a 4-step pipeline:
  1. Embed the query via Vertex AI text-embedding-005
  2. ANN search via Vertex AI Vector Search (with brand_id metadata filter)
  3. Fetch full document text from Firestore by returned IDs
  4. Re-rank top-10 with a lightweight Gemini scoring call
  5. Return top-3 to top-5 passages as context chunks

Falls back gracefully to Firestore keyword search if Vector Search is
not yet configured (VECTOR_SEARCH_INDEX_ENDPOINT env var unset).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("vantage.rag")


async def retrieve_ad_insights(hotel_name: str, query_context: str = "") -> dict:
    """Retrieve semantically relevant ad performance insights for a hotel.

    Args:
        hotel_name: The hotel/brand name (used as brand_id).
        query_context: Optional text describing the current ad brief (improves relevance).

    Returns:
        Dict with insight_text, top_headlines, top_descriptions, patterns.
    """
    query = query_context or f"Best performing ad headlines and descriptions for {hotel_name}"

    # Try semantic retrieval
    passages = await _semantic_retrieve(query, brand_id=hotel_name, section_type="ad_performance")

    if passages:
        return _format_passages_as_insights(passages)

    # Fallback: Firestore keyword scan (original v1 behavior)
    return _firestore_fallback_insights(hotel_name)


async def get_brand_usps(hotel_name: str) -> dict | None:
    """Retrieve brand USP data — semantic search then Firestore fallback."""
    query = f"Brand USPs, unique selling propositions, differentiators for {hotel_name}"
    passages = await _semantic_retrieve(query, brand_id=hotel_name, section_type="brand_usp")

    if passages:
        usps = [p["text"] for p in passages if p.get("text")]
        return {
            "hotel_name": hotel_name,
            "usps": usps,
            "positive_keywords": [],
            "restricted_keywords": [],
            "source": "vector_search",
        }

    # Firestore fallback
    return _firestore_fallback_usps(hotel_name)


async def _semantic_retrieve(
    query: str,
    brand_id: str,
    section_type: str | None = None,
    top_k: int = 10,
) -> list[dict]:
    """Core semantic retrieval: embed → ANN search → Firestore fetch → re-rank."""
    # Step 1: Embed query
    try:
        from backend.app.services.embedding.vertex_embedder import embed_texts
        embedded = await embed_texts([query], use_cache=False)
        if not embedded:
            return []
        query_embedding = embedded[0].embedding
    except Exception as exc:
        logger.warning("Embedding failed, falling back to keyword search: %s", exc)
        return []

    # Step 2: ANN search
    try:
        from backend.app.services.embedding.vector_index_manager import query_similar
        neighbors = await query_similar(
            query_embedding=query_embedding,
            top_k=top_k,
            brand_id=brand_id,
            section_type=section_type,
        )
    except Exception as exc:
        logger.warning("Vector Search query failed: %s", exc)
        return []

    if not neighbors:
        return []

    # Step 3: Fetch full text from Firestore by content hash IDs
    passages = _fetch_documents_by_ids([n["id"] for n in neighbors])
    if not passages:
        return []

    # Attach distances for re-ranking
    id_to_distance = {n["id"]: n["distance"] for n in neighbors}
    for p in passages:
        p["_distance"] = id_to_distance.get(p.get("id", ""), 999)

    # Step 4: Re-rank top-10 with Gemini (only if we have enough results)
    if len(passages) >= 5:
        passages = await _rerank_with_gemini(query, passages[:10])

    return passages[:5]


async def _rerank_with_gemini(query: str, passages: list[dict]) -> list[dict]:
    """Use Gemini to re-rank passages by relevance to the query."""
    try:
        from backend.app.core.vertex_client import get_generative_model
        import json

        passages_text = "\n".join(
            [f"[{i}] {p.get('text', '')[:200]}" for i, p in enumerate(passages)]
        )
        prompt = (
            f'Given this advertising brief: "{query}"\n\n'
            "Rank these passages from most to least relevant "
            "(output only a JSON array of indices, e.g. [2, 0, 4, 1, 3]):\n\n"
            f"{passages_text}\n\nReturn ONLY a JSON array of indices."
        )

        model = get_generative_model()
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1].split("```")[0]
        indices = json.loads(text)
        if isinstance(indices, list):
            return [passages[i] for i in indices if i < len(passages)]
    except Exception as exc:
        logger.debug("Gemini re-ranking failed (using ANN order): %s", exc)

    return sorted(passages, key=lambda p: p.get("_distance", 999))


def _fetch_documents_by_ids(doc_ids: list[str]) -> list[dict]:
    """Fetch document text from Firestore embedding_cache by content hash."""
    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
        results = []
        for doc_id in doc_ids:
            doc = db.collection("embedding_cache").document(doc_id).get()
            if doc.exists:
                data = doc.to_dict()
                results.append({"id": doc_id, "text": data.get("text", ""), **data})
        return results
    except Exception as exc:
        logger.warning("Firestore fetch failed: %s", exc)
        return []


def _firestore_fallback_insights(hotel_name: str) -> dict:
    """Original v1 keyword search — used when Vector Search unavailable."""
    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
        docs = list(
            db.collection("ad_insights").where("hotel_name", "==", hotel_name).limit(1).stream()
        )
        if docs:
            return docs[0].to_dict()
        global_docs = list(
            db.collection("ad_insights").where("hotel_name", "==", "_global").limit(1).stream()
        )
        if global_docs:
            return global_docs[0].to_dict()
    except Exception:
        pass
    return {}


def _firestore_fallback_usps(hotel_name: str) -> dict | None:
    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
        docs = list(
            db.collection("brand_usps").where("hotel_name", "==", hotel_name).limit(1).stream()
        )
        if docs:
            return docs[0].to_dict()
    except Exception:
        pass
    return None


def _format_passages_as_insights(passages: list[dict]) -> dict:
    """Format semantic search results into the insight dict shape expected by ad_generator."""
    texts = [p.get("text", "") for p in passages if p.get("text")]
    return {
        "hotel_name": "_semantic",
        "insight_text": "\n\n".join(texts[:3]),
        "top_headlines": [],
        "top_descriptions": [],
        "patterns": [],
        "source": "vector_search",
        "total_ads_analyzed": len(passages),
    }
