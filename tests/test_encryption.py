"""Tests for PII encryption and DPDP compliance."""

from auth.encryption import FieldEncryptor, PII_FIELDS


def test_encrypt_decrypt_roundtrip():
    enc = FieldEncryptor()
    original = "Ramesh Patel"
    encrypted = enc.encrypt(original)
    assert encrypted != original
    assert encrypted.startswith("enc:")
    decrypted = enc.decrypt(encrypted)
    assert decrypted == original


def test_encrypt_empty_string():
    enc = FieldEncryptor()
    encrypted = enc.encrypt("")
    assert encrypted.startswith("enc:")
    assert enc.decrypt(encrypted) == ""


def test_decrypt_plaintext_returns_as_is():
    enc = FieldEncryptor()
    plain = "not encrypted"
    assert enc.decrypt(plain) == plain


def test_is_encrypted():
    enc = FieldEncryptor()
    encrypted = enc.encrypt("test")
    assert encrypted.startswith("enc:")
    assert not "test".startswith("enc:")


def test_different_encryptions_differ():
    enc = FieldEncryptor()
    e1 = enc.encrypt("same text")
    e2 = enc.encrypt("same text")
    # Fernet uses random IV, so encryptions should differ
    assert e1 != e2


def test_pii_fields_registry():
    assert isinstance(PII_FIELDS, dict)
    assert len(PII_FIELDS) > 0


def test_encrypt_unicode():
    enc = FieldEncryptor()
    original = "राजेश पटेल +919876543210"
    encrypted = enc.encrypt(original)
    decrypted = enc.decrypt(encrypted)
    assert decrypted == original
