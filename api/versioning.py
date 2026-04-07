"""API versioning middleware and utilities.

Supports versioned routes (/api/v1/...) while maintaining backward
compatibility with unversioned routes (/api/...).

Strategy:
- /api/v1/* → rewrites to /api/* internally, served with version header
- /api/v2/* → existing v2 routes, served as-is
- /api/*    → legacy access, served with deprecation headers
"""

from typing import Callable

from fastapi import APIRouter, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Supported API versions
CURRENT_VERSION = "v1"
SUPPORTED_VERSIONS = ["v1", "v2"]
SUNSET_DATE = "2027-06-01"

router = APIRouter(tags=["versioning"])


class APIVersionMiddleware(BaseHTTPMiddleware):
    """Route versioned API requests and add version/deprecation headers."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # /api/v1/... → rewrite path to /api/... for internal routing
        if path.startswith("/api/v1/"):
            request.scope["path"] = "/api/" + path[8:]
            response = await call_next(request)
            response.headers["X-API-Version"] = "v1"
            return response

        # /api/v2/... → existing v2 routes, no rewrite needed
        if path.startswith("/api/v2/"):
            response = await call_next(request)
            response.headers["X-API-Version"] = "v2"
            return response

        # Legacy /api/... → serve with deprecation notice
        if path.startswith("/api/") and not path.startswith("/api/v"):
            response = await call_next(request)
            response.headers["X-API-Version"] = "v1"
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = SUNSET_DATE
            # Link to versioned equivalent
            versioned_path = "/api/v1/" + path[5:]
            response.headers["Link"] = f'<{versioned_path}>; rel="successor-version"'
            return response

        return await call_next(request)


@router.get("/api/version")
async def get_api_version():
    """Return current API version info and supported versions."""
    return {
        "current_version": CURRENT_VERSION,
        "supported_versions": SUPPORTED_VERSIONS,
        "deprecation_notice": (
            f"Unversioned /api/* routes are deprecated. "
            f"Use /api/v1/* instead. Sunset date: {SUNSET_DATE}"
        ),
        "docs": {
            "v1": "/docs (use /api/v1/ prefix for all endpoints)",
            "openapi": "/openapi.json",
        },
    }
