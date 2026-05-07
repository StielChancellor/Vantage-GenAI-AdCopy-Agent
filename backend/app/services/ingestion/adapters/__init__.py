"""Source-specific CSV adapters that emit NormalizedAdRecord lists."""
from backend.app.services.ingestion.adapters.google_ads_adapter import (
    detect_google_ads,
    parse_google_ads,
)
from backend.app.services.ingestion.adapters.moengage_adapter import (
    detect_moengage,
    parse_moengage,
)
from backend.app.services.ingestion.adapters.brand_usp_adapter import (
    detect_brand_usp,
    parse_brand_usp,
)

__all__ = [
    "detect_google_ads", "parse_google_ads",
    "detect_moengage", "parse_moengage",
    "detect_brand_usp", "parse_brand_usp",
]
