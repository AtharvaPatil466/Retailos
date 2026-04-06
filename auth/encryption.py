"""Data encryption at rest for sensitive fields.

Uses Fernet symmetric encryption (AES-128-CBC) for encrypting PII
and sensitive data stored in the database. Encryption key is derived
from the JWT secret or a dedicated ENCRYPTION_KEY env var.

Fields that should be encrypted:
- Customer phone numbers
- Customer email addresses
- Payment details
- WhatsApp numbers
- Staff phone numbers
"""

import base64
import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _get_key() -> bytes:
    """Derive a 32-byte Fernet key from environment secret."""
    secret = os.environ.get("ENCRYPTION_KEY", os.environ.get("JWT_SECRET_KEY", "default-dev-key"))
    # Derive a proper Fernet key using SHA256
    key_bytes = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


class FieldEncryptor:
    """Encrypt/decrypt sensitive database fields."""

    def __init__(self):
        self._key: Optional[bytes] = None
        self._fernet = None

    def _ensure_fernet(self):
        if self._fernet is None:
            try:
                from cryptography.fernet import Fernet
                self._key = _get_key()
                self._fernet = Fernet(self._key)
            except ImportError:
                logger.warning("cryptography package not installed. Encryption disabled.")
                return False
        return True

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string value. Returns base64-encoded ciphertext with 'enc:' prefix."""
        if not plaintext or plaintext.startswith("enc:"):
            return plaintext

        if not self._ensure_fernet():
            return plaintext

        try:
            encrypted = self._fernet.encrypt(plaintext.encode())
            return f"enc:{encrypted.decode()}"
        except Exception as e:
            logger.warning("Encryption failed: %s", e)
            return plaintext

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a previously encrypted value."""
        if not ciphertext or not ciphertext.startswith("enc:"):
            return ciphertext

        if not self._ensure_fernet():
            return ciphertext

        try:
            encrypted_data = ciphertext[4:].encode()  # Strip 'enc:' prefix
            return self._fernet.decrypt(encrypted_data).decode()
        except Exception as e:
            logger.warning("Decryption failed: %s", e)
            return ciphertext

    def is_encrypted(self, value: str) -> bool:
        return bool(value and value.startswith("enc:"))

    def encrypt_dict(self, data: dict, fields: list[str]) -> dict:
        """Encrypt specific fields in a dictionary."""
        result = dict(data)
        for field in fields:
            if field in result and result[field]:
                result[field] = self.encrypt(str(result[field]))
        return result

    def decrypt_dict(self, data: dict, fields: list[str]) -> dict:
        """Decrypt specific fields in a dictionary."""
        result = dict(data)
        for field in fields:
            if field in result and result[field]:
                result[field] = self.decrypt(str(result[field]))
        return result


# Singleton
encryptor = FieldEncryptor()

# Fields that contain PII and should be encrypted
PII_FIELDS = {
    "customer": ["phone", "email"],
    "user": ["phone", "email"],
    "staff": ["phone"],
    "supplier": ["contact_phone", "whatsapp_number"],
    "udhaar": ["phone"],
    "delivery": ["phone", "address"],
}


def encrypt_pii(value: str) -> str:
    """Convenience function to encrypt a PII value."""
    return encryptor.encrypt(value)


def decrypt_pii(value: str) -> str:
    """Convenience function to decrypt a PII value."""
    return encryptor.decrypt(value)
