"""Source-specific CSV adapters that emit NormalizedAdRecord lists."""
from backend.app.services.ingestion.adapters.google_ads_adapter import (
    detect_google_ads,
    parse_google_ads,
)
from backend.app.services.ingestion.adapters.moengage_adapter import (
    detect_moengage,
    parse_moengage,
)

__all__ = ["detect_google_ads", "parse_google_ads", "detect_moengage", "parse_moengage"]
