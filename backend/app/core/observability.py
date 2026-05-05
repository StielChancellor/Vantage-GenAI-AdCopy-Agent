"""Observability setup — Cloud Trace (OpenTelemetry) + structured Cloud Logging.

Call setup_observability() once at app startup in main.py.
Use get_tracer() to create spans in service code.
"""
import os
import logging
import contextlib
from typing import Generator

logger = logging.getLogger(__name__)

_tracer = None
_logging_configured = False


def setup_observability() -> None:
    """Initialize Cloud Logging and Cloud Trace. Safe to call multiple times."""
    global _logging_configured
    _setup_cloud_logging()
    _setup_tracing()
    _logging_configured = True


def _setup_cloud_logging() -> None:
    """Replace root logger handler with Cloud Logging structured JSON handler."""
    try:
        import google.cloud.logging
        client = google.cloud.logging.Client(
            project=os.environ.get("GCP_PROJECT_ID", "supple-moon-495404-b0")
        )
        client.setup_logging(log_level=logging.INFO)
    except Exception as exc:
        # Local dev: fall back to standard logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        logger.debug("Cloud Logging unavailable, using stderr: %s", exc)


def _setup_tracing() -> None:
    global _tracer
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

        provider = TracerProvider()
        exporter = CloudTraceSpanExporter(
            project_id=os.environ.get("GCP_PROJECT_ID", "supple-moon-495404-b0")
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("vantage-adcopy-agent")
        logger.info("Cloud Trace initialized.")
    except Exception as exc:
        logger.debug("Cloud Trace unavailable: %s", exc)
        _tracer = _NoopTracer()


def get_tracer():
    """Return the initialized tracer (or a no-op tracer for local dev)."""
    global _tracer
    if _tracer is None:
        _tracer = _NoopTracer()
    return _tracer


@contextlib.contextmanager
def trace_ai_call(
    operation: str,
    model: str,
    brand_id: str = "",
    request_type: str = "",
) -> Generator:
    """Context manager that wraps an AI call in a Cloud Trace span.

    Usage:
        with trace_ai_call("generate_ad", model_name, brand_id=hotel_name):
            response = model.generate_content(prompt)
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(operation) as span:
        try:
            span.set_attribute("ai.model", model)
            span.set_attribute("brand_id", brand_id)
            span.set_attribute("request_type", request_type)
        except Exception:
            pass
        yield span


class _NoopTracer:
    """Minimal tracer that does nothing — used when Cloud Trace is unavailable."""

    @contextlib.contextmanager
    def start_as_current_span(self, name: str, **kwargs):
        yield _NoopSpan()


class _NoopSpan:
    def set_attribute(self, *a, **kw):
        pass

    def record_exception(self, *a, **kw):
        pass
