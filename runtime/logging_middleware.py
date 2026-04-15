"""Request logging middleware with correlation IDs."""

import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from runtime.logging_config import (
    bind_request_context,
    clear_request_context,
    generate_request_id,
)
from runtime.metrics import metrics

logger = logging.getLogger("retailos.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all HTTP requests with timing and correlation IDs."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        req_id = request.headers.get("X-Request-ID", generate_request_id())

        user_id = ""
        store_id = ""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from jose import jwt
                import os
                token = auth_header[7:]
                payload = jwt.decode(
                    token,
                    os.environ.get("JWT_SECRET_KEY", ""),
                    algorithms=["HS256"],
                    options={"verify_exp": False},
                )
                user_id = payload.get("sub", "")
                store_id = payload.get("store_id", "")
            except Exception:
                pass

        bind_request_context(request_id=req_id, user_id=user_id, store_id=store_id)

        start = time.time()
        client_ip = request.client.host if request.client else "unknown"
        metrics.request_started()

        try:
            response = await call_next(request)
            duration_ms = round((time.time() - start) * 1000, 1)
            metrics.request_finished()
            metrics.record_request(request.method, request.url.path, response.status_code, duration_ms)

            # Add correlation headers to response
            response.headers["X-Request-ID"] = req_id

            # Log the request
            logger.info(
                "%s %s %d %.1fms",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
            )

            return response

        except Exception as exc:
            duration_ms = round((time.time() - start) * 1000, 1)
            metrics.request_finished()
            metrics.record_request(request.method, request.url.path, 500, duration_ms)
            logger.error(
                "%s %s ERROR %.1fms: %s",
                request.method,
                request.url.path,
                duration_ms,
                str(exc),
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
                exc_info=True,
            )
            raise
        finally:
            clear_request_context()
