"""Lightweight async task scheduler for RetailOS.

Runs background jobs at configurable intervals without external dependencies.
Jobs include: daily P&L email, udhaar reminders, expiry alerts, backup.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

JobFunc = Callable[[], Coroutine[Any, Any, None]]


@dataclass
class ScheduledJob:
    name: str
    func: JobFunc
    interval_seconds: int
    description: str = ""
    enabled: bool = True
    last_run: float = 0.0
    run_count: int = 0
    error_count: int = 0
    last_error: str = ""


class Scheduler:
    """Simple interval-based async scheduler."""

    def __init__(self):
        self._jobs: dict[str, ScheduledJob] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    def add_job(
        self,
        name: str,
        func: JobFunc,
        interval_seconds: int,
        description: str = "",
        enabled: bool = True,
    ):
        """Register a recurring job."""
        self._jobs[name] = ScheduledJob(
            name=name,
            func=func,
            interval_seconds=interval_seconds,
            description=description,
            enabled=enabled,
        )
        logger.info("Scheduled job '%s' every %ds", name, interval_seconds)

    def remove_job(self, name: str):
        """Remove a job by name."""
        self._jobs.pop(name, None)

    def enable_job(self, name: str):
        if name in self._jobs:
            self._jobs[name].enabled = True

    def disable_job(self, name: str):
        if name in self._jobs:
            self._jobs[name].enabled = False

    def list_jobs(self) -> list[dict]:
        """List all registered jobs and their status."""
        return [
            {
                "name": j.name,
                "description": j.description,
                "interval_seconds": j.interval_seconds,
                "enabled": j.enabled,
                "last_run": j.last_run,
                "run_count": j.run_count,
                "error_count": j.error_count,
                "last_error": j.last_error,
            }
            for j in self._jobs.values()
        ]

    async def _run_loop(self):
        """Main scheduler loop — checks jobs every 10 seconds."""
        while self._running:
            now = time.time()
            for job in self._jobs.values():
                if not job.enabled:
                    continue
                if now - job.last_run < job.interval_seconds:
                    continue

                # Time to run
                try:
                    await job.func()
                    job.run_count += 1
                    job.last_run = now
                    job.last_error = ""
                    logger.info("Job '%s' completed (run #%d)", job.name, job.run_count)
                except Exception as e:
                    job.error_count += 1
                    job.last_error = str(e)
                    job.last_run = now  # Don't retry immediately
                    logger.error("Job '%s' failed: %s", job.name, e)

            await asyncio.sleep(10)

    def start(self):
        """Start the scheduler in the background."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Scheduler started with %d jobs", len(self._jobs))

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Scheduler stopped")


# ── Default Jobs ─────────────────────────────────────────

async def job_expiry_alerts():
    """Check for products nearing expiry and create notifications."""
    from sqlalchemy import select
    from db.session import async_session_factory
    from db.models import Product

    async with async_session_factory() as session:
        # Products with shelf_life_days set and last_restock_date
        result = await session.execute(
            select(Product).where(
                Product.shelf_life_days.isnot(None),
                Product.last_restock_date.isnot(None),
                Product.is_active.is_(True),
                Product.current_stock > 0,
            )
        )
        products = result.scalars().all()

        alerts = []
        for p in products:
            try:
                from datetime import datetime, timedelta
                restock_date = datetime.strptime(p.last_restock_date, "%Y-%m-%d")
                expiry_date = restock_date + timedelta(days=p.shelf_life_days)
                days_left = (expiry_date - datetime.now()).days
                if days_left <= 7 and days_left >= 0:
                    alerts.append({
                        "sku": p.sku,
                        "product_name": p.product_name,
                        "days_until_expiry": days_left,
                        "stock": p.current_stock,
                    })
            except (ValueError, TypeError):
                continue

        if alerts:
            logger.info("Expiry alerts: %d products expiring within 7 days", len(alerts))
        return alerts


async def job_low_stock_check():
    """Check for products below reorder threshold."""
    from sqlalchemy import select
    from db.session import async_session_factory
    from db.models import Product

    async with async_session_factory() as session:
        result = await session.execute(
            select(Product).where(
                Product.is_active.is_(True),
                Product.current_stock <= Product.reorder_threshold,
            )
        )
        low_stock = result.scalars().all()

        if low_stock:
            logger.info("Low stock: %d products below reorder threshold", len(low_stock))
        return low_stock


async def job_udhaar_reminders():
    """Send automated reminders for overdue credit accounts."""
    from sqlalchemy import select
    from db.session import async_session_factory
    from db.models import UdhaarLedger

    async with async_session_factory() as session:
        result = await session.execute(
            select(UdhaarLedger).where(UdhaarLedger.balance > 0)
        )
        overdue = result.scalars().all()

        sent = 0
        for ledger in overdue:
            if ledger.balance > 500:  # Only remind for significant balances
                # In production, this would call whatsapp_client.send_udhaar_reminder()
                logger.info(
                    "Udhaar reminder: %s owes ₹%.2f",
                    ledger.customer_name, ledger.balance,
                )
                sent += 1
        return sent


def register_default_jobs(scheduler: Scheduler):
    """Register the standard RetailOS background jobs."""
    scheduler.add_job(
        "expiry_alerts",
        job_expiry_alerts,
        interval_seconds=6 * 3600,  # Every 6 hours
        description="Check for products nearing expiry date",
    )
    scheduler.add_job(
        "low_stock_check",
        job_low_stock_check,
        interval_seconds=3600,  # Every hour
        description="Alert when products fall below reorder threshold",
    )
    scheduler.add_job(
        "udhaar_reminders",
        job_udhaar_reminders,
        interval_seconds=24 * 3600,  # Once daily
        description="Send payment reminders for overdue credit accounts",
    )
