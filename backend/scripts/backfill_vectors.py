"""One-time migration script: Firestore ad_insights + brand_usps → Vertex AI Vector Search.

Run once after Vector Search index is set up and VECTOR_SEARCH_INDEX_ENDPOINT is configured.

Usage:
    export GCP_PROJECT_ID=supple-moon-495404-b0
    export VECTOR_SEARCH_INDEX_ENDPOINT=<your_endpoint_id>
    python -m backend.scripts.backfill_vectors
"""
import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vantage.backfill")


async def backfill():
    from backend.app.core.database import get_firestore
    from backend.app.services.embedding.vertex_embedder import embed_texts

    db = get_firestore()
    total_embedded = 0

    # Backfill ad_insights
    logger.info("Backfilling ad_insights collection...")
    ad_docs = list(db.collection("ad_insights").stream())
    for doc in ad_docs:
        data = doc.to_dict()
        hotel_name = data.get("hotel_name", "_global")
        texts_to_embed = []

        if data.get("insight_text"):
            texts_to_embed.append(data["insight_text"])
        for h in data.get("top_headlines", [])[:10]:
            if h:
                texts_to_embed.append(f"Headline: {h}")
        for d in data.get("top_descriptions", [])[:10]:
            if d:
                texts_to_embed.append(f"Description: {d}")

        if texts_to_embed:
            metadata = [{"brand_id": hotel_name, "section_type": "ad_performance", "text": t} for t in texts_to_embed]
            await embed_texts(texts_to_embed, metadata_list=metadata, use_cache=True)
            total_embedded += len(texts_to_embed)
            logger.info("  Embedded %d texts for hotel: %s", len(texts_to_embed), hotel_name)

    # Backfill brand_usps
    logger.info("Backfilling brand_usps collection...")
    usp_docs = list(db.collection("brand_usps").stream())
    for doc in usp_docs:
        data = doc.to_dict()
        hotel_name = data.get("hotel_name", "_global")
        usps = data.get("usps", [])
        if usps:
            metadata = [{"brand_id": hotel_name, "section_type": "brand_usp", "text": u} for u in usps]
            await embed_texts(usps, metadata_list=metadata, use_cache=True)
            total_embedded += len(usps)
            logger.info("  Embedded %d USPs for hotel: %s", len(usps), hotel_name)

    logger.info("Backfill complete. Total texts embedded: %d", total_embedded)


if __name__ == "__main__":
    if not os.environ.get("VECTOR_SEARCH_INDEX_ENDPOINT"):
        logger.error("VECTOR_SEARCH_INDEX_ENDPOINT must be set before running backfill.")
        sys.exit(1)
    asyncio.run(backfill())
