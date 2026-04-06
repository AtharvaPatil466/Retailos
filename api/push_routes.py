"""Web Push Notification API endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.dependencies import require_role
from db.models import User
from notifications.push import push_service

router = APIRouter(prefix="/api/push", tags=["notifications"])


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict


class PushMessage(BaseModel):
    user_id: str
    title: str
    body: str
    icon: str = "/icon-192.png"
    url: str = "/"


class BroadcastMessage(BaseModel):
    title: str
    body: str
    icon: str = "/icon-192.png"
    url: str = "/"


@router.get("/vapid-key")
async def get_vapid_key():
    """Get the VAPID public key for push subscription."""
    return {
        "public_key": push_service.get_public_key(),
        "is_configured": push_service.is_configured,
    }


@router.post("/subscribe")
async def subscribe(
    subscription: PushSubscription,
    user: User = Depends(require_role("cashier")),
):
    """Register browser push subscription for current user."""
    result = push_service.subscribe(user.id, subscription.model_dump())
    return result


@router.post("/unsubscribe")
async def unsubscribe(user: User = Depends(require_role("cashier"))):
    """Remove push subscription for current user."""
    return push_service.unsubscribe(user.id)


@router.post("/send")
async def send_push(
    message: PushMessage,
    user: User = Depends(require_role("manager")),
):
    """Send a push notification to a specific user."""
    return await push_service.send(
        user_id=message.user_id,
        title=message.title,
        body=message.body,
        icon=message.icon,
        url=message.url,
    )


@router.post("/broadcast")
async def broadcast_push(
    message: BroadcastMessage,
    user: User = Depends(require_role("owner")),
):
    """Broadcast push notification to all subscribed users."""
    return await push_service.broadcast(
        title=message.title,
        body=message.body,
        icon=message.icon,
        url=message.url,
    )


@router.get("/status")
async def push_status(user: User = Depends(require_role("staff"))):
    """Get push notification service status."""
    return {
        "is_configured": push_service.is_configured,
        "subscribers_count": push_service.get_subscribers_count(),
    }


@router.get("/log")
async def push_log(
    limit: int = 50,
    user: User = Depends(require_role("manager")),
):
    """Get recent push notification log (demo mode)."""
    return {"notifications": push_service.get_log(limit), "count": len(push_service.get_log(limit))}
