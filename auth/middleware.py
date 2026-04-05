"""Security middleware: rate limiting, input sanitization, CORS hardening."""

import hashlib
import html
import re
import time
from collections import defaultdict
from typing import Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiter per IP."""

    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.rate = requests_per_minute
        self.window = 60  # seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Prune old entries
        self._hits[client_ip] = [t for t in self._hits[client_ip] if t > now - self.window]

        if len(self._hits[client_ip]) >= self.rate:
            return Response(
                content='{"detail":"Rate limit exceeded. Try again later."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(self.window)},
            )

        self._hits[client_ip].append(now)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


# ── Input Sanitization Utilities ──

_XSS_PATTERN = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_SQL_INJECTION_PATTERNS = [
    re.compile(r"(\b(union|select|insert|update|delete|drop|alter)\b.*\b(from|into|table|where)\b)", re.IGNORECASE),
    re.compile(r"(--|;|/\*|\*/|@@|char\(|nchar\(|varchar\(|exec\(|execute\()", re.IGNORECASE),
]


def sanitize_string(value: str) -> str:
    """Remove potential XSS/injection from user input strings."""
    # HTML-encode to prevent XSS
    cleaned = html.escape(value.strip())
    # Remove script tags (even if encoded, belt-and-suspenders)
    cleaned = _XSS_PATTERN.sub("", cleaned)
    return cleaned


def detect_sql_injection(value: str) -> bool:
    """Heuristic SQL injection detection for logging/alerting."""
    for pattern in _SQL_INJECTION_PATTERNS:
        if pattern.search(value):
            return True
    return False


# ── DPDP Act Compliance Helpers ──

def hash_pii(value: str) -> str:
    """One-way hash for PII data that needs to be stored pseudonymized."""
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def mask_phone(phone: str) -> str:
    """Mask a phone number for display: +91 98***43210"""
    if len(phone) < 6:
        return "***"
    return phone[:5] + "***" + phone[-5:]


def mask_email(email: str) -> str:
    """Mask email for display: r***@gmail.com"""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return local[0] + "***@" + domain
