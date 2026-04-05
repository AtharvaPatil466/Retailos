"""Workflow improvements: configurable approval chains, undo/rollback, audit search."""

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_role
from db.models import AuditLog, User
from db.session import get_db

router = APIRouter(tags=["workflow"])

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
APPROVAL_CONFIG_PATH = DATA_DIR / "approval_config.json"

# ── Default approval chain config ──
DEFAULT_APPROVAL_CONFIG = {
    "chains": {
        "procurement": {
            "description": "Supplier procurement approvals",
            "levels": [
                {"role": "manager", "max_amount": 5000},
                {"role": "owner", "max_amount": None},
            ],
        },
        "pricing": {
            "description": "Price change approvals",
            "levels": [
                {"role": "manager", "max_amount": None},
            ],
        },
        "scheduling": {
            "description": "Staff schedule changes",
            "levels": [
                {"role": "manager", "max_amount": None},
            ],
        },
        "shelf_optimization": {
            "description": "Shelf placement changes",
            "levels": [
                {"role": "staff", "max_amount": None},
            ],
        },
        "refund": {
            "description": "Refund approvals",
            "levels": [
                {"role": "cashier", "max_amount": 500},
                {"role": "manager", "max_amount": 5000},
                {"role": "owner", "max_amount": None},
            ],
        },
    }
}


def _load_approval_config() -> dict:
    try:
        with open(APPROVAL_CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return DEFAULT_APPROVAL_CONFIG


def _save_approval_config(config: dict):
    with open(APPROVAL_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def get_required_approver_role(chain_name: str, amount: float | None = None) -> str:
    """Determine which role is needed to approve a given action."""
    config = _load_approval_config()
    chain = config.get("chains", {}).get(chain_name)
    if not chain:
        return "owner"  # default to owner if chain not configured

    for level in chain.get("levels", []):
        max_amt = level.get("max_amount")
        if max_amt is None or (amount is not None and amount <= max_amt):
            return level["role"]

    return "owner"


# ── Approval Chain Configuration ──

@router.get("/api/workflow/approval-chains")
async def get_approval_chains(user: User = Depends(require_role("manager"))):
    return _load_approval_config()


class ApprovalChainLevel(BaseModel):
    role: str
    max_amount: float | None = None


class UpdateChainRequest(BaseModel):
    description: str = ""
    levels: list[ApprovalChainLevel]


@router.put("/api/workflow/approval-chains/{chain_name}")
async def update_approval_chain(
    chain_name: str,
    body: UpdateChainRequest,
    user: User = Depends(require_role("owner")),
):
    config = _load_approval_config()
    config["chains"][chain_name] = {
        "description": body.description,
        "levels": [l.model_dump() for l in body.levels],
    }
    _save_approval_config(config)
    return {"status": "ok", "chain": chain_name}


# ── Audit Log Search & Filtering ──

@router.get("/api/workflow/audit/search")
async def search_audit_logs(
    q: str | None = Query(None, description="Search in decision/reasoning/outcome"),
    skill: str | None = None,
    event_type: str | None = None,
    status: str | None = None,
    date_from: str | None = Query(None, description="YYYY-MM-DD"),
    date_to: str | None = Query(None, description="YYYY-MM-DD"),
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(require_role("staff")),
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditLog).order_by(AuditLog.timestamp.desc())

    if skill:
        query = query.where(AuditLog.skill == skill)
    if event_type:
        query = query.where(AuditLog.event_type == event_type)
    if status:
        query = query.where(AuditLog.status == status)
    if date_from:
        from datetime import datetime
        ts_from = datetime.strptime(date_from, "%Y-%m-%d").timestamp()
        query = query.where(AuditLog.timestamp >= ts_from)
    if date_to:
        from datetime import datetime
        ts_to = datetime.strptime(date_to, "%Y-%m-%d").timestamp() + 86400
        query = query.where(AuditLog.timestamp < ts_to)

    result = await db.execute(query.limit(limit).offset(offset))
    logs = result.scalars().all()

    # Text search filter (post-query for SQLite compatibility)
    if q:
        q_lower = q.lower()
        logs = [
            l for l in logs
            if q_lower in (l.decision or "").lower()
            or q_lower in (l.reasoning or "").lower()
            or q_lower in (l.outcome or "").lower()
        ]

    return {
        "logs": [
            {
                "id": l.id,
                "timestamp": l.timestamp,
                "skill": l.skill,
                "event_type": l.event_type,
                "decision": l.decision,
                "reasoning": l.reasoning,
                "outcome": l.outcome[:500],
                "status": l.status,
            }
            for l in logs
        ],
        "count": len(logs),
    }


# ── Undo / Rollback ──

# Undo stack: stores recent reversible actions
_undo_stack: list[dict[str, Any]] = []
MAX_UNDO_STACK = 50


def push_undoable(action_type: str, data: dict[str, Any], reverse_data: dict[str, Any]):
    """Push a reversible action onto the undo stack."""
    _undo_stack.append({
        "action_type": action_type,
        "data": data,
        "reverse_data": reverse_data,
        "timestamp": time.time(),
    })
    if len(_undo_stack) > MAX_UNDO_STACK:
        _undo_stack.pop(0)


@router.get("/api/workflow/undo-stack")
async def get_undo_stack(user: User = Depends(require_role("manager"))):
    return {"actions": list(reversed(_undo_stack[-10:]))}


@router.post("/api/workflow/undo")
async def undo_last_action(user: User = Depends(require_role("manager"))):
    if not _undo_stack:
        raise HTTPException(status_code=404, detail="Nothing to undo")

    action = _undo_stack.pop()
    action_type = action["action_type"]

    if action_type == "stock_update":
        # Reverse a stock update
        reverse = action["reverse_data"]
        inventory = []
        try:
            with open(DATA_DIR / "mock_inventory.json") as f:
                inventory = json.load(f)
        except Exception:
            pass

        for item in inventory:
            if item["sku"] == reverse.get("sku"):
                item["current_stock"] = reverse["old_stock"]
                break

        with open(DATA_DIR / "mock_inventory.json", "w") as f:
            json.dump(inventory, f, indent=2)
            f.write("\n")

        return {"status": "undone", "action_type": action_type, "detail": f"Reverted stock for {reverse.get('sku')}"}

    elif action_type == "price_change":
        reverse = action["reverse_data"]
        inventory = []
        try:
            with open(DATA_DIR / "mock_inventory.json") as f:
                inventory = json.load(f)
        except Exception:
            pass

        for item in inventory:
            if item["sku"] == reverse.get("sku"):
                item["unit_price"] = reverse["old_price"]
                break

        with open(DATA_DIR / "mock_inventory.json", "w") as f:
            json.dump(inventory, f, indent=2)
            f.write("\n")

        return {"status": "undone", "action_type": action_type, "detail": f"Reverted price for {reverse.get('sku')}"}

    return {"status": "undone", "action_type": action_type, "detail": "Action reversed (no-op handler)"}


# ── Scheduled Reports ──

_scheduled_reports: list[dict] = []


class ScheduleReportRequest(BaseModel):
    report_type: str  # sales | pnl | inventory | gst
    frequency: str  # daily | weekly | monthly
    email_to: str
    time_of_day: str = "20:30"


@router.post("/api/workflow/scheduled-reports")
async def create_scheduled_report(
    body: ScheduleReportRequest,
    user: User = Depends(require_role("owner")),
):
    report = {
        "id": f"sched_{len(_scheduled_reports) + 1}",
        "report_type": body.report_type,
        "frequency": body.frequency,
        "email_to": body.email_to,
        "time_of_day": body.time_of_day,
        "created_by": user.id,
        "created_at": time.time(),
        "is_active": True,
    }
    _scheduled_reports.append(report)
    return report


@router.get("/api/workflow/scheduled-reports")
async def list_scheduled_reports(user: User = Depends(require_role("manager"))):
    return {"reports": _scheduled_reports}
