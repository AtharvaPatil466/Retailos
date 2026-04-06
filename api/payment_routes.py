"""Payment API routes — Razorpay UPI, card, wallet integration."""

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth.dependencies import require_role
from db.models import User
from payments.razorpay_client import (
    RazorpayClient,
    record_payment,
    get_payment_records,
)

router = APIRouter(prefix="/api/payments", tags=["payments"])

razorpay = RazorpayClient()


class CreatePaymentOrderRequest(BaseModel):
    amount: float  # Amount in rupees
    order_id: str  # Internal RetailOS order ID
    customer_id: str = ""
    currency: str = "INR"
    notes: dict[str, str] = {}


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    internal_order_id: str = ""
    customer_id: str = ""


class RecordOfflinePaymentRequest(BaseModel):
    order_id: str
    amount: float
    method: str = "cash"  # cash | upi | card | wallet
    customer_id: str = ""
    reference: str = ""


class RefundRequest(BaseModel):
    razorpay_payment_id: str
    amount: Optional[float] = None  # None = full refund, else partial (in rupees)
    reason: str = ""


# ── Payment Flow ─────────────────────────────────────────

@router.get("/config")
async def payment_config(user: User = Depends(require_role("cashier"))):
    """Return Razorpay public key for frontend checkout."""
    return {
        "razorpay_key_id": razorpay.key_id if razorpay.is_configured else "",
        "is_configured": razorpay.is_configured,
        "supported_methods": ["upi", "card", "netbanking", "wallet"],
        "currency": "INR",
    }


@router.post("/create-order")
async def create_payment_order(
    body: CreatePaymentOrderRequest,
    user: User = Depends(require_role("cashier")),
):
    """Create a Razorpay payment order for checkout.

    The frontend uses the returned order_id to open the Razorpay checkout modal.
    """
    if not razorpay.is_configured:
        # Demo mode: return a mock order
        mock_order = {
            "id": f"order_demo_{int(time.time())}",
            "amount": int(body.amount * 100),
            "currency": body.currency,
            "receipt": body.order_id,
            "status": "created",
            "demo_mode": True,
        }
        return mock_order

    try:
        order = await razorpay.create_order(
            amount_paise=int(body.amount * 100),
            currency=body.currency,
            receipt=body.order_id,
            notes=body.notes or {"customer_id": body.customer_id},
        )
        return order
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Payment gateway error: {str(e)}")


@router.post("/verify")
async def verify_payment(
    body: VerifyPaymentRequest,
    user: User = Depends(require_role("cashier")),
):
    """Verify payment signature after Razorpay checkout completes.

    Called by the frontend after the customer completes payment.
    """
    if not razorpay.is_configured:
        # Demo mode: accept all payments
        record = record_payment(
            order_id=body.internal_order_id,
            amount=0,
            method="demo",
            status="captured",
            customer_id=body.customer_id,
            razorpay_payment_id=body.razorpay_payment_id,
            razorpay_order_id=body.razorpay_order_id,
        )
        return {"verified": True, "demo_mode": True, "payment": record}

    is_valid = razorpay.verify_payment_signature(
        body.razorpay_order_id,
        body.razorpay_payment_id,
        body.razorpay_signature,
    )

    if not is_valid:
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    # Fetch payment details
    payment_details = await razorpay.fetch_payment(body.razorpay_payment_id)

    record = record_payment(
        order_id=body.internal_order_id,
        amount=payment_details.get("amount", 0) / 100,
        method=payment_details.get("method", "unknown"),
        status=payment_details.get("status", "captured"),
        customer_id=body.customer_id,
        razorpay_payment_id=body.razorpay_payment_id,
        razorpay_order_id=body.razorpay_order_id,
    )

    return {"verified": True, "payment": record, "details": payment_details}


@router.post("/record-offline")
async def record_offline_payment(
    body: RecordOfflinePaymentRequest,
    user: User = Depends(require_role("cashier")),
):
    """Record a cash/offline UPI payment (no gateway needed)."""
    record = record_payment(
        order_id=body.order_id,
        amount=body.amount,
        method=body.method,
        status="captured",
        customer_id=body.customer_id,
    )
    return {"status": "recorded", "payment": record}


@router.post("/refund")
async def create_refund(
    body: RefundRequest,
    user: User = Depends(require_role("manager")),
):
    """Create a refund (full or partial) via Razorpay."""
    if not razorpay.is_configured:
        return {
            "status": "refunded",
            "demo_mode": True,
            "payment_id": body.razorpay_payment_id,
            "amount": body.amount,
        }

    try:
        amount_paise = int(body.amount * 100) if body.amount else None
        refund = await razorpay.create_refund(
            payment_id=body.razorpay_payment_id,
            amount_paise=amount_paise,
            notes={"reason": body.reason} if body.reason else None,
        )
        return {"status": "refunded", "refund": refund}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Refund failed: {str(e)}")


@router.get("/history")
async def payment_history(
    order_id: str = "",
    customer_id: str = "",
    user: User = Depends(require_role("cashier")),
):
    """Get payment records, optionally filtered by order or customer."""
    records = get_payment_records(order_id=order_id, customer_id=customer_id)
    return {"payments": records, "count": len(records)}


@router.post("/webhook")
async def razorpay_webhook(request: Request):
    """Handle Razorpay webhook events (payment.captured, refund.processed, etc.)."""
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    webhook_secret = __import__("os").environ.get("RAZORPAY_WEBHOOK_SECRET", "")
    if webhook_secret and razorpay.is_configured:
        if not razorpay.verify_webhook_signature(body.decode(), signature, webhook_secret):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    import json
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("event", "")
    payload = event.get("payload", {})

    if event_type == "payment.captured":
        payment = payload.get("payment", {}).get("entity", {})
        record_payment(
            order_id=payment.get("notes", {}).get("order_id", ""),
            amount=payment.get("amount", 0) / 100,
            method=payment.get("method", "unknown"),
            status="captured",
            customer_id=payment.get("notes", {}).get("customer_id", ""),
            razorpay_payment_id=payment.get("id", ""),
            razorpay_order_id=payment.get("order_id", ""),
        )

    return {"status": "ok"}
