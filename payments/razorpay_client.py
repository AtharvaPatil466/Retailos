"""Razorpay payment gateway integration.

Supports UPI, card, netbanking, and wallet payments.
Handles order creation, payment verification, and refunds.
"""

import hashlib
import hmac
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"


class RazorpayClient:
    """Async Razorpay API client."""

    def __init__(self, key_id: str = "", key_secret: str = ""):
        self.key_id = key_id or RAZORPAY_KEY_ID
        self.key_secret = key_secret or RAZORPAY_KEY_SECRET

    @property
    def is_configured(self) -> bool:
        return bool(self.key_id and self.key_secret)

    async def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        """Make an authenticated request to Razorpay API."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method,
                f"{RAZORPAY_BASE_URL}{path}",
                json=data,
                auth=(self.key_id, self.key_secret),
            )
            resp.raise_for_status()
            return resp.json()

    async def create_order(
        self,
        amount_paise: int,
        currency: str = "INR",
        receipt: str = "",
        notes: dict[str, str] | None = None,
    ) -> dict:
        """Create a Razorpay order.

        Args:
            amount_paise: Amount in paise (e.g., 50000 = ₹500)
            currency: Currency code (default INR)
            receipt: Your internal order/receipt ID
            notes: Optional metadata dict
        """
        payload = {
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
        }
        if notes:
            payload["notes"] = notes

        return await self._request("POST", "/orders", payload)

    async def fetch_order(self, order_id: str) -> dict:
        """Fetch order details by Razorpay order ID."""
        return await self._request("GET", f"/orders/{order_id}")

    async def fetch_payment(self, payment_id: str) -> dict:
        """Fetch payment details by Razorpay payment ID."""
        return await self._request("GET", f"/payments/{payment_id}")

    async def create_refund(
        self,
        payment_id: str,
        amount_paise: int | None = None,
        notes: dict[str, str] | None = None,
    ) -> dict:
        """Create a refund (full or partial).

        Args:
            payment_id: Razorpay payment ID to refund
            amount_paise: Partial refund amount in paise (None = full refund)
        """
        payload: dict[str, Any] = {}
        if amount_paise is not None:
            payload["amount"] = amount_paise
        if notes:
            payload["notes"] = notes

        return await self._request("POST", f"/payments/{payment_id}/refund", payload)

    async def fetch_refund(self, payment_id: str, refund_id: str) -> dict:
        """Fetch refund details."""
        return await self._request("GET", f"/payments/{payment_id}/refunds/{refund_id}")

    def verify_payment_signature(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> bool:
        """Verify Razorpay webhook/checkout payment signature using HMAC SHA256."""
        message = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected = hmac.new(
            self.key_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, razorpay_signature)

    def verify_webhook_signature(self, body: str, signature: str, webhook_secret: str = "") -> bool:
        """Verify Razorpay webhook event signature."""
        secret = webhook_secret or self.key_secret
        expected = hmac.new(
            secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


# ── In-memory payment tracker (for demo/offline mode) ────

_payment_records: list[dict[str, Any]] = []


def record_payment(
    order_id: str,
    amount: float,
    method: str = "upi",
    status: str = "captured",
    customer_id: str = "",
    razorpay_payment_id: str = "",
    razorpay_order_id: str = "",
) -> dict:
    """Record a payment (works even without Razorpay keys)."""
    record = {
        "id": f"pay_{len(_payment_records) + 1}_{int(time.time())}",
        "order_id": order_id,
        "amount": amount,
        "method": method,
        "status": status,
        "customer_id": customer_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_order_id": razorpay_order_id,
        "created_at": time.time(),
    }
    _payment_records.append(record)
    return record


def get_payment_records(order_id: str = "", customer_id: str = "") -> list[dict]:
    """Get payment records, optionally filtered."""
    records = _payment_records
    if order_id:
        records = [r for r in records if r["order_id"] == order_id]
    if customer_id:
        records = [r for r in records if r["customer_id"] == customer_id]
    return records
