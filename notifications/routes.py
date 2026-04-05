from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_role
from db.models import User
from db.session import get_db
from notifications.service import notification_service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def get_notifications(
    limit: int = 50,
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    notifications = await notification_service.get_unread(db, user.id, limit=limit)
    return [
        {
            "id": n.id,
            "channel": n.channel,
            "title": n.title,
            "body": n.body,
            "category": n.category,
            "priority": n.priority,
            "is_read": n.is_read,
            "sent_at": n.sent_at,
        }
        for n in notifications
    ]


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    ok = await notification_service.mark_read(db, notification_id)
    return {"status": "ok" if ok else "not_found"}


@router.post("/read-all")
async def mark_all_read(
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    count = await notification_service.mark_all_read(db, user.id)
    return {"status": "ok", "marked_read": count}
