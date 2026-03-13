"""RAG engine for retrieving historical high-performing ad copies."""
from backend.app.core.database import get_chroma, get_firestore


def retrieve_top_ads(hotel_name: str, n_results: int = 5) -> list[dict]:
    """Retrieve top-performing historical ads for a specific hotel.

    Falls back to global top 10% if hotel has no data (cold start).
    """
    chroma = get_chroma()

    try:
        collection = chroma.get_collection("historical_ads")
    except Exception:
        return []

    # Try hotel-specific query first
    results = collection.query(
        query_texts=[hotel_name],
        n_results=n_results * 2,
        where={"hotel_name": hotel_name},
    )

    ads = _parse_chroma_results(results)

    if not ads:
        # Cold start fallback: query global top performers
        all_results = collection.get(include=["metadatas", "documents"])

        if not all_results["documents"]:
            return []

        # Sort by CTR + CVR combined score, take top 10%
        scored = []
        for i, meta in enumerate(all_results["metadatas"]):
            score = meta.get("ctr", 0) + meta.get("cvr", 0)
            scored.append(
                {
                    "text": all_results["documents"][i],
                    "hotel_name": meta.get("hotel_name", "unknown"),
                    "headlines": meta.get("headlines", ""),
                    "descriptions": meta.get("descriptions", ""),
                    "ctr": meta.get("ctr", 0),
                    "cvr": meta.get("cvr", 0),
                    "score": score,
                }
            )

        scored.sort(key=lambda x: x["score"], reverse=True)
        top_pct = max(1, len(scored) // 10)
        ads = scored[:top_pct][:n_results]

    # Sort by performance
    ads.sort(key=lambda x: x.get("ctr", 0) + x.get("cvr", 0), reverse=True)
    return ads[:n_results]


def _parse_chroma_results(results: dict) -> list[dict]:
    """Parse ChromaDB query results into a list of ad dicts."""
    if not results or not results.get("documents") or not results["documents"][0]:
        return []

    ads = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i] if results.get("metadatas") else {}
        ads.append(
            {
                "text": doc,
                "hotel_name": meta.get("hotel_name", "unknown"),
                "headlines": meta.get("headlines", ""),
                "descriptions": meta.get("descriptions", ""),
                "ctr": meta.get("ctr", 0),
                "cvr": meta.get("cvr", 0),
            }
        )
    return ads


def get_brand_usps(hotel_name: str) -> dict | None:
    """Retrieve brand USP data for a hotel from Firestore."""
    db = get_firestore()
    docs = list(
        db.collection("brand_usps").where("hotel_name", "==", hotel_name).limit(1).stream()
    )
    if docs:
        return docs[0].to_dict()
    return None
