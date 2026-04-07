"""WhatsApp Business API integration via Gupshup/Meta Cloud API.

Supports sending template messages, free-form text, and media.
Used for udhaar reminders, order confirmations, delivery updates.
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

WHATSAPP_API_KEY = os.environ.get("WHATSAPP_API_KEY", "")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")
WHATSAPP_API_URL = os.environ.get(
    "WHATSAPP_API_URL",
    f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}" if WHATSAPP_PHONE_ID else "",
)

# In-memory log for demo mode
_message_log: list[dict[str, Any]] = []


class WhatsAppClient:
    """Async WhatsApp Business API client."""

    def __init__(self):
        self.api_key = WHATSAPP_API_KEY
        self.phone_id = WHATSAPP_PHONE_ID
        self.api_url = WHATSAPP_API_URL

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.phone_id)

    async def _send(self, payload: dict) -> dict:
        """Send a message via WhatsApp Business API."""
        if not self.is_configured:
            # Demo mode: log the message
            entry = {"status": "demo", "payload": payload}
            _message_log.append(entry)
            logger.info("WhatsApp demo: %s", payload.get("to", "unknown"))
            return {"demo": True, "status": "queued"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_url}/messages",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            result = resp.json()
            _message_log.append({"status": "sent", "response": result, "payload": payload})
            return result

    async def send_text(self, to: str, message: str) -> dict:
        """Send a plain text message."""
        return await self._send({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message},
        })

    async def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = "en",
        parameters: list[str] | None = None,
    ) -> dict:
        """Send a pre-approved template message."""
        components = []
        if parameters:
            components.append({
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in parameters],
            })

        return await self._send({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        })

    async def send_document(self, to: str, document_url: str, filename: str, caption: str = "") -> dict:
        """Send a document (PDF invoice, receipt, etc.)."""
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "document",
            "document": {
                "link": document_url,
                "filename": filename,
            },
        }
        if caption:
            payload["document"]["caption"] = caption
        return await self._send(payload)

    async def send_image(self, to: str, image_url: str, caption: str = "") -> dict:
        """Send an image."""
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": {"link": image_url},
        }
        if caption:
            payload["image"]["caption"] = caption
        return await self._send(payload)

    # ── Convenience methods for common RetailOS messages ──

    async def send_order_confirmation(self, phone: str, order_id: str, total: float, items_count: int) -> dict:
        """Send order confirmation to customer."""
        msg = (
            f"✅ *Order Confirmed*\n\n"
            f"Order: {order_id}\n"
            f"Items: {items_count}\n"
            f"Total: ₹{total:,.2f}\n\n"
            f"Thank you for your purchase!"
        )
        return await self.send_text(phone, msg)

    async def send_udhaar_reminder(self, phone: str, customer_name: str, balance: float, due_date: str = "") -> dict:
        """Send credit/udhaar payment reminder."""
        msg = (
            f"🔔 *Payment Reminder*\n\n"
            f"Dear {customer_name},\n"
            f"Your outstanding balance is ₹{balance:,.2f}.\n"
        )
        if due_date:
            msg += f"Due by: {due_date}\n"
        msg += "\nPlease clear your dues at your earliest convenience. Thank you!"
        return await self.send_text(phone, msg)

    async def send_delivery_update(self, phone: str, order_id: str, status: str, eta: str = "") -> dict:
        """Send delivery status update."""
        status_emoji = {"dispatched": "🚚", "out_for_delivery": "📦", "delivered": "✅"}.get(status, "📋")
        msg = f"{status_emoji} *Delivery Update*\n\nOrder: {order_id}\nStatus: {status.replace('_', ' ').title()}"
        if eta:
            msg += f"\nETA: {eta}"
        return await self.send_text(phone, msg)

    async def send_digital_receipt(self, phone: str, receipt_url: str, order_id: str) -> dict:
        """Send digital receipt as PDF document."""
        return await self.send_document(
            to=phone,
            document_url=receipt_url,
            filename=f"receipt_{order_id}.pdf",
            caption=f"Your receipt for order {order_id}",
        )


def get_message_log() -> list[dict]:
    """Get all sent/demo messages (for debugging and demo)."""
    return list(_message_log)


def clear_message_log():
    """Clear the message log."""
    _message_log.clear()


# Singleton
whatsapp_client = WhatsAppClient()
