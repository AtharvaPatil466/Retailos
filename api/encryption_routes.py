"""Data encryption management API endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.dependencies import require_role
from auth.encryption import encryptor, PII_FIELDS
from db.models import User

router = APIRouter(prefix="/api/encryption", tags=["security"])


class EncryptRequest(BaseModel):
    value: str


class DecryptRequest(BaseModel):
    value: str


@router.get("/status")
async def encryption_status(user: User = Depends(require_role("owner"))):
    """Get encryption service status."""
    test_value = "test_encryption"
    encrypted = encryptor.encrypt(test_value)
    is_working = encryptor.decrypt(encrypted) == test_value

    return {
        "encryption_available": is_working,
        "algorithm": "AES-128-CBC (Fernet)",
        "pii_fields": PII_FIELDS,
    }


@router.post("/encrypt")
async def encrypt_value(
    body: EncryptRequest,
    user: User = Depends(require_role("owner")),
):
    """Encrypt a value (for testing/debugging)."""
    encrypted = encryptor.encrypt(body.value)
    return {
        "original_length": len(body.value),
        "encrypted": encrypted,
        "encrypted_length": len(encrypted),
        "is_encrypted": encryptor.is_encrypted(encrypted),
    }


@router.post("/decrypt")
async def decrypt_value(
    body: DecryptRequest,
    user: User = Depends(require_role("owner")),
):
    """Decrypt a value (for testing/debugging)."""
    decrypted = encryptor.decrypt(body.value)
    return {
        "decrypted": decrypted,
        "was_encrypted": encryptor.is_encrypted(body.value),
    }


@router.get("/pii-fields")
async def list_pii_fields(user: User = Depends(require_role("owner"))):
    """List all fields marked as PII that should be encrypted."""
    return {"pii_fields": PII_FIELDS}
