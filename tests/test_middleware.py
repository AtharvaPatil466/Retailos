"""Tests for security middleware utilities."""

from auth.middleware import (
    detect_sql_injection,
    mask_email,
    mask_phone,
    sanitize_string,
)


def test_sanitize_removes_script_tags():
    result = sanitize_string('<script>alert("xss")</script>Hello')
    assert "<script>" not in result
    assert "Hello" in result


def test_sanitize_html_encodes():
    result = sanitize_string('<img src=x onerror=alert(1)>')
    assert "<img" not in result


def test_detect_sql_injection_true():
    assert detect_sql_injection("1; DROP TABLE users;--")
    assert detect_sql_injection("' UNION SELECT * FROM users --")


def test_detect_sql_injection_false():
    assert not detect_sql_injection("Amul Butter 500g")
    assert not detect_sql_injection("normal search query")


def test_mask_phone():
    assert mask_phone("+919876543210") == "+9198***43210"


def test_mask_email():
    assert mask_email("rahul@gmail.com") == "r***@gmail.com"
