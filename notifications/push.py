"""Web Push Notification service using VAPID protocol.

Supports browser push notifications via the Web Push standard.
In demo mode (no VAPID keys configured), stores subscriptions and
logs notifications in-memory for testing.
"""

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class PushNotificationService:
    """VAPID-based web push notification sender."""

    def __init__(self):
        self.vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY", "")
        self.vapid_public_key = os.environ.get("VAPID_PUBLIC_KEY", "")
        self.vapid_email = os.environ.get("VAPID_EMAIL", "mailto:admin@retailos.app")
        self._subscriptions: dict[str, dict] = {}  # user_id -> subscription info
        self._notification_log: list[dict] = []

    @property
    def is_configured(self) -> bool:
        return bool(self.vapid_private_key and self.vapid_public_key)

    def get_public_key(self) -> str:
        return self.vapid_public_key

    def subscribe(self, user_id: str, subscription: dict) -> dict:
        """Register a push subscription for a user."""
        self._subscriptions[user_id] = {
            "subscription": subscription,
            "subscribed_at": time.time(),
            "user_id": user_id,
        }
        return {"status": "subscribed", "user_id": user_id}

    def unsubscribe(self, user_id: str) -> dict:
        """Remove a push subscription."""
        self._subscriptions.pop(user_id, None)
        return {"status": "unsubscribed", "user_id": user_id}

    def get_subscription(self, user_id: str) -> dict | None:
        entry = self._subscriptions.get(user_id)
        return entry["subscription"] if entry else None

    async def send(
        self,
        user_id: str,
        title: str,
        body: str,
        icon: str = "/icon-192.png",
        url: str = "/",
        data: dict[str, Any] | None = None,
    ) -> dict:
        """Send a push notification to a subscribed user."""
        sub = self._subscriptions.get(user_id)
        if not sub:
            return {"status": "error", "detail": "User not subscribed"}

        payload = json.dumps({
            "title": title,
            "body": body,
            "icon": icon,
            "url": url,
            "data": data or {},
            "timestamp": time.time(),
        })

        if self.is_configured:
            try:
                from pywebpush import webpush, WebPushException
                webpush(
                    subscription_info=sub["subscription"],
                    data=payload,
                    vapid_private_key=self.vapid_private_key,
                    vapid_claims={"sub": self.vapid_email},
                )
                logger.info("Push sent to user %s: %s", user_id, title)
                return {"status": "sent", "user_id": user_id}
            except Exception as e:
                logger.warning("Push failed for user %s: %s", user_id, e)
                return {"status": "error", "detail": str(e)}
        else:
            # Demo mode: log the notification
            entry = {
                "user_id": user_id,
                "title": title,
                "body": body,
                "icon": icon,
                "url": url,
                "timestamp": time.time(),
                "demo": True,
            }
            self._notification_log.append(entry)
            logger.info("Push (demo) to user %s: %s", user_id, title)
            return {"status": "sent_demo", "user_id": user_id}

    async def broadcast(
        self,
        title: str,
        body: str,
        icon: str = "/icon-192.png",
        url: str = "/",
    ) -> dict:
        """Send push notification to all subscribed users."""
        results = []
        for user_id in list(self._subscriptions.keys()):
            result = await self.send(user_id, title, body, icon, url)
            results.append(result)
        return {"sent": len(results), "results": results}

    def get_log(self, limit: int = 50) -> list[dict]:
        return self._notification_log[-limit:]

    def get_subscribers_count(self) -> int:
        return len(self._subscriptions)


push_service = PushNotificationService()
