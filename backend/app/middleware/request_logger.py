"""FastAPI middleware — structured request/response logging with trace correlation."""
import time
import uuid
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("vantage.requests")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with latency, status, user_id, and trace ID."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
        start = time.time()

        # Extract user_id from JWT if present (best effort — no auth error here)
        user_id = _extract_user_id(request)

        response = await call_next(request)

        latency_ms = round((time.time() - start) * 1000)
        logger.info(
            "request",
            extra={
                "json_fields": {
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": latency_ms,
                    "user_id": user_id,
                }
            },
        )

        response.headers["X-Trace-ID"] = trace_id
        return response


def _extract_user_id(request: Request) -> str:
    try:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            import jwt
            from backend.app.core.config import get_settings
            settings = get_settings()
            payload = jwt.decode(
                auth[7:],
                settings.get_jwt_secret(),
                algorithms=[settings.JWT_ALGORITHM],
            )
            return payload.get("sub", "")
    except Exception:
        pass
    return ""
