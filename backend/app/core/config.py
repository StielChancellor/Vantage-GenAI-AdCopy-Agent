from pathlib import Path

from pydantic_settings import BaseSettings
from functools import lru_cache

# Look for .env in backend/ directory or project root
_ENV_FILE = None
for candidate in [
    Path(__file__).resolve().parent.parent.parent / ".env",  # backend/.env
    Path.cwd() / ".env",  # project root .env
    Path.cwd() / "backend" / ".env",  # project root -> backend/.env
]:
    if candidate.exists():
        _ENV_FILE = str(candidate)
        break


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Vantage AdCopy Agent"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Auth
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours

    # Firebase
    FIREBASE_PROJECT_ID: str = "vantage-genai-adcopy-agent"
    FIREBASE_SERVICE_ACCOUNT_PATH: str = ""

    # Google AI (Gemini)
    GEMINI_API_KEY: str = ""

    # Google Places API
    GOOGLE_PLACES_API_KEY: str = ""

    # Google Custom Search (Event Grounding)
    GOOGLE_CUSTOM_SEARCH_API_KEY: str = ""
    GOOGLE_CUSTOM_SEARCH_CX: str = ""

    # GCP
    GCP_PROJECT_ID: str = "vantage-genai-adcopy-agent"
    GCP_PROJECT_NUMBER: str = "566761437172"

    # Cache
    REVIEW_CACHE_DAYS: int = 30

    model_config = {"env_file": _ENV_FILE, "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
