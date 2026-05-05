"""Secret Manager wrapper with process-level TTL cache.

Replaces raw env var reads for sensitive credentials.
On Cloud Run, the service account (vantage-cloudrun-sa) has
roles/secretmanager.secretAccessor. Locally, use Application Default Credentials
or set the env vars directly (they still work as fallbacks).
"""
import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


def get_secret(secret_id: str, version: str = "latest") -> str:
    """Fetch a secret value from Secret Manager with TTL cache.

    Falls back to environment variable with the same name (uppercased,
    hyphens replaced with underscores) for local development.
    """
    now = time.time()
    cache_key = f"{secret_id}/{version}"
    if cache_key in _cache:
        value, expiry = _cache[cache_key]
        if now < expiry:
            return value

    # Try Secret Manager first (production)
    value = _fetch_from_secret_manager(secret_id, version)

    # Fall back to environment variable for local dev
    if value is None:
        env_name = secret_id.replace("-", "_").upper()
        # Strip leading "vantage-" prefix when checking env vars
        short_name = env_name.replace("VANTAGE_", "")
        value = os.environ.get(env_name) or os.environ.get(short_name) or ""
        if value:
            logger.debug("Secret '%s' loaded from environment variable.", secret_id)

    _cache[cache_key] = (value, now + _CACHE_TTL_SECONDS)
    return value


def _fetch_from_secret_manager(secret_id: str, version: str) -> Optional[str]:
    project_id = os.environ.get("GCP_PROJECT_ID", "supple-moon-495404-b0")
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("utf-8")
    except Exception as exc:
        logger.debug("Secret Manager unavailable for '%s': %s", secret_id, exc)
        return None


def invalidate(secret_id: str) -> None:
    keys_to_delete = [k for k in _cache if k.startswith(secret_id + "/")]
    for k in keys_to_delete:
        del _cache[k]
