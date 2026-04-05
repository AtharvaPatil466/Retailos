"""Webhook system for third-party integrations.

Register URLs to receive event notifications when things happen in RetailOS.
"""

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.dependencies import require_role
from db.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# In-memory webhook registry (would be DB-backed in production)
_webhooks: list[dict[str, Any]] = []


class WebhookRegisterRequest(BaseModel):
    url: str
    events: list[str]  # e.g. ["order.created", "stock.low", "approval.pending"]
    secret: str = ""  # for HMAC signature verification
    description: str = ""


SUPPORTED_EVENTS = [
    "order.created",
    "order.delivered",
    "stock.low",
    "stock.updated",
    "approval.pending",
    "approval.resolved",
    "supplier.reply",
    "deal.confirmed",
    "return.created",
    "return.processed",
    "delivery.dispatched",
    "delivery.completed",
    "udhaar.credit",
    "udhaar.payment",
    "shift.review",
    "expiry.risk",
]


@router.get("/events")
async def list_supported_events():
    return {"events": SUPPORTED_EVENTS}


@router.post("")
async def register_webhook(
    body: WebhookRegisterRequest,
    user: User = Depends(require_role("owner")),
):
    invalid = [e for e in body.events if e not in SUPPORTED_EVENTS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported events: {invalid}")

    webhook = {
        "id": f"wh_{len(_webhooks) + 1}",
        "url": body.url,
        "events": body.events,
        "secret": body.secret,
        "description": body.description,
        "created_by": user.id,
        "created_at": time.time(),
        "is_active": True,
        "delivery_count": 0,
        "failure_count": 0,
    }
    _webhooks.append(webhook)
    return {"id": webhook["id"], "status": "registered"}


@router.get("")
async def list_webhooks(user: User = Depends(require_role("owner"))):
    return {"webhooks": [{k: v for k, v in wh.items() if k != "secret"} for wh in _webhooks]}


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str, user: User = Depends(require_role("owner"))):
    for i, wh in enumerate(_webhooks):
        if wh["id"] == webhook_id:
            _webhooks.pop(i)
            return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Webhook not found")


async def dispatch_webhook_event(event_name: str, payload: dict[str, Any]):
    """Fire-and-forget: send event to all registered webhooks."""
    for wh in _webhooks:
        if not wh.get("is_active"):
            continue
        if event_name not in wh.get("events", []):
            continue

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    wh["url"],
                    json={"event": event_name, "data": payload, "timestamp": time.time()},
                    headers={"X-RetailOS-Event": event_name},
                )
            wh["delivery_count"] = wh.get("delivery_count", 0) + 1
        except Exception as e:
            wh["failure_count"] = wh.get("failure_count", 0) + 1
            logger.warning("Webhook delivery failed for %s: %s", wh["id"], e)
