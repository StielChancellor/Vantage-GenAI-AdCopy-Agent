"""CSV ingestion for historical ad data and brand USP data."""
import re
from typing import Optional

import pandas as pd

from backend.app.core.database import get_firestore, get_chroma
from backend.app.models.schemas import CSVUploadResponse


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


def ingest_historical_csv(df: pd.DataFrame) -> CSVUploadResponse:
    """Ingest historical ad performance CSV with dynamic column mapping.

    Expected columns: various headline/description columns, CTR, CVR as final columns.
    """
    db = get_firestore()
    chroma = get_chroma()
    collection = chroma.get_or_create_collection("historical_ads")

    # Dynamic column mapping: find headline, description, CTR, CVR columns
    cols = df.columns.tolist()
    headline_cols = [c for c in cols if "headline" in c.lower()]
    desc_cols = [c for c in cols if "description" in c.lower() or "desc" in c.lower()]
    ctr_col = next((c for c in cols if "ctr" in c.lower()), None)
    cvr_col = next((c for c in cols if "cvr" in c.lower() or "conversion" in c.lower()), None)

    hotels_found = set()
    rows_processed = 0

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

        metadata = {
            "hotel_name": hotel_name or "unknown",
            "headlines": " | ".join(headlines),
            "descriptions": " | ".join(descriptions),
            "ctr": ctr,
            "cvr": cvr,
            "row_index": idx,
        }

        # Store in ChromaDB for vector search
        collection.add(
            documents=[full_text],
            metadatas=[metadata],
            ids=[f"ad_{idx}"],
        )

        # Store in Firestore for structured queries
        db.collection("historical_ads").add(
            {
                "full_text": full_text,
                "hotel_name": hotel_name or "unknown",
                "headlines": headlines,
                "descriptions": descriptions,
                "ctr": ctr,
                "cvr": cvr,
            }
        )

        rows_processed += 1

    return CSVUploadResponse(
        rows_processed=rows_processed,
        hotels_found=list(hotels_found),
        status="success",
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
