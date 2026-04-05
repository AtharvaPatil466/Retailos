"""Health checks, structured logging config, and metrics endpoint."""

import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db

router = APIRouter(tags=["ops"])

_start_time = time.time()
_request_count = 0
_error_count = 0


def increment_request_count():
    global _request_count
    _request_count += 1


def increment_error_count():
    global _error_count
    _error_count += 1


@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}


@router.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    checks = {"database": False, "data_files": False}

    # DB check
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass

    # Data files check
    data_dir = Path(__file__).resolve().parent.parent / "data"
    checks["data_files"] = (data_dir / "mock_inventory.json").exists()

    all_ok = all(checks.values())
    return {"status": "ready" if all_ok else "degraded", "checks": checks}


@router.get("/health/live")
async def liveness_check():
    return {"status": "alive", "uptime_seconds": round(time.time() - _start_time, 1)}


@router.get("/api/metrics")
async def get_metrics(db: AsyncSession = Depends(get_db)):
    uptime = time.time() - _start_time

    # DB row counts
    from db.models import Order, Product, Customer
    product_count = (await db.execute(select(text("count(*)")).select_from(Product.__table__))).scalar() or 0
    order_count = (await db.execute(select(text("count(*)")).select_from(Order.__table__))).scalar() or 0
    customer_count = (await db.execute(select(text("count(*)")).select_from(Customer.__table__))).scalar() or 0

    return {
        "uptime_seconds": round(uptime, 1),
        "requests_total": _request_count,
        "errors_total": _error_count,
        "db": {
            "products": product_count,
            "orders": order_count,
            "customers": customer_count,
        },
        "python_version": os.sys.version,
    }


def setup_structured_logging():
    """Configure JSON-formatted structured logging."""
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    formatter = logging.Formatter(
        fmt='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(log_level)

    # Clear existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
