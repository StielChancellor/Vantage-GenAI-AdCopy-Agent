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
    scope: str = "hotel",
    brand_id: str | None = None,
    hotel_id: str | None = None,
    hotel_name_for_anonymize: str | None = None,
    city_for_anonymize: str | None = None,
    is_loyalty: bool = False,
) -> dict:
    """Retrieve semantically relevant ad performance insights.

    v2.2 adds **scope** awareness so brand-level generations don't leak hotel-
    specific identity into the prompt:

    - scope='hotel'   → existing v2.1 behavior; no anonymization.
    - scope='brand'   → pull anonymized hotel exemplars (strip property names,
       cities) so the model learns generic patterns under the brand's voice
       without parroting individual hotel facts.
    - scope='loyalty' (v2.4, or `is_loyalty=True`) → loyalty-programme mode.
       Pulls (a) the loyalty brand's own training, then (b) anonymized exemplars
       from EVERY non-loyalty brand so the loyalty programme inherits chain-wide
       voice. All cross-brand passages run through the anonymization pipeline.
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

    # Brand id used as the vector restrict — fall back to the hotel_name string
    # for backwards compatibility.
    vector_brand_id = brand_id or hotel_name

    passages = await _semantic_retrieve(
        query,
        brand_id=vector_brand_id,
        section_type=None,
        campaign_type=campaign_type,
        season=season,
        min_impression_bucket="mid",
    )

    if not passages and (campaign_type or season):
        passages = await _semantic_retrieve(
            query, brand_id=vector_brand_id, campaign_type=campaign_type,
            min_impression_bucket="mid",
        )

    # v2.4 — loyalty mode: also pull cross-brand exemplars from every non-loyalty
    # brand and anonymize them, so the loyalty programme picks up chain-wide voice.
    cross_brand_passages: list[dict] = []
    if (scope == "loyalty" or is_loyalty):
        try:
            from backend.app.core.database import get_firestore
            db = get_firestore()
            partner_brand_ids: list[str] = []
            for d in db.collection("brands").stream():
                if d.id == brand_id:
                    continue
                if (d.to_dict() or {}).get("kind", "hotel") == "loyalty":
                    continue
                partner_brand_ids.append(d.id)
            for pbid in partner_brand_ids[:8]:   # cap fan-out
                got = await _semantic_retrieve(
                    query, brand_id=pbid, section_type=None,
                    campaign_type=campaign_type, season=season,
                    min_impression_bucket="mid",
                )
                cross_brand_passages.extend(got[:2])   # keep top 2 per partner
            if cross_brand_passages:
                cross_brand_passages = [
                    _anonymize_passage(p, extra_terms=[]) for p in cross_brand_passages
                ]
        except Exception as exc:
            logger.debug("Loyalty cross-brand retrieval failed: %s", exc)

    # v2.2 anonymization: when scope='brand' or loyalty, sanitize hotel-specific tokens.
    if scope in ("brand", "loyalty") and passages:
        hotel_tokens = []
        if hotel_name_for_anonymize:
            hotel_tokens.append(hotel_name_for_anonymize)
        if city_for_anonymize:
            hotel_tokens.append(city_for_anonymize)
        passages = [_anonymize_passage(p, extra_terms=hotel_tokens) for p in passages]

    # Merge loyalty cross-brand pool AFTER anonymization of the primary set.
    if cross_brand_passages:
        passages = (passages or []) + cross_brand_passages

    if passages:
        out = _format_passages_as_insights(
            passages, campaign_type=campaign_type, season=season, scope=scope,
        )
        if cross_brand_passages:
            out["cross_brand_count"] = len(cross_brand_passages)
            out["loyalty_mode"] = True
        return out

    return _firestore_fallback_insights(hotel_name)


_AMENITY_RE = None
def _get_amenity_re():
    """Lazy compile — strip phrases that wrap a hotel-specific noun in possessive form,
    e.g. "ITC Maurya's spa" → "the spa", "Mumbai's largest pool" → "the largest pool"."""
    global _AMENITY_RE
    if _AMENITY_RE is None:
        import re
        _AMENITY_RE = re.compile(r"\b([A-Z][\w]*(?:\s+[A-Z][\w]*)*)['’]s\b")
    return _AMENITY_RE


def _anonymize_passage(passage: dict, extra_terms: list[str] | None = None) -> dict:
    """Strip hotel-specific identity tokens from a passage so brand-level
    generations don't leak property names. Operates on a SHALLOW COPY so the
    Firestore-cached source isn't mutated."""
    import re

    p = dict(passage)
    text = (p.get("headline") or "") + " || " + (p.get("description") or "")

    # 1. Remove brand+property names from the passage's own metadata
    for tok in [p.get("hotel_name"), p.get("business_name")]:
        if tok and isinstance(tok, str) and len(tok) > 2:
            text = re.sub(re.escape(tok), "the property", text, flags=re.IGNORECASE)

    # 2. Caller-supplied extras (typically the active selection's hotel + city)
    for tok in extra_terms or []:
        if tok and isinstance(tok, str) and len(tok) > 2:
            text = re.sub(re.escape(tok), "the property", text, flags=re.IGNORECASE)

    # 3. Generic possessive replacement: "Mumbai's pool" → "the pool"
    text = _get_amenity_re().sub("the", text)

    # Split back
    if " || " in text:
        h, _, d = text.partition(" || ")
    else:
        h, d = text, ""
    p["headline"] = h.strip()
    p["description"] = d.strip()
    p["_anonymized"] = True
    # Drop identity metadata so downstream formatter doesn't surface it
    p.pop("hotel_name", None)
    return p


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


async def retrieve_visual_inspiration(
    theme_text: str,
    selection: dict | None = None,
    top_k: int = 8,
) -> dict:
    """v2.7 — Retrieve past creative-asset captions for the Campaign Ideation
    shortlist generator. Mirrors `retrieve_ad_insights` scoping rules:

      - scope='brand' | 'hotel' | 'multi' | 'city' → pull only that brand(s)'
        creative_assets.
      - scope='loyalty' (or selection.is_loyalty=True) → fan out across up to
        8 partner brands and anonymize the resulting passages.

    Returns a dict shaped:
      {
        assets: [ { id, brand_id, caption_json, headline, body, ... }, ... ],
        loyalty_mode: bool,
        anonymized: bool,
      }
    """
    selection = selection or {}
    scope = selection.get("scope") or "hotel"
    is_loyalty = bool(selection.get("is_loyalty")) or scope == "loyalty"

    brand_ids: list[str] = []
    primary_brand_id = selection.get("brand_id") or ""
    if primary_brand_id:
        brand_ids.append(primary_brand_id)
    brand_ids.extend([b for b in (selection.get("brand_ids") or []) if b and b not in brand_ids])

    hotel_ids: list[str] = []
    if selection.get("hotel_id"):
        hotel_ids.append(selection["hotel_id"])
    hotel_ids.extend([h for h in (selection.get("hotel_ids") or []) if h and h not in hotel_ids])

    cities = list(selection.get("cities") or [])

    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
    except Exception as exc:
        logger.warning("retrieve_visual_inspiration: Firestore unavailable: %s", exc)
        return {"assets": [], "loyalty_mode": is_loyalty, "anonymized": False}

    matched_brands: set[str] = set(brand_ids)

    if hotel_ids:
        for hid in hotel_ids:
            try:
                d = db.collection("hotels").document(hid).get()
                if d.exists:
                    b = (d.to_dict() or {}).get("brand_id")
                    if b:
                        matched_brands.add(b)
            except Exception:
                pass

    if cities and not matched_brands:
        try:
            for d in db.collection("hotels").where("city", "in", cities[:10]).stream():
                b = (d.to_dict() or {}).get("brand_id")
                if b:
                    matched_brands.add(b)
        except Exception:
            pass

    assets: list[dict] = []

    def _pull_brand(bid: str, cap: int) -> list[dict]:
        try:
            stream = (
                db.collection("creative_assets")
                .where("brand_id", "==", bid)
                .limit(cap)
                .stream()
            )
            return [{"id": doc.id, **(doc.to_dict() or {})} for doc in stream]
        except Exception as exc:
            logger.debug("creative_assets fetch failed for %s: %s", bid, exc)
            return []

    if is_loyalty:
        # Pull anonymized exemplars across up to 8 non-loyalty partner brands.
        try:
            partner_ids: list[str] = []
            for d in db.collection("brands").stream():
                bdata = d.to_dict() or {}
                if bdata.get("kind", "hotel") == "loyalty":
                    continue
                partner_ids.append(d.id)
            for pid in partner_ids[:8]:
                per = _pull_brand(pid, max(2, top_k // 4))
                assets.extend(per[:2])
        except Exception as exc:
            logger.debug("loyalty fan-out failed: %s", exc)
        # Anonymize each
        anon: list[dict] = []
        for a in assets:
            anon.append(_anonymize_passage(a, extra_terms=[a.get("hotel_name")]))
        assets = anon
    else:
        for bid in list(matched_brands)[:5]:
            assets.extend(_pull_brand(bid, max(3, top_k // 2)))

    # Light ranking: prefer assets whose theme/season/captions overlap the theme_text.
    if theme_text:
        theme_lower = theme_text.lower()

        def _score(a: dict) -> int:
            cap = a.get("caption_json") or {}
            haystack = " ".join(str(v) for v in [
                cap.get("mood"),
                cap.get("theme_hint"),
                cap.get("season_hint"),
                cap.get("hero_subject"),
                " ".join(cap.get("motifs") or []) if isinstance(cap.get("motifs"), list) else "",
                " ".join(cap.get("palette_tokens") or []) if isinstance(cap.get("palette_tokens"), list) else "",
                a.get("campaign_name"),
                a.get("season"),
                a.get("theme"),
                a.get("headline"),
            ] if v).lower()
            score = 0
            for token in [t for t in theme_lower.replace(",", " ").split() if len(t) > 3]:
                if token in haystack:
                    score += 1
            return score

        assets.sort(key=_score, reverse=True)

    return {
        "assets": assets[:top_k],
        "loyalty_mode": is_loyalty,
        "anonymized": is_loyalty,
    }


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
    scope: str = "hotel",
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
        "scope": scope,
        "scope_campaign_type": campaign_type,
        "scope_season": season,
        "total_ads_analyzed": len(passages),
        "anonymized": scope == "brand",
    }
