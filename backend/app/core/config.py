from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings

# Look for .env in backend/ directory or project root
_ENV_FILE = None
for candidate in [
    Path(__file__).resolve().parent.parent.parent / ".env",
    Path.cwd() / ".env",
    Path.cwd() / "backend" / ".env",
]:
    if candidate.exists():
        _ENV_FILE = str(candidate)
        break


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Vantage AdCopy Agent"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Auth (sensitive — loaded from Secret Manager in production)
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Firebase / Firestore
    FIREBASE_PROJECT_ID: str = "supple-moon-495404-b0"
    FIREBASE_SERVICE_ACCOUNT_PATH: str = ""

    # GCP project — non-sensitive
    GCP_PROJECT_ID: str = "supple-moon-495404-b0"
    GCP_PROJECT_NUMBER: str = "717874273203"
    GCP_REGION: str = "us-central1"

    # Vertex AI — non-sensitive
    VERTEX_AI_LOCATION: str = "us-central1"
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # BigQuery
    BQ_DATASET: str = "vantage"

    # Cloud Tasks
    CLOUD_TASKS_QUEUE: str = "vantage-ingestion"
    CLOUD_TASKS_LOCATION: str = "us-central1"

    # Cloud Storage
    GCS_UPLOADS_BUCKET: str = "vantage-uploads-supple-moon-495404-b0"
    GCS_FAILED_BUCKET: str = "vantage-failed-ingestion-supple-moon-495404-b0"

    # Google Places API (sensitive — Secret Manager in prod, env var locally)
    GOOGLE_PLACES_API_KEY: str = ""

    # Google Custom Search (sensitive — Secret Manager in prod)
    GOOGLE_CUSTOM_SEARCH_API_KEY: str = ""
    GOOGLE_CUSTOM_SEARCH_CX: str = ""

    # Cache
    REVIEW_CACHE_DAYS: int = 30
    REDIS_URL: str = ""  # e.g. redis://10.x.x.x:6379 for Memorystore

    model_config = {"env_file": _ENV_FILE, "extra": "ignore"}

    def get_jwt_secret(self) -> str:
        """Return JWT secret from Secret Manager (prod) or env var (local)."""
        if self.ENVIRONMENT == "production":
            from backend.app.core.secrets import get_secret
            return get_secret("vantage-jwt-secret-key")
        return self.JWT_SECRET_KEY

    def get_places_api_key(self) -> str:
        if self.ENVIRONMENT == "production":
            from backend.app.core.secrets import get_secret
            return get_secret("vantage-google-places-api-key")
        return self.GOOGLE_PLACES_API_KEY

    def get_custom_search_api_key(self) -> str:
        if self.ENVIRONMENT == "production":
            from backend.app.core.secrets import get_secret
            return get_secret("vantage-google-custom-search-api-key")
        return self.GOOGLE_CUSTOM_SEARCH_API_KEY

    def get_custom_search_cx(self) -> str:
        if self.ENVIRONMENT == "production":
            from backend.app.core.secrets import get_secret
            return get_secret("vantage-google-custom-search-cx")
        return self.GOOGLE_CUSTOM_SEARCH_CX


@lru_cache()
def get_settings() -> Settings:
    return Settings()
