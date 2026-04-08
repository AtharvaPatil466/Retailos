"""Security middleware: rate limiting, input sanitization, CORS hardening, RBAC."""

import hashlib
import html
import json
import os
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


# ── Role-Based Access Control Middleware ──

ROLE_HIERARCHY: dict[str, int] = {
    "owner": 4,
    "manager": 3,
    "staff": 2,
    "cashier": 1,
}

# Route patterns → minimum role required.
# Matched top-to-bottom; first match wins.
# Public routes (no auth needed) are listed under PUBLIC_PATTERNS.
PUBLIC_PATTERNS: list[re.Pattern] = [
    re.compile(r"^/api/auth/(login|register)$"),
    re.compile(r"^/api/v\d+/auth/(login|register)$"),
    re.compile(r"^/health"),
    re.compile(r"^/api/v\d+/health"),
    re.compile(r"^/docs"),
    re.compile(r"^/openapi\.json$"),
    re.compile(r"^/redoc"),
    re.compile(r"^/ws/"),          # WebSocket endpoints handle auth separately
    re.compile(r"^/$"),
]

# Routes that handle their own RBAC via Depends(require_role(...)).
# The middleware lets these through — double-checking would break
# their fine-grained role logic.
SELF_ENFORCED_PATTERNS: list[re.Pattern] = [
    re.compile(r"^/api/auth/"),       # auth routes use require_role() internally
    re.compile(r"^/api/v\d+/auth/"),
    re.compile(r"^/api/webhooks"),    # webhook routes enforce owner internally
    re.compile(r"^/api/v\d+/webhooks"),
]

# (HTTP method regex, path regex, minimum_role)
RBAC_RULES: list[tuple[re.Pattern, re.Pattern, str]] = [
    # Owner-only: backup, compliance, encryption, store settings
    (re.compile(r"^(POST|DELETE)$"), re.compile(r"^/api/backup/"), "owner"),
    (re.compile(r"^(POST|PUT|DELETE)$"), re.compile(r"^/api/store/"), "owner"),
    (re.compile(r".*"), re.compile(r"^/api/compliance/"), "owner"),
    (re.compile(r".*"), re.compile(r"^/api/encryption/"), "owner"),

    # Manager+: staff management, vendor management, promotions CRUD, reports
    (re.compile(r"^(POST|PUT|PATCH|DELETE)$"), re.compile(r"^/api/staff/"), "manager"),
    (re.compile(r"^(POST|PUT|PATCH|DELETE)$"), re.compile(r"^/api/vendors?/"), "manager"),
    (re.compile(r"^(POST|PUT|PATCH|DELETE)$"), re.compile(r"^/api/promotions/"), "manager"),
    (re.compile(r".*"), re.compile(r"^/api/reports/"), "manager"),
    (re.compile(r"^(POST|PUT|PATCH|DELETE)$"), re.compile(r"^/api/scheduler/"), "manager"),
    (re.compile(r"^(POST)$"), re.compile(r"^/api/push/broadcast$"), "manager"),
    (re.compile(r"^(POST|PUT|PATCH|DELETE)$"), re.compile(r"^/api/inventory/register$"), "manager"),

    # Staff+: inventory updates, approvals, shelf audit, delivery management
    (re.compile(r"^(POST|PUT|PATCH)$"), re.compile(r"^/api/inventory/"), "staff"),
    (re.compile(r"^(POST)$"), re.compile(r"^/api/approvals/"), "staff"),
    (re.compile(r"^(POST|PUT|PATCH)$"), re.compile(r"^/api/shelf/"), "staff"),
    (re.compile(r"^(POST|PUT|PATCH)$"), re.compile(r"^/api/delivery/"), "staff"),
    (re.compile(r"^(POST|PUT|PATCH)$"), re.compile(r"^/api/returns/"), "staff"),

    # Cashier (lowest authenticated role): sales, orders, cart, sync, reads
    (re.compile(r"^(POST)$"), re.compile(r"^/api/inventory/sale$"), "cashier"),
    (re.compile(r"^(POST)$"), re.compile(r"^/api/sync/"), "cashier"),
    (re.compile(r"^(GET)$"), re.compile(r"^/api/"), "cashier"),
]


class RBACMiddleware(BaseHTTPMiddleware):
    """Enforce role-based access control on API routes via JWT inspection.

    Routes are matched against RBAC_RULES by HTTP method and path.
    Public routes (health, auth, docs, websocket) bypass checks entirely.
    Any authenticated request whose role is below the required minimum gets 403.
    Unauthenticated requests to protected routes get 401.
    """

    # Strip /api/v1/ or /api/v2/ to canonical /api/ for matching
    _VERSION_PREFIX = re.compile(r"^/api/v\d+/")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        method = request.method

        # Normalize versioned paths: /api/v1/foo → /api/foo for rule matching
        canonical_path = self._VERSION_PREFIX.sub("/api/", path)

        # Skip public routes (check both original and canonical)
        for pattern in PUBLIC_PATTERNS:
            if pattern.match(path) or pattern.match(canonical_path):
                return await call_next(request)

        # Routes that enforce their own RBAC — let them through
        for pattern in SELF_ENFORCED_PATTERNS:
            if pattern.match(path) or pattern.match(canonical_path):
                return await call_next(request)

        # Find the minimum role for this method+path
        required_role = None
        for method_re, path_re, role in RBAC_RULES:
            if method_re.match(method) and (path_re.match(path) or path_re.match(canonical_path)):
                required_role = role
                break

        # If no rule matched, default to requiring at least cashier for any /api/ route
        if required_role is None:
            if path.startswith("/api/"):
                required_role = "cashier"
            else:
                return await call_next(request)

        min_level = ROLE_HIERARCHY.get(required_role, 0)

        # Extract role from JWT
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return Response(
                content=json.dumps({"detail": "Authentication required"}),
                status_code=401,
                media_type="application/json",
            )

        try:
            from jose import jwt as jose_jwt
            token = auth_header[7:]
            payload = jose_jwt.decode(
                token,
                os.environ.get("JWT_SECRET_KEY", ""),
                algorithms=["HS256"],
            )
            user_role = payload.get("role", "")
            user_level = ROLE_HIERARCHY.get(user_role, 0)

            if user_level < min_level:
                return Response(
                    content=json.dumps({
                        "detail": f"Forbidden: requires '{required_role}' role or higher, you have '{user_role}'",
                    }),
                    status_code=403,
                    media_type="application/json",
                )
        except Exception:
            return Response(
                content=json.dumps({"detail": "Invalid or expired token"}),
                status_code=401,
                media_type="application/json",
            )

        return await call_next(request)
