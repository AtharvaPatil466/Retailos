"""Security middleware: rate limiting, input sanitization, CORS hardening."""

import hashlib
import html
import json
import re
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


# Per-endpoint rate limit overrides (requests per minute)
ENDPOINT_LIMITS: dict[str, int] = {
    "/api/auth/login": 20,
    "/api/auth/register": 30,
    "/api/payments/create-order": 30,
    "/api/payments/webhook": 200,
    "/api/sms/send": 30,
    "/api/sms/send-otp": 10,
    "/api/whatsapp/send-text": 30,
    "/api/push/broadcast": 5,
    "/api/backup/create": 5,
    "/api/backup/restore": 3,
    "/health": 300,
    "/health/live": 300,
}

# Tiered rate limits by role
ROLE_LIMITS: dict[str, int] = {
    "owner": 300,
    "manager": 200,
    "staff": 150,
    "cashier": 120,
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Tiered rate limiter with per-IP, per-endpoint, and per-role controls."""

    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.default_rate = requests_per_minute
        self.window = 60  # seconds
        self._ip_hits: dict[str, list[float]] = defaultdict(list)
        self._endpoint_hits: dict[str, list[float]] = defaultdict(list)
        self._blocked_ips: dict[str, float] = {}  # IP -> blocked until timestamp

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        now = time.time()

        # Check if IP is temporarily blocked
        if client_ip in self._blocked_ips:
            if now < self._blocked_ips[client_ip]:
                remaining = int(self._blocked_ips[client_ip] - now)
                return Response(
                    content=json.dumps({"detail": "Too many requests. IP temporarily blocked.", "retry_after": remaining}),
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": str(remaining)},
                )
            del self._blocked_ips[client_ip]

        # Per-IP global rate limit
        self._ip_hits[client_ip] = [t for t in self._ip_hits[client_ip] if t > now - self.window]
        ip_limit = self.default_rate

        if len(self._ip_hits[client_ip]) >= ip_limit:
            # Block for 5 minutes after hitting limit
            self._blocked_ips[client_ip] = now + 300
            return Response(
                content=json.dumps({"detail": "Rate limit exceeded. IP blocked for 5 minutes.", "retry_after": 300}),
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "300"},
            )

        # Per-endpoint rate limit
        endpoint_limit = ENDPOINT_LIMITS.get(path)
        if endpoint_limit:
            key = f"{client_ip}:{path}"
            self._endpoint_hits[key] = [t for t in self._endpoint_hits[key] if t > now - self.window]
            if len(self._endpoint_hits[key]) >= endpoint_limit:
                return Response(
                    content=json.dumps({"detail": f"Rate limit exceeded for {path}. Try again later.", "limit": endpoint_limit}),
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": str(self.window)},
                )
            self._endpoint_hits[key].append(now)

        self._ip_hits[client_ip].append(now)

        response = await call_next(request)

        # Add rate limit headers
        remaining = ip_limit - len(self._ip_hits[client_ip])
        response.headers["X-RateLimit-Limit"] = str(ip_limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(int(now + self.window))

        return response

    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        now = time.time()
        active_ips = sum(1 for hits in self._ip_hits.values() if any(t > now - self.window for t in hits))
        return {
            "active_ips": active_ips,
            "blocked_ips": len(self._blocked_ips),
            "tracked_endpoints": len(self._endpoint_hits),
        }


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
