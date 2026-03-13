"""Tests for auth utilities."""
import pytest
from backend.app.core.auth import hash_password, verify_password, create_access_token, decode_token


def test_password_hashing():
    password = "TestPassword123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_token_creation():
    data = {"sub": "test@example.com", "role": "user", "name": "Test User", "uid": "123"}
    token = create_access_token(data)
    assert isinstance(token, str)

    decoded = decode_token(token)
    assert decoded["sub"] == "test@example.com"
    assert decoded["role"] == "user"


def test_jwt_invalid_token():
    with pytest.raises(Exception):
        decode_token("invalid.token.here")
