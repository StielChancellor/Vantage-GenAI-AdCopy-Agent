"""Firestore database client initialization."""
from google.cloud import firestore

from backend.app.core.config import get_settings

settings = get_settings()

_firestore_client = None


def get_firestore() -> firestore.Client:
    global _firestore_client
    if _firestore_client is None:
        if settings.FIREBASE_SERVICE_ACCOUNT_PATH:
            _firestore_client = firestore.Client.from_service_account_json(
                settings.FIREBASE_SERVICE_ACCOUNT_PATH
            )
        else:
            _firestore_client = firestore.Client(project=settings.GCP_PROJECT_ID)
    return _firestore_client
