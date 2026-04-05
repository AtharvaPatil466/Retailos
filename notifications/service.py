import json
import logging
import os
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Notification, User

logger = logging.getLogger(__name__)


class NotificationService:
    """Unified notification dispatcher.

    Supports: in_app, email, sms, whatsapp, push.
    External channels (SMS, WhatsApp) log the notification but require
    real provider credentials to actually send.
    """

    def __init__(self):
        self._email_configured = bool(os.environ.get("SMTP_HOST"))
        self._sms_configured = bool(os.environ.get("SMS_API_KEY"))
        self._whatsapp_configured = bool(os.environ.get("WHATSAPP_API_KEY"))

    async def send(
        self,
        db: AsyncSession,
        *,
        user_id: str | None = None,
        store_id: str | None = None,
        channel: str = "in_app",
        title: str,
        body: str,
        category: str = "general",
        priority: str = "normal",
        metadata: dict[str, Any] | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            store_id=store_id,
            channel=channel,
            title=title,
            body=body,
            category=category,
            priority=priority,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        db.add(notification)
        await db.flush()

        # Dispatch to external channel
        if channel == "email":
            await self._send_email(user_id, title, body, db)
        elif channel == "sms":
            await self._send_sms(user_id, body, db)
        elif channel == "whatsapp":
            await self._send_whatsapp(user_id, body, db)

        return notification

    async def send_to_role(
        self,
        db: AsyncSession,
        *,
        store_id: str,
        role: str,
        channel: str = "in_app",
        title: str,
        body: str,
        category: str = "general",
        priority: str = "normal",
        metadata: dict[str, Any] | None = None,
    ) -> list[Notification]:
        """Send a notification to all users with a given role in a store."""
        result = await db.execute(
            select(User).where(User.store_id == store_id, User.role == role, User.is_active == True)
        )
        users = result.scalars().all()
        notifications = []
        for user in users:
            n = await self.send(
                db,
                user_id=user.id,
                store_id=store_id,
                channel=channel,
                title=title,
                body=body,
                category=category,
                priority=priority,
                metadata=metadata,
            )
            notifications.append(n)
        return notifications

    async def get_unread(self, db: AsyncSession, user_id: str, limit: int = 50) -> list[Notification]:
        result = await db.execute(
            select(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)
            .order_by(Notification.sent_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_read(self, db: AsyncSession, notification_id: str) -> bool:
        result = await db.execute(select(Notification).where(Notification.id == notification_id))
        notification = result.scalar_one_or_none()
        if notification:
            notification.is_read = True
            notification.read_at = time.time()
            return True
        return False

    async def mark_all_read(self, db: AsyncSession, user_id: str) -> int:
        result = await db.execute(
            select(Notification).where(Notification.user_id == user_id, Notification.is_read == False)
        )
        notifications = result.scalars().all()
        now = time.time()
        for n in notifications:
            n.is_read = True
            n.read_at = now
        return len(notifications)

    # ── External channel dispatchers ──

    async def _send_email(self, user_id: str | None, subject: str, body: str, db: AsyncSession):
        if not self._email_configured:
            logger.debug("Email not configured, skipping send for user %s", user_id)
            return

        user = None
        if user_id:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

        if not user or not user.email:
            return

        try:
            import aiosmtplib
            from email.mime.text import MIMEText

            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = os.environ.get("SMTP_FROM", "noreply@retailos.app")
            msg["To"] = user.email

            await aiosmtplib.send(
                msg,
                hostname=os.environ["SMTP_HOST"],
                port=int(os.environ.get("SMTP_PORT", 587)),
                username=os.environ.get("SMTP_USERNAME"),
                password=os.environ.get("SMTP_PASSWORD"),
                use_tls=os.environ.get("SMTP_USE_TLS", "true").lower() == "true",
            )
        except Exception as e:
            logger.warning("Failed to send email to %s: %s", user.email, e)

    async def _send_sms(self, user_id: str | None, body: str, db: AsyncSession):
        if not self._sms_configured:
            logger.debug("SMS not configured, skipping send for user %s", user_id)
            return
        # Placeholder for SMS provider integration (e.g., Twilio, MSG91)
        logger.info("SMS would be sent to user %s: %s", user_id, body[:50])

    async def _send_whatsapp(self, user_id: str | None, body: str, db: AsyncSession):
        if not self._whatsapp_configured:
            logger.debug("WhatsApp not configured, skipping send for user %s", user_id)
            return
        # Placeholder for WhatsApp Business API integration (e.g., Gupshup, Twilio)
        logger.info("WhatsApp would be sent to user %s: %s", user_id, body[:50])


# Singleton
notification_service = NotificationService()
