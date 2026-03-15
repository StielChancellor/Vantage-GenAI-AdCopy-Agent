"""CSV ingestion for historical ad data and brand USP data.

Historical ads are stored in Firestore, then analyzed by Gemini to produce
pre-processed insights that persist across Cloud Run restarts.
"""
import json
import re
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import google.generativeai as genai

from backend.app.core.config import get_settings
from backend.app.core.database import get_firestore
from backend.app.models.schemas import CSVUploadResponse

settings = get_settings()


def _extract_hotel_name(text: str) -> Optional[str]:
    """Extract hotel name from ad copy text.

    Heuristic: look for capitalized proper nouns that appear consistently.
    Common patterns: "Book [Hotel Name] Today", "[Hotel Name] - Best Rates"
    """
    if not isinstance(text, str):
        return None
    # Remove common ad phrases to isolate hotel name
    cleaned = re.sub(
        r"(book|now|today|best|rate|deal|offer|save|discount|luxury|resort|hotel|official|site|free)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Find sequences of capitalized words (likely hotel name)
    matches = re.findall(r"(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", cleaned)
    if matches:
        # Return the longest match as the most likely hotel name
        return max(matches, key=len).strip()
    return None


def _get_admin_model() -> str:
    """Get the admin-configured default model from Firestore."""
    try:
        db = get_firestore()
        doc = db.collection("admin_settings").document("config").get()
        if doc.exists:
            return doc.to_dict().get("default_model", "gemini-2.5-flash")
    except Exception:
        pass
    return "gemini-2.5-flash"


def _generate_insights(hotel_name: str, ads: list[dict]) -> dict:
    """Call Gemini to analyze historical ads and produce structured insights.

    Args:
        hotel_name: The hotel or brand name.
        ads: List of ad dicts with keys: headlines, descriptions, ctr, cvr.

    Returns:
        Insight dict ready for Firestore storage.
    """
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model_name = _get_admin_model()

    # Build the ads data for analysis
    ads_text = ""
    for i, ad in enumerate(ads[:100]):  # Limit to 100 ads to stay within token limits
        ads_text += f"\nAd {i + 1}:"
        ads_text += f"\n  Headlines: {ad.get('headlines', '')}"
        ads_text += f"\n  Descriptions: {ad.get('descriptions', '')}"
        ads_text += f"\n  CTR: {ad.get('ctr', 0)}%"
        ads_text += f"\n  CVR: {ad.get('cvr', 0)}%\n"

    prompt = f"""Analyze these {len(ads)} historical ad performance records for "{hotel_name}".

{ads_text}

Based on this data, provide a comprehensive analysis. Return ONLY valid JSON with this structure:
{{
  "insight_text": "2-3 paragraph summary of what makes ads perform well for this hotel. Include specific patterns, power words, themes, and CTR/CVR benchmarks.",
  "top_headlines": ["top 5 best-performing headlines by CTR+CVR combined"],
  "top_descriptions": ["top 5 best-performing descriptions by CTR+CVR combined"],
  "patterns": ["list of 5-8 key actionable findings, e.g. 'Urgency words like Book Now drove 40% higher CTR'", "Headlines under 25 chars outperformed longer ones by 2x"],
  "avg_ctr": <average CTR as number>,
  "avg_cvr": <average CVR as number>,
  "best_ctr": <highest CTR as number>,
  "best_cvr": <highest CVR as number>
}}"""

    system_prompt = """You are an expert advertising data analyst. Analyze historical ad performance data
and identify actionable patterns. Focus on what drives high CTR and CVR. Be specific with numbers and examples.
Output ONLY valid JSON matching the requested format."""

    try:
        model = genai.GenerativeModel(model_name, system_instruction=system_prompt)
        response = model.generate_content(prompt)

        # Parse response
        json_str = response.text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        insight_data = json.loads(json_str.strip())

        # Build the final insight document
        return {
            "hotel_name": hotel_name,
            "insight_text": insight_data.get("insight_text", ""),
            "top_headlines": insight_data.get("top_headlines", []),
            "top_descriptions": insight_data.get("top_descriptions", []),
            "patterns": insight_data.get("patterns", []),
            "avg_ctr": insight_data.get("avg_ctr", 0),
            "avg_cvr": insight_data.get("avg_cvr", 0),
            "best_ctr": insight_data.get("best_ctr", 0),
            "best_cvr": insight_data.get("best_cvr", 0),
            "total_ads_analyzed": len(ads),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        # Fallback: store basic stats without AI analysis
        ctrs = [ad.get("ctr", 0) for ad in ads if ad.get("ctr", 0) > 0]
        cvrs = [ad.get("cvr", 0) for ad in ads if ad.get("cvr", 0) > 0]

        # Sort by CTR + CVR and pick top performers
        sorted_ads = sorted(ads, key=lambda a: a.get("ctr", 0) + a.get("cvr", 0), reverse=True)
        top_5 = sorted_ads[:5]

        return {
            "hotel_name": hotel_name,
            "insight_text": f"Analysis of {len(ads)} historical ads. AI insight generation failed ({str(e)[:100]}). Showing raw top performers.",
            "top_headlines": [a.get("headlines", "").split(" | ")[0] for a in top_5 if a.get("headlines")],
            "top_descriptions": [a.get("descriptions", "").split(" | ")[0] for a in top_5 if a.get("descriptions")],
            "patterns": [],
            "avg_ctr": round(sum(ctrs) / len(ctrs), 2) if ctrs else 0,
            "avg_cvr": round(sum(cvrs) / len(cvrs), 2) if cvrs else 0,
            "best_ctr": max(ctrs) if ctrs else 0,
            "best_cvr": max(cvrs) if cvrs else 0,
            "total_ads_analyzed": len(ads),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


def ingest_historical_csv(df: pd.DataFrame) -> CSVUploadResponse:
    """Ingest historical ad performance CSV with dynamic column mapping.

    1. Parses CSV rows into structured ad records
    2. Stores raw ads in Firestore (persistent)
    3. Groups ads by hotel name
    4. Generates AI insights per hotel via Gemini
    5. Stores insights in Firestore ad_insights collection
    """
    db = get_firestore()

    # Dynamic column mapping: find headline, description, CTR, CVR columns
    cols = df.columns.tolist()
    headline_cols = [c for c in cols if "headline" in c.lower()]
    desc_cols = [c for c in cols if "description" in c.lower() or "desc" in c.lower()]
    ctr_col = next((c for c in cols if "ctr" in c.lower()), None)
    cvr_col = next((c for c in cols if "cvr" in c.lower() or "conversion" in c.lower()), None)

    hotels_found = set()
    rows_processed = 0
    hotel_ads = {}  # Group ads by hotel name for insight generation

    for idx, row in df.iterrows():
        # Combine all ad text
        headlines = [str(row[c]) for c in headline_cols if pd.notna(row.get(c))]
        descriptions = [str(row[c]) for c in desc_cols if pd.notna(row.get(c))]
        full_text = " | ".join(headlines + descriptions)

        if not full_text.strip() or full_text == "":
            continue

        # Extract hotel name from ad copy
        hotel_name = _extract_hotel_name(full_text)
        if hotel_name:
            hotels_found.add(hotel_name)

        # Parse metrics
        ctr = float(str(row.get(ctr_col, 0)).replace("%", "")) if ctr_col else 0.0
        cvr = float(str(row.get(cvr_col, 0)).replace("%", "")) if cvr_col else 0.0

        ad_record = {
            "full_text": full_text,
            "hotel_name": hotel_name or "unknown",
            "headlines": " | ".join(headlines),
            "descriptions": " | ".join(descriptions),
            "ctr": ctr,
            "cvr": cvr,
        }

        # Store raw ad in Firestore for audit/reference
        db.collection("historical_ads").add(ad_record)

        # Group by hotel name for insight generation
        key = hotel_name or "unknown"
        if key not in hotel_ads:
            hotel_ads[key] = []
        hotel_ads[key].append(ad_record)

        rows_processed += 1

    # Generate insights per hotel using Gemini
    insights_generated = []
    for hotel, ads in hotel_ads.items():
        if len(ads) < 2:
            continue  # Need at least 2 ads for meaningful analysis

        insight = _generate_insights(hotel, ads)

        # Upsert: delete existing insights for this hotel, then add new
        existing = list(
            db.collection("ad_insights")
            .where("hotel_name", "==", hotel)
            .stream()
        )
        for edoc in existing:
            edoc.reference.delete()

        db.collection("ad_insights").add(insight)
        insights_generated.append(hotel)

    # Generate global insights across all hotels if we have enough data
    all_ads = [ad for ads_list in hotel_ads.values() for ad in ads_list]
    if len(all_ads) >= 5:
        global_insight = _generate_insights("_global", all_ads)
        global_insight["hotel_name"] = "_global"

        # Upsert global insights
        existing_global = list(
            db.collection("ad_insights")
            .where("hotel_name", "==", "_global")
            .stream()
        )
        for edoc in existing_global:
            edoc.reference.delete()

        db.collection("ad_insights").add(global_insight)

    return CSVUploadResponse(
        rows_processed=rows_processed,
        hotels_found=list(hotels_found),
        status=f"success — insights generated for {len(insights_generated)} hotel(s)",
    )


def ingest_brand_usp_csv(df: pd.DataFrame) -> CSVUploadResponse:
    """Ingest Brand & USP CSV.

    Expected columns: Hotel Name, USPs, Positive Keywords, Negative Keywords, Restricted Keywords
    """
    db = get_firestore()
    hotels_found = []
    rows_processed = 0

    # Normalize column names
    col_map = {}
    for c in df.columns:
        cl = c.lower().strip()
        if "hotel" in cl and "name" in cl:
            col_map["hotel_name"] = c
        elif "usp" in cl:
            col_map["usps"] = c
        elif "positive" in cl:
            col_map["positive_keywords"] = c
        elif "negative" in cl and "restrict" not in cl:
            col_map["negative_keywords"] = c
        elif "restrict" in cl:
            col_map["restricted_keywords"] = c

    for _, row in df.iterrows():
        hotel_name = str(row.get(col_map.get("hotel_name", ""), "")).strip()
        if not hotel_name:
            continue

        def parse_list(val):
            if pd.isna(val):
                return []
            return [x.strip() for x in str(val).split(",") if x.strip()]

        doc = {
            "hotel_name": hotel_name,
            "usps": parse_list(row.get(col_map.get("usps", ""))),
            "positive_keywords": parse_list(row.get(col_map.get("positive_keywords", ""))),
            "negative_keywords": parse_list(row.get(col_map.get("negative_keywords", ""))),
            "restricted_keywords": parse_list(row.get(col_map.get("restricted_keywords", ""))),
        }

        # Upsert: delete existing then add
        existing = list(
            db.collection("brand_usps")
            .where("hotel_name", "==", hotel_name)
            .stream()
        )
        for edoc in existing:
            edoc.reference.delete()

        db.collection("brand_usps").add(doc)
        hotels_found.append(hotel_name)
        rows_processed += 1

    return CSVUploadResponse(
        rows_processed=rows_processed,
        hotels_found=hotels_found,
        status="success",
    )
