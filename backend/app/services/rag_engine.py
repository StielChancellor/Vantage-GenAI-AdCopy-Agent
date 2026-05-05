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


async def retrieve_ad_insights(
    hotel_name: str,
    query_context: str = "",
    campaign_type: str | None = None,
    season: str | None = None,
    flight_date=None,
) -> dict:
    """Retrieve semantically relevant ad performance insights for a hotel.

    v2.1: campaign_type and season filter the vector search so that a Demand
    Gen video request only retrieves Demand Gen video exemplars from matching
    seasons. Falls through to Firestore keyword search if Vector Search is
    unavailable.
    """
    query = query_context or f"Best performing ad headlines and descriptions for {hotel_name}"

    # Derive season from flight_date if not given explicitly
    if not season and flight_date:
        try:
            from backend.app.services.ingestion.normalized_record import season_for_month
            from datetime import date as _date, datetime as _dt
            if isinstance(flight_date, str):
                d = _dt.fromisoformat(flight_date).date()
            elif isinstance(flight_date, _dt):
                d = flight_date.date()
            elif isinstance(flight_date, _date):
                d = flight_date
            else:
                d = None
            if d:
                season = season_for_month(d.month)
        except Exception:
            pass

    passages = await _semantic_retrieve(
        query,
        brand_id=hotel_name,
        section_type=None,                  # search across both google_ads_export and moengage_push
        campaign_type=campaign_type,
        season=season,
        min_impression_bucket="mid",        # exclude low-volume noise
    )

    # If type-filtered search returned nothing, retry without the season constraint
    # (a brand might not have winter Demand Gen video exemplars yet).
    if not passages and (campaign_type or season):
        passages = await _semantic_retrieve(
            query, brand_id=hotel_name, campaign_type=campaign_type,
            min_impression_bucket="mid",
        )

    if passages:
        return _format_passages_as_insights(passages, campaign_type=campaign_type, season=season)

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
    campaign_type: str | None = None,
    season: str | None = None,
    min_impression_bucket: str | None = None,
) -> list[dict]:
    """Core semantic retrieval: embed → ANN search → Firestore fetch → rank by perf_score."""
    try:
        from backend.app.services.embedding.vertex_embedder import embed_texts
        embedded = await embed_texts([query], use_cache=False)
        if not embedded:
            return []
        query_embedding = embedded[0].embedding
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        return []

    try:
        from backend.app.services.embedding.vector_index_manager import query_similar
        neighbors = await query_similar(
            query_embedding=query_embedding,
            top_k=top_k,
            brand_id=brand_id,
            section_type=section_type,
            campaign_type=campaign_type,
            season=season,
            min_impression_bucket=min_impression_bucket,
        )
    except Exception as exc:
        logger.warning("Vector Search query failed: %s", exc)
        return []

    if not neighbors:
        return []

    passages = _fetch_documents_by_ids([n["id"] for n in neighbors])
    if not passages:
        return []

    id_to_distance = {n["id"]: n["distance"] for n in neighbors}
    for p in passages:
        p["_distance"] = id_to_distance.get(p.get("id", ""), 999)

    # v2.1: prefer performance_score (already on each passage) over Gemini re-rank.
    # Performance score blends recency × impressions × CTR — much more reliable
    # than text-similarity for ranking historical exemplars.
    passages.sort(
        key=lambda p: (p.get("performance_score", 0), -p.get("_distance", 999)),
        reverse=True,
    )
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


def _format_passages_as_insights(
    passages: list[dict],
    campaign_type: str | None = None,
    season: str | None = None,
) -> dict:
    """Format semantic search results for ad_generator consumption.
    v2.1 returns rich, typed exemplars instead of raw concatenated text so
    ad_generator can build a structured 'TOP PERFORMERS FOR {type}' block."""
    exemplars = []
    headlines = []
    descriptions = []
    for p in passages:
        h = (p.get("headline") or "").strip()
        d = (p.get("description") or "").strip()
        if not h and not d:
            continue
        exemplars.append({
            "headline": h,
            "description": d,
            "campaign_type": p.get("campaign_type", ""),
            "ad_strength": p.get("ad_strength", ""),
            "impressions": p.get("impressions", 0),
            "ctr": p.get("ctr", 0.0),
            "performance_score": round(p.get("performance_score", 0.0), 4),
            "month": p.get("month"),
            "season": p.get("season", ""),
        })
        if h:
            headlines.append(h)
        if d:
            descriptions.append(d)

    insight_text_lines = []
    if exemplars:
        scope = campaign_type or "all campaign types"
        if season:
            scope += f" — {season}"
        insight_text_lines.append(f"Top historical performers (scope: {scope}):")
        for ex in exemplars[:5]:
            insight_text_lines.append(
                f"- [{ex['campaign_type']}] \"{ex['headline']}\" / \"{ex['description'][:120]}\" "
                f"— score {ex['performance_score']}, "
                f"{ex['impressions']} impressions, CTR {ex['ctr']}%"
            )

    return {
        "hotel_name": "_semantic",
        "insight_text": "\n".join(insight_text_lines),
        "top_headlines": headlines[:5],
        "top_descriptions": descriptions[:5],
        "patterns": [],
        "exemplars": exemplars,
        "source": "vector_search",
        "scope_campaign_type": campaign_type,
        "scope_season": season,
        "total_ads_analyzed": len(passages),
    }
