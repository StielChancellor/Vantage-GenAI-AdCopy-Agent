"""MoEngage push-notification CSV adapter.

Input columns:
    Campaign Sent Time
    Android Message Title (Android, Web), Title (iOS)
    Ios Message Title (Android, Web), Title (iOS)
    Android Message (Android, Web), Subtitle (iOS)
    Ios Message (Android, Web), Subtitle (iOS)
    Android Impressions, Ios Impressions, All Platform Impressions
    Android CTR, Ios CTR, All Platform CTR

Output: TWO records per source row (one Android, one iOS) — but only when that
platform's impressions > 0. Rows where both platforms have zero impressions are
skipped entirely (campaign never delivered, would poison the training set).
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from backend.app.services.ingestion.normalized_record import (
    NormalizedAdRecord,
    season_for_month,
)

logger = logging.getLogger("vantage.ingestion.moengage")

_SIGNATURE_COLUMNS = {"Campaign Sent Time", "All Platform Impressions"}

# Real column names in the export — they contain commas and parens
COL_SENT = "Campaign Sent Time"
COL_TITLE_ANDROID = "Android Message Title (Android, Web), Title (iOS)"
COL_TITLE_IOS = "Ios Message Title (Android, Web), Title (iOS)"
COL_MSG_ANDROID = "Android Message (Android, Web), Subtitle (iOS)"
COL_MSG_IOS = "Ios Message (Android, Web), Subtitle (iOS)"
COL_IMPR_ANDROID = "Android Impressions"
COL_IMPR_IOS = "Ios Impressions"
COL_CTR_ANDROID = "Android CTR"
COL_CTR_IOS = "Ios CTR"


def detect_moengage(df: pd.DataFrame) -> bool:
    return _SIGNATURE_COLUMNS.issubset(set(df.columns))


def parse_moengage(df: pd.DataFrame) -> list[NormalizedAdRecord]:
    """Convert a MoEngage push export into per-platform NormalizedAdRecord list."""
    records: list[NormalizedAdRecord] = []
    skipped_zero = 0

    for idx, row in df.iterrows():
        sent_at = _parse_dt(row.get(COL_SENT))
        if sent_at is None:
            logger.debug("Row %d: invalid Campaign Sent Time — skipping", idx)
            continue

        month = sent_at.month
        season = season_for_month(month)
        hour = sent_at.hour
        # Python: Monday=0 .. Sunday=6
        dow = sent_at.weekday()

        # ANDROID record
        android_impr = _parse_int(row.get(COL_IMPR_ANDROID))
        android_ctr = _parse_pct(row.get(COL_CTR_ANDROID))
        android_title = _clean(row.get(COL_TITLE_ANDROID))
        android_msg = _clean(row.get(COL_MSG_ANDROID))
        if android_impr > 0 and android_title:
            records.append(NormalizedAdRecord(
                headline=android_title,
                description=android_msg,
                campaign_type="push_android",
                impressions=android_impr,
                ctr=android_ctr,
                sent_at=sent_at,
                flight_date=sent_at.date(),
                hour_of_day=hour,
                day_of_week=dow,
                month=month,
                season=season,
            ))
        else:
            skipped_zero += 1

        # iOS record
        ios_impr = _parse_int(row.get(COL_IMPR_IOS))
        ios_ctr = _parse_pct(row.get(COL_CTR_IOS))
        ios_title = _clean(row.get(COL_TITLE_IOS))
        ios_msg = _clean(row.get(COL_MSG_IOS))
        if ios_impr > 0 and ios_title:
            records.append(NormalizedAdRecord(
                headline=ios_title,
                description=ios_msg,
                campaign_type="push_ios",
                impressions=ios_impr,
                ctr=ios_ctr,
                sent_at=sent_at,
                flight_date=sent_at.date(),
                hour_of_day=hour,
                day_of_week=dow,
                month=month,
                season=season,
            ))
        else:
            skipped_zero += 1

    logger.info(
        "moengage_adapter: %d input rows → %d records (skipped %d zero-impression entries)",
        len(df), len(records), skipped_zero,
    )
    return records


# ---------------------------------------------------------------------------


def _clean(val) -> str:
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


def _parse_int(val) -> int:
    if val is None or pd.isna(val):
        return 0
    try:
        return int(float(str(val).replace(",", "").strip()))
    except (ValueError, TypeError):
        return 0


def _parse_pct(val) -> float:
    """MoEngage CTR comes as plain numbers (already in %). e.g. 2.02 means 2.02%."""
    if val is None or pd.isna(val):
        return 0.0
    try:
        f = float(str(val).rstrip("%").strip())
    except (ValueError, TypeError):
        return 0.0
    return round(f, 4)


def _parse_dt(val) -> datetime | None:
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None
