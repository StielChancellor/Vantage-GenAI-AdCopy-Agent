from pydantic_settings import BaseSettings
from functools import lru_cache


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

    # GCP
    GCP_PROJECT_ID: str = "vantage-genai-adcopy-agent"
    GCP_PROJECT_NUMBER: str = "566761437172"

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    # Cache
    REVIEW_CACHE_DAYS: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
