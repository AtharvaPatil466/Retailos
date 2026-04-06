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
    from runtime.metrics import metrics

    # DB row counts
    from db.models import Order, Product, Customer
    product_count = (await db.execute(select(text("count(*)")).select_from(Product.__table__))).scalar() or 0
    order_count = (await db.execute(select(text("count(*)")).select_from(Order.__table__))).scalar() or 0
    customer_count = (await db.execute(select(text("count(*)")).select_from(Customer.__table__))).scalar() or 0

    # Update business gauges
    metrics.set_gauge("db.products", product_count)
    metrics.set_gauge("db.orders", order_count)
    metrics.set_gauge("db.customers", customer_count)

    summary = metrics.get_summary()
    summary["db"] = {
        "products": product_count,
        "orders": order_count,
        "customers": customer_count,
    }
    summary["python_version"] = os.sys.version
    return summary


@router.get("/api/metrics/prometheus")
async def get_prometheus_metrics():
    """Export metrics in Prometheus text exposition format."""
    from fastapi.responses import PlainTextResponse
    from runtime.metrics import metrics
    return PlainTextResponse(
        content=metrics.get_prometheus_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
