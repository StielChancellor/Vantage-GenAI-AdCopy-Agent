"""Google Ads Editor CSV adapter.

Input: a wide-format Google Ads Editor export (39 columns) containing per-ad
rows with up to 15 short headlines, 5 long headlines, 5 descriptions, 5
carousel cards, an `Ad type`, `Ad strength`, `Impr.`, `CTR`, and `Business name`.

Output: a list of NormalizedAdRecord — ONE per non-empty (headline, description)
pair within each input row. The `Impr.` and `CTR` are inherited by every
exploded record (they describe the ad as a whole, not the individual asset),
which is the correct behaviour for training a per-asset retrieval model.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

import pandas as pd

from backend.app.services.ingestion.normalized_record import (
    NormalizedAdRecord,
    season_for_month,
)

logger = logging.getLogger("vantage.ingestion.google_ads")

# Column-name signatures used to auto-detect this format
_SIGNATURE_COLUMNS = {"Ad type", "Impr.", "CTR"}

# Maps the human-readable "Ad type" cell to our canonical campaign_type enum.
# Add new variants here as Google rolls them out.
_AD_TYPE_MAP: dict[str, str] = {
    "performance max": "pmax",
    "performance max ad": "pmax",
    "demand gen image ad": "demandgen_image",
    "demand gen carousel ad": "demandgen_carousel",
    "demand gen video ad": "demandgen_video",
    "responsive search ad": "search_responsive",
    "expanded text ad": "search_responsive",
    "mobile app installs ad v2": "app_installs",
    "mobile app installs ad": "app_installs",
}

_HEADLINE_COLS_SHORT = [f"Headline {i}" for i in range(1, 16)]   # 15 short slots
_HEADLINE_COLS_LONG = ["Long headline"] + [f"Long headline {i}" for i in range(1, 6)]
_DESC_COLS = ["Description"] + [f"Description {i}" for i in range(1, 6)]
_CARD_COLS = [f"Card {i} headline" for i in range(1, 6)]


def detect_google_ads(df: pd.DataFrame) -> bool:
    """True if the DataFrame columns match the Google Ads Editor signature."""
    return _SIGNATURE_COLUMNS.issubset(set(df.columns))


def parse_google_ads(df: pd.DataFrame, upload_date: date | None = None) -> list[NormalizedAdRecord]:
    """Convert a Google Ads Editor export into NormalizedAdRecord list.

    Each input row produces one record per non-empty headline×description pair
    (with carousel-card headlines preserved as a list on every record from that row).
    """
    upload_date = upload_date or date.today()
    records: list[NormalizedAdRecord] = []

    for idx, row in df.iterrows():
        ad_type_raw = _clean(row.get("Ad type"))
        campaign_type = _AD_TYPE_MAP.get(ad_type_raw.lower().strip(), "")
        if not campaign_type:
            logger.debug("Row %d: unknown Ad type '%s' — skipping", idx, ad_type_raw)
            continue

        impressions = _parse_int(row.get("Impr."))
        ctr = _parse_pct(row.get("CTR"))
        ad_strength = _clean(row.get("Ad strength")) or None
        business_name = _clean(row.get("Business name"))

        # Gather every non-empty headline/description for this row
        short_headlines = _gather(row, _HEADLINE_COLS_SHORT)
        long_headlines = _gather(row, _HEADLINE_COLS_LONG)
        descriptions = _gather(row, _DESC_COLS)
        card_headlines = _gather(row, _CARD_COLS)

        # Pair each headline with each description (cartesian — small per row)
        # Cap at 30 records per source row to bound explosion
        all_headlines = short_headlines + long_headlines
        if not all_headlines:
            logger.debug("Row %d: no headlines after cleaning — skipping", idx)
            continue
        if not descriptions:
            descriptions = [""]  # so we still emit headline-only records

        flight_hint = _infer_flight_date(all_headlines + descriptions, upload_date)
        month = flight_hint.month
        season = season_for_month(month)

        emitted = 0
        for h in all_headlines:
            for d in descriptions:
                if emitted >= 30:
                    break
                rec = NormalizedAdRecord(
                    headline=h,
                    description=d,
                    campaign_type=campaign_type,
                    impressions=impressions,
                    ctr=ctr,
                    ad_strength=ad_strength,
                    flight_date=flight_hint,
                    month=month,
                    season=season,
                    business_name=business_name,
                    card_headlines=card_headlines,
                    long_headlines=long_headlines,
                    raw_ad_type=ad_type_raw,
                )
                records.append(rec)
                emitted += 1

    logger.info(
        "google_ads_adapter: %d input rows → %d normalized records",
        len(df), len(records),
    )
    return records


# ---------------------------------------------------------------------------
# Helpers


def _clean(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s in {"--", "nan", "NaN", "None", ""}:
        return ""
    return s


def _gather(row, cols: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for c in cols:
        if c not in row.index:
            continue
        v = _clean(row.get(c))
        if v and v.lower() not in seen:
            out.append(v)
            seen.add(v.lower())
    return out


def _parse_int(val) -> int:
    if val is None or pd.isna(val):
        return 0
    s = str(val).replace(",", "").replace(" ", "").strip()
    if not s or s == "--":
        return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _parse_pct(val) -> float:
    """Parse '6.79%' or '0.0679' into 6.79 (always returns the percentage form)."""
    if val is None or pd.isna(val):
        return 0.0
    s = str(val).strip().rstrip("%").replace(",", "")
    if not s or s == "--":
        return 0.0
    try:
        f = float(s)
    except (ValueError, TypeError):
        return 0.0
    # If user supplied 0.0679 instead of 6.79, normalize to percentage
    if f < 1 and "%" not in str(val):
        f *= 100
    return round(f, 4)


_DATE_PATTERNS = [
    # "Book by 25th March '26", "Book by 24th April"
    re.compile(r"book by\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s*['’]?(\d{2,4}))?", re.IGNORECASE),
    # "Valid for stays from 4th May to 31st Oct"
    re.compile(r"from\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)", re.IGNORECASE),
    # "Offer Valid Till Jan 31st"
    re.compile(r"till\s+([A-Za-z]+)\s+(\d{1,2})", re.IGNORECASE),
]
_MONTHS = {
    m: i for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"], start=1
    )
}


def _infer_flight_date(texts: list[str], fallback: date) -> date:
    """Best-effort: parse 'Book by 25th March', 'Valid till Jan 31st' etc.
    Falls back to upload_date if no date hint found."""
    blob = " ".join(texts)
    for pat in _DATE_PATTERNS:
        m = pat.search(blob)
        if not m:
            continue
        groups = m.groups()
        if len(groups) >= 2 and groups[0] and groups[0].isdigit():
            # day, month[, year]
            day = int(groups[0])
            mon_str = (groups[1] or "")[:3].lower()
            mon = _MONTHS.get(mon_str)
            year = fallback.year
            if len(groups) > 2 and groups[2]:
                yr = int(groups[2])
                year = 2000 + yr if yr < 100 else yr
        elif len(groups) >= 2 and groups[0]:
            # month, day
            mon_str = groups[0][:3].lower()
            mon = _MONTHS.get(mon_str)
            day = int(groups[1])
            year = fallback.year
        else:
            continue
        if mon:
            try:
                return date(year, mon, max(1, min(28, day)))
            except ValueError:
                continue
    return fallback
