"""Integration tests for authentication system."""

from auth.security import create_access_token, decode_token, hash_password, verify_password


def test_password_hashing():
    hashed = hash_password("testpassword123")
    assert verify_password("testpassword123", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_jwt_creation_and_decoding():
    token = create_access_token({"sub": "user-1", "role": "owner", "store_id": "store-001"})
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["role"] == "owner"


def test_expired_token():
    token = create_access_token({"sub": "user-1"}, expires_delta=-10)
    payload = decode_token(token)
    assert payload is None


def test_invalid_token():
    payload = decode_token("invalid.token.here")
    assert payload is None
