"""Human-visible 5-character campaign IDs (v2.9).

Generated at the first of these moments:
- a new ideation is started, OR
- a new Unified Campaign draft is created.

The same id flows from `campaign_ideations` → `unified_campaigns` when an
ideation is promoted, so a marketer can quote a single 5-char handle (e.g.
"#K7H3W") across the whole journey.

Alphabet: 31 uppercase chars with confusables (0/O/1/I/L) removed →
~28 million combinations. Plenty for years, and easy to type/share verbally.
"""
from __future__ import annotations

import logging
import secrets

logger = logging.getLogger("vantage.campaign_id")

# 31 chars — no 0, O, 1, I, L.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_LENGTH = 5
_DEFAULT_ATTEMPTS = 8


def _random_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))


def _id_in_use(db, cid: str) -> bool:
    """True if `cid` already lives on a campaign_ideations OR unified_campaigns doc."""
    try:
        for coll in ("campaign_ideations", "unified_campaigns"):
            hit = list(db.collection(coll).where("campaign_id", "==", cid).limit(1).stream())
            if hit:
                return True
    except Exception as exc:
        # On Firestore error we conservatively assume not-in-use so a single
        # transient failure can't make new ideations fail. The race window is
        # tiny and the next backfill / lazy regen will heal collisions.
        logger.debug("campaign_id collision check failed: %s", exc)
        return False
    return False


def generate_campaign_id(max_attempts: int = _DEFAULT_ATTEMPTS) -> str:
    """Return an unused 5-char id. Falls back to a raw random id after
    `max_attempts` collisions — the alphabet is so wide that this only happens
    if Firestore is unreachable, in which case the conservative fallback
    keeps the user moving."""
    try:
        from backend.app.core.database import get_firestore
        db = get_firestore()
    except Exception:
        return _random_id()
    for _ in range(max_attempts):
        cid = _random_id()
        if not _id_in_use(db, cid):
            return cid
    logger.warning("campaign_id: %d collisions in a row — returning unchecked id", max_attempts)
    return _random_id()


def ensure_campaign_id(doc_ref, data: dict) -> str:
    """Lazy backfill helper: if the doc has a `campaign_id`, return it.
    Otherwise generate one, persist it onto the same doc, return it."""
    existing = (data or {}).get("campaign_id")
    if existing:
        return existing
    cid = generate_campaign_id()
    try:
        doc_ref.set({"campaign_id": cid}, merge=True)
    except Exception as exc:
        logger.debug("campaign_id backfill write failed: %s", exc)
    return cid
