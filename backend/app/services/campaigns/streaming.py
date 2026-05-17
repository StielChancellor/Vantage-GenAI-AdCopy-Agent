"""Streaming Unified Campaign fan-out (v3.0).

Replaces the request/response synchronous /generate path for large campaigns.

Flow:
1. POST /generate-async writes all (entity, level, channel) tasks to a
   `unified_campaigns/{id}/generations` subcollection in status='pending',
   stamps a fresh `job` object on the parent doc, kicks off
   `_stream_worker()` via asyncio.create_task, and returns the job_id +
   total_tasks immediately.
2. The worker processes tasks under a semaphore (default 15), dispatching
   each via asyncio.to_thread so the synchronous Vertex SDK doesn't block
   the event loop. Per-row state transitions are written to Firestore as
   they happen.
3. The worker reads `job.cancelled` and `job.brief_revision` BETWEEN
   tasks so /steer and /cancel take effect without partial-state writes.
4. A heartbeat writes `job.last_heartbeat` every ~5 s so the frontend
   can detect a stalled worker and offer /resume.

The leaf generators (`_gen_search_or_meta`, `_gen_app_push`) are imported
from `orchestrator.py` unchanged — they take a StructuredCampaign +
entity + channel/level + reference_urls and return variants. The
streaming worker simply re-reads the latest `structured` (under the
current brief_revision) before each task.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.app.core.database import get_firestore
from backend.app.core.version import APP_VERSION
from backend.app.models.schemas import (
    StructuredCampaign, UnifiedCampaignSelection,
)
from backend.app.services.campaigns.orchestrator import (
    _expand_entities, _hotels_under_brand, _resolve_label,
    _gen_search_or_meta, _gen_app_push,
)

logger = logging.getLogger("vantage.campaigns.streaming")

_COLL = "unified_campaigns"

# Process-local registry of in-flight workers so /resume is idempotent
# and we don't accidentally spin a second worker for the same campaign.
_workers_in_flight: dict[str, asyncio.Task] = {}
_workers_lock = asyncio.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────
# Task-list builder (mirrors orchestrator.run_campaign's task expansion)
# ──────────────────────────────────────────────────────────────────


def _build_tasks(selection: UnifiedCampaignSelection) -> list[dict]:
    """Expand the selection into a deterministic list of task records.
    Each record is a dict ready for Firestore persistence."""
    if not selection.channels:
        selection.channels = ["search_ads"]
    if not selection.campaign_levels:
        selection.campaign_levels = ["single"]

    # Effective levels (expand chain_plus_single).
    eff_levels: list[str] = []
    for lvl in selection.campaign_levels:
        if lvl == "chain_plus_single":
            eff_levels.extend(["chain", "single"])
        else:
            eff_levels.append(lvl)
    want_chain = "chain" in eff_levels
    want_single = "single" in eff_levels

    entities = _expand_entities(selection)

    # Build (entity, level) work items.
    work: list[tuple[dict, str]] = []
    seen: set[tuple] = set()

    def _push(entity: dict, level: str):
        key = (
            entity.get("scope"),
            entity.get("hotel_id") or "",
            entity.get("brand_id") or "",
            entity.get("label") or "",
            level,
        )
        if key in seen:
            return
        seen.add(key)
        work.append((entity, level))

    for entity in entities:
        scope = entity.get("scope")
        if scope == "hotel":
            if want_single:
                _push(entity, "single")
            if want_chain and entity.get("brand_id"):
                _push({
                    "label": entity["brand_id"], "scope": "brand",
                    "brand_id": entity["brand_id"], "is_loyalty": False,
                }, "chain")
        elif scope == "brand":
            if want_chain:
                _push(entity, "chain")
            if want_single:
                for hotel_entity in _hotels_under_brand(entity.get("brand_id", "")):
                    _push(hotel_entity, "single")
        elif scope == "loyalty":
            _push(entity, "chain")
        elif scope == "city":
            if want_chain:
                _push(entity, "chain")
            if want_single:
                try:
                    from backend.app.services.hotels import catalog
                    city = (entity.get("cities") or [None])[0] or ""
                    for h in (catalog.hotels_for_city(city) or []):
                        _push({
                            "label": h.get("hotel_name") or h.get("hotel_id"),
                            "scope": "hotel", "hotel_id": h.get("hotel_id"),
                            "brand_id": h.get("brand_id"), "is_loyalty": False,
                        }, "single")
                except Exception:
                    pass

    # Cartesian with channels → flat task list, idx assigned in order.
    tasks: list[dict] = []
    for entity, level in work:
        label = _resolve_label(entity)
        for channel in selection.channels:
            tasks.append({
                "idx": len(tasks),
                "label": label,
                "scope": entity.get("scope", "hotel"),
                "hotel_id": entity.get("hotel_id"),
                "brand_id": entity.get("brand_id"),
                "channel": channel,
                "level": level,
                "_entity": entity,            # internal, stripped before write
            })
    return tasks


# ──────────────────────────────────────────────────────────────────
# Public API — called from routers/campaigns.py
# ──────────────────────────────────────────────────────────────────


async def start_job(campaign_id: str, override_selection: UnifiedCampaignSelection | None = None) -> dict:
    """Kick off a streaming generation. Writes pending rows, stamps the
    job state, fires the worker, returns {job_id, total_tasks, brief_revision}.
    Returns in <1 s — the worker runs detached."""
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    snap = ref.get()
    if not snap.exists:
        raise ValueError("Campaign not found")
    data = snap.to_dict() or {}

    # Build the task list.
    selection = override_selection or UnifiedCampaignSelection(**(data.get("selection") or {}))
    tasks = _build_tasks(selection)
    if not tasks:
        raise ValueError("Selection produced 0 tasks — pick at least one hotel/brand/city and one channel.")

    # Wipe any existing generations subcollection then re-write fresh rows.
    # (User initiates a new run; previous attempts archive into the legacy
    # `generated` array if desired — for now we just overwrite.)
    gens = ref.collection("generations")
    try:
        existing = list(gens.stream())
        for d in existing:
            d.reference.delete()
    except Exception as exc:
        logger.debug("clearing prior generations failed (non-fatal): %s", exc)

    now = _now()
    batch = db.batch()
    for t in tasks:
        # Strip internal-only keys before persisting.
        row = {
            "idx": t["idx"],
            "label": t["label"] or "",
            "scope": t["scope"],
            "hotel_id": t.get("hotel_id"),
            "brand_id": t.get("brand_id"),
            "channel": t["channel"],
            "level": t["level"],
            "status": "pending",
            "brief_revision": 0,
            "variants": [],
            "tokens_used": 0,
            "model_used": "",
            "time_seconds": 0.0,
            "created_at": now,
            "updated_at": now,
        }
        batch.set(gens.document(str(t["idx"])), row)
    batch.commit()

    job_id = uuid.uuid4().hex[:16]
    sel_dict = selection.model_dump() if hasattr(selection, "model_dump") else selection.dict()
    ref.set({
        "status": "generating",
        "selection": sel_dict,
        "job": {
            "job_id": job_id,
            "brief_revision": 0,
            "total_tasks": len(tasks),
            "completed_tasks": 0,
            "failed_tasks": 0,
            "stale_tasks": 0,
            "cancelled": False,
            "started_at": now,
            "finished_at": None,
            "last_heartbeat": now,
        },
        "app_version": APP_VERSION,
        "updated_at": now,
    }, merge=True)

    # Detach the worker. Cloud Run's --no-cpu-throttling keeps the task alive
    # past the originating HTTP request.
    await _ensure_worker(campaign_id)

    return {
        "job_id": job_id,
        "total_tasks": len(tasks),
        "brief_revision": 0,
    }


async def _ensure_worker(campaign_id: str) -> bool:
    """Spawn the worker for a campaign if none is already running in this
    process. Returns True if a new worker was created, False if one was
    already in flight."""
    async with _workers_lock:
        existing = _workers_in_flight.get(campaign_id)
        if existing and not existing.done():
            return False
        task = asyncio.create_task(_stream_worker(campaign_id))
        _workers_in_flight[campaign_id] = task
        # Clean up the registry entry once the task finishes.
        task.add_done_callback(lambda t, cid=campaign_id: _workers_in_flight.pop(cid, None))
        return True


async def _stream_worker(campaign_id: str) -> None:
    """Detached background worker. Pulls pending rows, dispatches each
    under a semaphore via asyncio.to_thread so the sync Vertex SDK
    doesn't block the event loop."""
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    semaphore_cap = int(os.environ.get("UC_PARALLEL_FANOUT", "15"))
    sem = asyncio.Semaphore(semaphore_cap)

    # Heartbeat task — writes job.last_heartbeat every 5 s while the worker runs.
    heartbeat_stop = asyncio.Event()

    async def _heartbeat():
        while not heartbeat_stop.is_set():
            try:
                ref.set({"job": {"last_heartbeat": _now()}}, merge=True)
            except Exception as exc:
                logger.debug("heartbeat write failed (non-fatal): %s", exc)
            try:
                await asyncio.wait_for(heartbeat_stop.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                continue

    hb_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            # Re-read parent state every iteration so /steer + /cancel land.
            parent = ref.get().to_dict() or {}
            job = parent.get("job") or {}
            if job.get("cancelled"):
                logger.info("worker %s: cancelled", campaign_id)
                break
            brief_revision = int(job.get("brief_revision") or 0)
            structured_dict = parent.get("structured") or {"campaign_name": "Untitled"}
            structured = StructuredCampaign(**structured_dict)
            reference_urls = list(parent.get("reference_urls") or [])

            # Pull a chunk of pending rows.
            pending_docs = list(
                ref.collection("generations").where("status", "==", "pending").limit(semaphore_cap * 2).stream()
            )
            if not pending_docs:
                break

            async def _run_one(doc_snap):
                row_id = doc_snap.id
                row_ref = ref.collection("generations").document(row_id)
                row_data = doc_snap.to_dict() or {}
                entity = {
                    "label": row_data.get("label"),
                    "scope": row_data.get("scope"),
                    "hotel_id": row_data.get("hotel_id"),
                    "brand_id": row_data.get("brand_id"),
                    "is_loyalty": row_data.get("scope") == "loyalty",
                }
                channel = row_data.get("channel")
                level = row_data.get("level")

                async with sem:
                    # Re-check cancellation just before starting (cheap).
                    parent_check = ref.get().to_dict() or {}
                    job_check = parent_check.get("job") or {}
                    if job_check.get("cancelled"):
                        return

                    row_ref.set({
                        "status": "running",
                        "brief_revision": brief_revision,
                        "updated_at": _now(),
                    }, merge=True)

                    def _sync_work() -> dict:
                        async def _do():
                            if channel == "app_push":
                                v, t, m, s = await _gen_app_push(structured, entity, reference_urls)
                            else:
                                v, t, m, s = await _gen_search_or_meta(
                                    structured, entity, channel, level, reference_urls,
                                )
                            return {"variants": v, "tokens_used": int(t),
                                    "model_used": m or "", "time_seconds": float(s)}
                        return asyncio.new_event_loop().run_until_complete(_do())

                    try:
                        result = await asyncio.to_thread(_sync_work)
                        row_ref.set({
                            **result,
                            "status": "complete",
                            "brief_revision": brief_revision,
                            "updated_at": _now(),
                        }, merge=True)
                        _increment_counter(ref, "completed_tasks")
                    except Exception as exc:
                        logger.warning("subgen failed for %s/%s: %s", campaign_id, row_id, exc)
                        row_ref.set({
                            "status": "failed",
                            "error": str(exc)[:300],
                            "brief_revision": brief_revision,
                            "updated_at": _now(),
                        }, merge=True)
                        _increment_counter(ref, "failed_tasks")

            await asyncio.gather(*[_run_one(d) for d in pending_docs])

            # Loop again to drain any pending rows (e.g. from /regen-stale).
            # Stop when no more pending exist.
            still_pending = list(
                ref.collection("generations").where("status", "==", "pending").limit(1).stream()
            )
            if not still_pending:
                break

    finally:
        heartbeat_stop.set()
        try:
            await hb_task
        except Exception:
            pass

    # Final job-state write. Status flips back to 'locked' if at least some
    # rows completed, otherwise stays 'generating' so /resume can pick up.
    try:
        snap = ref.get()
        if snap.exists:
            data = snap.to_dict() or {}
            job = data.get("job") or {}
            done = int(job.get("completed_tasks") or 0) + int(job.get("failed_tasks") or 0)
            total = int(job.get("total_tasks") or 0)
            new_status = "locked" if done >= total else data.get("status", "generating")
            ref.set({
                "status": new_status,
                "job": {**job, "finished_at": _now() if done >= total else None},
                "updated_at": _now(),
            }, merge=True)
    except Exception as exc:
        logger.debug("final job-state write failed: %s", exc)


def _increment_counter(ref, field: str) -> None:
    """Best-effort transactional increment of a job counter."""
    try:
        from google.cloud import firestore as fs
        ref.update({f"job.{field}": fs.Increment(1)})
    except Exception as exc:
        logger.debug("counter increment failed for %s: %s", field, exc)


# ──────────────────────────────────────────────────────────────────
# Steer / cancel / regen-stale / resume
# ──────────────────────────────────────────────────────────────────


def steer_job(campaign_id: str, structured: StructuredCampaign, scope: str = "remaining") -> dict:
    """Apply a new brief mid-flight. Increments brief_revision; if scope='all'
    also flips every completed row to stale (user can /regen-stale to re-run)."""
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    snap = ref.get()
    if not snap.exists:
        raise ValueError("Campaign not found")
    data = snap.to_dict() or {}
    job = data.get("job") or {}
    new_rev = int(job.get("brief_revision") or 0) + 1

    structured_dict = structured.model_dump() if hasattr(structured, "model_dump") else structured.dict()

    stale_count = 0
    if scope == "all":
        # Mark every completed row as stale.
        gens = ref.collection("generations").where("status", "==", "complete").stream()
        batch = db.batch()
        for d in gens:
            batch.set(d.reference, {"status": "stale", "updated_at": _now()}, merge=True)
            stale_count += 1
        try:
            batch.commit()
        except Exception as exc:
            logger.warning("steer all: stale flip failed: %s", exc)

    ref.set({
        "structured": structured_dict,
        "job": {"brief_revision": new_rev,
                "stale_tasks": (job.get("stale_tasks") or 0) + stale_count},
        "updated_at": _now(),
    }, merge=True)

    return {"brief_revision": new_rev, "completed_marked_stale": stale_count}


def cancel_job(campaign_id: str) -> None:
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    ref.set({"job": {"cancelled": True}, "updated_at": _now()}, merge=True)


def regen_stale(campaign_id: str) -> dict:
    """Flip every row in `stale` back to `pending`. Worker (if idle)
    will pick them up the next time /resume or a fresh worker is launched."""
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    snap = ref.get()
    if not snap.exists:
        raise ValueError("Campaign not found")
    flipped = 0
    batch = db.batch()
    for d in ref.collection("generations").where("status", "==", "stale").stream():
        batch.set(d.reference, {"status": "pending", "updated_at": _now()}, merge=True)
        flipped += 1
    try:
        batch.commit()
    except Exception as exc:
        logger.warning("regen_stale: flip failed: %s", exc)
    # Reset stale counter (worker will re-count by querying), un-cancel,
    # and re-mark status=generating so /resume can spin.
    ref.set({
        "status": "generating",
        "job": {"cancelled": False, "stale_tasks": 0},
        "updated_at": _now(),
    }, merge=True)
    return {"flipped": flipped}


async def resume_job(campaign_id: str) -> bool:
    """Idempotent: spawn the worker if not already running.
    Returns True if a new worker started, False if one was already running."""
    db = get_firestore()
    ref = db.collection(_COLL).document(campaign_id)
    snap = ref.get()
    if not snap.exists:
        raise ValueError("Campaign not found")
    # Un-cancel + reset heartbeat so a fresh worker can pick up.
    ref.set({
        "status": "generating",
        "job": {"cancelled": False, "last_heartbeat": _now()},
        "updated_at": _now(),
    }, merge=True)
    # Also flip any `running` rows back to `pending` — the worker that was
    # marking them running is no longer here.
    try:
        for d in ref.collection("generations").where("status", "==", "running").stream():
            d.reference.set({"status": "pending", "updated_at": _now()}, merge=True)
    except Exception as exc:
        logger.debug("running->pending flip on resume failed: %s", exc)
    return await _ensure_worker(campaign_id)
