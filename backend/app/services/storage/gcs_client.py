"""GCS helper for the creative-assets bucket (v2.7).

Bucket: `vantage-creative-assets-{env}` (multi-region `us`).
Per-brand prefix: `gs://bucket/brands/{brand_id}/packs/{pack_id}/{filename}`.

Reads served via signed URLs (1-hour TTL). Falls back to the public `gs://`
path if signing fails (e.g. when running under default ADC without an
explicit service-account email — never blocks ingestion).
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import timedelta

logger = logging.getLogger("vantage.storage")

_client_lock = threading.Lock()
_client = None
_bucket_cache: dict[str, object] = {}


def _bucket_name() -> str:
    env = os.environ.get("VANTAGE_ENV", "prod")
    return os.environ.get(
        "CREATIVE_ASSETS_BUCKET",
        f"vantage-creative-assets-{env}",
    )


def _get_client():
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            from google.cloud import storage
            project = os.environ.get("GCP_PROJECT_ID", "supple-moon-495404-b0")
            _client = storage.Client(project=project)
    return _client


def _get_bucket(name: str | None = None):
    name = name or _bucket_name()
    if name in _bucket_cache:
        return _bucket_cache[name]
    client = _get_client()
    bucket = client.bucket(name)
    _bucket_cache[name] = bucket
    return bucket


def object_path(brand_id: str, pack_id: str, filename: str) -> str:
    """Canonical GCS object key for a pack image."""
    safe_brand = (brand_id or "_unknown").strip().lower().replace("/", "_")
    safe_pack = (pack_id or "_unknown").strip().replace("/", "_")
    safe_file = (filename or "image").strip().replace("/", "_")
    return f"brands/{safe_brand}/packs/{safe_pack}/{safe_file}"


def upload_bytes(
    brand_id: str,
    pack_id: str,
    filename: str,
    data: bytes,
    content_type: str = "image/jpeg",
) -> str:
    """Upload raw image bytes. Returns the GCS object path (without scheme)."""
    bucket = _get_bucket()
    path = object_path(brand_id, pack_id, filename)
    blob = bucket.blob(path)
    blob.upload_from_string(data, content_type=content_type)
    return path


def signed_read_url(gcs_path: str, ttl_seconds: int = 3600) -> str:
    """Generate a v4 signed read URL. On failure returns gs:// fallback."""
    if not gcs_path:
        return ""
    try:
        bucket = _get_bucket()
        blob = bucket.blob(gcs_path)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=ttl_seconds),
            method="GET",
        )
    except Exception as exc:
        logger.debug("signed_url failed for %s: %s", gcs_path, exc)
        return f"gs://{_bucket_name()}/{gcs_path}"


def read_bytes(gcs_path: str) -> bytes:
    """Download bytes for a stored object — used by the captioning step."""
    bucket = _get_bucket()
    blob = bucket.blob(gcs_path)
    return blob.download_as_bytes()


def guess_content_type(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"
