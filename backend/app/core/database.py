"""Firestore database client and ChromaDB vector store initialization."""
import os
from functools import lru_cache

from google.cloud import firestore
import chromadb

from backend.app.core.config import get_settings

settings = get_settings()

_firestore_client = None
_chroma_client = None


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


def get_chroma() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    return _chroma_client
