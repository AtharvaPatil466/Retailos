"""Enhanced credit management (udhaar): limits, reminders, partial payments, interest."""

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_role
from db.models import UdhaarEntry, UdhaarLedger, User
from db.session import get_db

router = APIRouter(prefix="/api/v2/udhaar", tags=["udhaar"])


class CreditRequest(BaseModel):
    customer_code: str
    customer_name: str
    phone: str
    amount: float
    items_json: str = "[]"
    order_id: str | None = None


class PaymentRequest(BaseModel):
    amount: float
    note: str = ""


class SetLimitRequest(BaseModel):
    credit_limit: float


@router.get("")
async def list_udhaar_ledgers(
    outstanding_only: bool = False,
    user: User = Depends(require_role("staff")),
    db: AsyncSession = Depends(get_db),
):
    query = select(UdhaarLedger).order_by(UdhaarLedger.balance.desc())
    if outstanding_only:
        query = query.where(UdhaarLedger.balance > 0)

    result = await db.execute(query)
    ledgers = result.scalars().all()

    return {
        "ledgers": [
            {
                "udhaar_id": l.udhaar_id,
                "customer_name": l.customer_name,
                "phone": l.phone,
                "total_credit": l.total_credit,
                "total_paid": l.total_paid,
                "balance": l.balance,
                "credit_limit": l.credit_limit,
                "utilization_pct": round(l.balance / l.credit_limit * 100, 1) if l.credit_limit > 0 else 0,
                "last_reminder_sent": l.last_reminder_sent,
            }
            for l in ledgers
        ],
        "total_outstanding": sum(l.balance for l in ledgers),
    }


@router.post("/credit")
async def add_credit(
    body: CreditRequest,
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    # Find or create ledger
    result = await db.execute(
        select(UdhaarLedger).where(UdhaarLedger.phone == body.phone)
    )
    ledger = result.scalar_one_or_none()

    if not ledger:
        ledger = UdhaarLedger(
            udhaar_id=f"UDH-{int(time.time())}",
            customer_id="",
            customer_name=body.customer_name,
            phone=body.phone,
            created_at=time.strftime("%Y-%m-%d"),
        )
        db.add(ledger)
        await db.flush()

    # Check credit limit
    new_balance = ledger.balance + body.amount
    if new_balance > ledger.credit_limit:
        raise HTTPException(
            status_code=400,
            detail=f"Credit limit exceeded. Limit: ₹{ledger.credit_limit}, Current: ₹{ledger.balance}, Requested: ₹{body.amount}",
        )

    ledger.total_credit += body.amount
    ledger.balance = new_balance

    entry = UdhaarEntry(
        ledger_id=ledger.id,
        order_id=body.order_id,
        entry_type="credit",
        amount=body.amount,
        items_json=body.items_json,
        date=time.strftime("%Y-%m-%d"),
    )
    db.add(entry)
    await db.flush()

    return {"udhaar_id": ledger.udhaar_id, "new_balance": ledger.balance, "credit_limit": ledger.credit_limit}


@router.post("/{udhaar_id}/pay")
async def record_payment(
    udhaar_id: str,
    body: PaymentRequest,
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UdhaarLedger).where(UdhaarLedger.udhaar_id == udhaar_id))
    ledger = result.scalar_one_or_none()
    if not ledger:
        raise HTTPException(status_code=404, detail="Ledger not found")

    if body.amount > ledger.balance:
        raise HTTPException(status_code=400, detail=f"Payment ₹{body.amount} exceeds balance ₹{ledger.balance}")

    ledger.total_paid += body.amount
    ledger.balance -= body.amount

    entry = UdhaarEntry(
        ledger_id=ledger.id,
        entry_type="payment",
        amount=body.amount,
        note=body.note,
        date=time.strftime("%Y-%m-%d"),
    )
    db.add(entry)
    await db.flush()

    return {"udhaar_id": udhaar_id, "payment": body.amount, "new_balance": ledger.balance}


@router.put("/{udhaar_id}/limit")
async def set_credit_limit(
    udhaar_id: str,
    body: SetLimitRequest,
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UdhaarLedger).where(UdhaarLedger.udhaar_id == udhaar_id))
    ledger = result.scalar_one_or_none()
    if not ledger:
        raise HTTPException(status_code=404, detail="Ledger not found")

    ledger.credit_limit = body.credit_limit
    await db.flush()
    return {"udhaar_id": udhaar_id, "new_limit": body.credit_limit}


@router.post("/{udhaar_id}/remind")
async def send_reminder(
    udhaar_id: str,
    user: User = Depends(require_role("staff")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UdhaarLedger).where(UdhaarLedger.udhaar_id == udhaar_id))
    ledger = result.scalar_one_or_none()
    if not ledger:
        raise HTTPException(status_code=404, detail="Ledger not found")

    ledger.last_reminder_sent = time.strftime("%Y-%m-%d")
    await db.flush()

    return {
        "status": "reminder_queued",
        "customer": ledger.customer_name,
        "phone": ledger.phone,
        "balance": ledger.balance,
        "message": f"Hi {ledger.customer_name}, you have an outstanding balance of ₹{ledger.balance:.0f} at RetailOS Supermart. Please settle at your convenience.",
    }
