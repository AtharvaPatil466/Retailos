"""Scheduler management API routes."""

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import require_role
from db.models import User
from scheduler.engine import Scheduler

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])

# Singleton — initialized in create_app
_scheduler: Scheduler | None = None


def set_scheduler(scheduler: Scheduler):
    global _scheduler
    _scheduler = scheduler


def get_scheduler() -> Scheduler:
    if _scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")
    return _scheduler


@router.get("/jobs")
async def list_jobs(user: User = Depends(require_role("manager"))):
    """List all scheduled jobs and their status."""
    scheduler = get_scheduler()
    return {"jobs": scheduler.list_jobs()}


@router.post("/jobs/{job_name}/enable")
async def enable_job(job_name: str, user: User = Depends(require_role("owner"))):
    """Enable a scheduled job."""
    scheduler = get_scheduler()
    scheduler.enable_job(job_name)
    return {"status": "enabled", "job": job_name}


@router.post("/jobs/{job_name}/disable")
async def disable_job(job_name: str, user: User = Depends(require_role("owner"))):
    """Disable a scheduled job."""
    scheduler = get_scheduler()
    scheduler.disable_job(job_name)
    return {"status": "disabled", "job": job_name}


@router.post("/jobs/{job_name}/run-now")
async def run_job_now(job_name: str, user: User = Depends(require_role("owner"))):
    """Manually trigger a scheduled job immediately."""
    scheduler = get_scheduler()
    jobs = {j["name"]: j for j in scheduler.list_jobs()}
    if job_name not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_name}' not found")

    # Find and run the job
    job = scheduler._jobs.get(job_name)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_name}' not found")

    try:
        await job.func()
        job.run_count += 1
        import time
        job.last_run = time.time()
        return {"status": "completed", "job": job_name, "run_count": job.run_count}
    except Exception as e:
        job.error_count += 1
        job.last_error = str(e)
        raise HTTPException(status_code=500, detail=f"Job failed: {str(e)}")
