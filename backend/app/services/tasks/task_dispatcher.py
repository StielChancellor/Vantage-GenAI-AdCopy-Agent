"""Cloud Tasks HTTP queue wrapper for async background jobs.

All Vantage background operations (CSV embedding, BQ export, market digest)
go through this dispatcher. Task handler endpoints live at /internal/tasks/{type}.
"""
import os
import json
import logging
from typing import Any

logger = logging.getLogger("vantage.tasks")

_PROJECT = os.environ.get("GCP_PROJECT_ID", "supple-moon-495404-b0")
_LOCATION = os.environ.get("CLOUD_TASKS_LOCATION", "us-central1")
_QUEUE = os.environ.get("CLOUD_TASKS_QUEUE", "vantage-ingestion")

_tasks_client = None


def _get_client():
    global _tasks_client
    if _tasks_client is None:
        from google.cloud import tasks_v2
        _tasks_client = tasks_v2.CloudTasksClient()
    return _tasks_client


def enqueue(
    task_type: str,
    payload: dict[str, Any],
    service_url: str | None = None,
    delay_seconds: int = 0,
) -> str | None:
    """Enqueue an HTTP task. Returns the task name or None on failure.

    Args:
        task_type: Used as the URL suffix: POST /internal/tasks/{task_type}
        payload: JSON-serializable dict sent as request body.
        service_url: Override the Cloud Run URL. Auto-detected from env if not set.
        delay_seconds: Seconds to delay execution (0 = immediate).
    """
    url = _build_url(task_type, service_url)
    body = json.dumps(payload).encode()
    parent = f"projects/{_PROJECT}/locations/{_LOCATION}/queues/{_QUEUE}"

    task: dict = {
        "http_request": {
            "http_method": "POST",
            "url": url,
            "headers": {"Content-Type": "application/json"},
            "body": body,
            "oidc_token": {
                "service_account_email": f"vantage-tasks-sa@{_PROJECT}.iam.gserviceaccount.com",
            },
        }
    }

    if delay_seconds > 0:
        from google.protobuf import timestamp_pb2
        import time
        ts = timestamp_pb2.Timestamp()
        ts.FromSeconds(int(time.time()) + delay_seconds)
        task["schedule_time"] = ts

    try:
        client = _get_client()
        response = client.create_task(parent=parent, task=task)
        logger.info("Task enqueued: %s → %s", task_type, response.name)
        return response.name
    except Exception as exc:
        logger.error("Failed to enqueue task '%s': %s", task_type, exc)
        return None


def _build_url(task_type: str, override: str | None) -> str:
    if override:
        return f"{override.rstrip('/')}/internal/tasks/{task_type}"
    # Auto-detect: K_SERVICE env is set by Cloud Run
    service_name = os.environ.get("K_SERVICE", "vantage-adcopy-agent")
    project = _PROJECT
    region = _LOCATION
    return (
        f"https://{service_name}-{_short_hash(project)}-uc.a.run.app"
        f"/internal/tasks/{task_type}"
    )


def _short_hash(s: str) -> str:
    import hashlib
    return hashlib.md5(s.encode()).hexdigest()[:8]
