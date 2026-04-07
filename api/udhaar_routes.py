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
                "udhaar_id": ledger.udhaar_id,
                "customer_name": ledger.customer_name,
                "phone": ledger.phone,
                "total_credit": ledger.total_credit,
                "total_paid": ledger.total_paid,
                "balance": ledger.balance,
                "credit_limit": ledger.credit_limit,
                "utilization_pct": round(ledger.balance / ledger.credit_limit * 100, 1) if ledger.credit_limit > 0 else 0,
                "last_reminder_sent": ledger.last_reminder_sent,
            }
            for ledger in ledgers
        ],
        "total_outstanding": sum(ledger.balance for ledger in ledgers),
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


# ── Interest & Late Fee Calculation ──

INTEREST_RATE_MONTHLY = 0.02  # 2% per month
LATE_FEE_THRESHOLD_DAYS = 30  # After 30 days, late fee applies
LATE_FEE_FLAT = 50  # Flat ₹50 late fee


class InterestConfig(BaseModel):
    monthly_rate: float = 0.02
    late_fee_threshold_days: int = 30
    late_fee_flat: float = 50


@router.get("/{udhaar_id}/interest")
async def calculate_interest(
    udhaar_id: str,
    user: User = Depends(require_role("staff")),
    db: AsyncSession = Depends(get_db),
):
    """Calculate accrued interest and late fees on an outstanding balance."""
    result = await db.execute(select(UdhaarLedger).where(UdhaarLedger.udhaar_id == udhaar_id))
    ledger = result.scalar_one_or_none()
    if not ledger:
        raise HTTPException(status_code=404, detail="Ledger not found")

    if ledger.balance <= 0:
        return {"udhaar_id": udhaar_id, "balance": 0, "interest": 0, "late_fee": 0, "total_due": 0}

    # Get oldest unpaid credit entry
    entries_result = await db.execute(
        select(UdhaarEntry)
        .where(UdhaarEntry.ledger_id == ledger.id, UdhaarEntry.entry_type == "credit")
        .order_by(UdhaarEntry.timestamp.asc())
    )
    entries = entries_result.scalars().all()

    days_outstanding = 0
    if entries:
        oldest_ts = entries[0].timestamp
        days_outstanding = int((time.time() - oldest_ts) / 86400)

    # Calculate monthly interest
    months = max(0, days_outstanding / 30)
    interest = round(ledger.balance * INTEREST_RATE_MONTHLY * months, 2)

    # Late fee
    late_fee = LATE_FEE_FLAT if days_outstanding > LATE_FEE_THRESHOLD_DAYS else 0

    total_due = round(ledger.balance + interest + late_fee, 2)

    return {
        "udhaar_id": udhaar_id,
        "customer_name": ledger.customer_name,
        "principal_balance": ledger.balance,
        "days_outstanding": days_outstanding,
        "interest_rate": f"{INTEREST_RATE_MONTHLY * 100}% per month",
        "accrued_interest": interest,
        "late_fee": late_fee,
        "total_due": total_due,
    }


@router.post("/{udhaar_id}/apply-interest")
async def apply_interest(
    udhaar_id: str,
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Apply accrued interest and late fees to the ledger balance."""
    result = await db.execute(select(UdhaarLedger).where(UdhaarLedger.udhaar_id == udhaar_id))
    ledger = result.scalar_one_or_none()
    if not ledger:
        raise HTTPException(status_code=404, detail="Ledger not found")

    if ledger.balance <= 0:
        return {"status": "no_balance", "udhaar_id": udhaar_id}

    entries_result = await db.execute(
        select(UdhaarEntry)
        .where(UdhaarEntry.ledger_id == ledger.id, UdhaarEntry.entry_type == "credit")
        .order_by(UdhaarEntry.timestamp.asc())
    )
    entries = entries_result.scalars().all()
    days_outstanding = 0
    if entries:
        days_outstanding = int((time.time() - entries[0].timestamp) / 86400)

    months = max(0, days_outstanding / 30)
    interest = round(ledger.balance * INTEREST_RATE_MONTHLY * months, 2)
    late_fee = LATE_FEE_FLAT if days_outstanding > LATE_FEE_THRESHOLD_DAYS else 0
    total_charges = interest + late_fee

    if total_charges > 0:
        ledger.total_credit += total_charges
        ledger.balance += total_charges

        entry = UdhaarEntry(
            ledger_id=ledger.id,
            entry_type="credit",
            amount=total_charges,
            note=f"Interest: ₹{interest}, Late fee: ₹{late_fee} ({days_outstanding} days outstanding)",
            date=time.strftime("%Y-%m-%d"),
        )
        db.add(entry)
        await db.flush()

    return {
        "udhaar_id": udhaar_id,
        "interest_applied": interest,
        "late_fee_applied": late_fee,
        "new_balance": ledger.balance,
    }


@router.get("/{udhaar_id}/history")
async def get_ledger_history(
    udhaar_id: str,
    user: User = Depends(require_role("staff")),
    db: AsyncSession = Depends(get_db),
):
    """Get full transaction history for a credit ledger."""
    result = await db.execute(select(UdhaarLedger).where(UdhaarLedger.udhaar_id == udhaar_id))
    ledger = result.scalar_one_or_none()
    if not ledger:
        raise HTTPException(status_code=404, detail="Ledger not found")

    entries_result = await db.execute(
        select(UdhaarEntry)
        .where(UdhaarEntry.ledger_id == ledger.id)
        .order_by(UdhaarEntry.timestamp.desc())
    )
    entries = entries_result.scalars().all()

    return {
        "udhaar_id": udhaar_id,
        "customer_name": ledger.customer_name,
        "balance": ledger.balance,
        "credit_limit": ledger.credit_limit,
        "entries": [
            {
                "type": e.entry_type,
                "amount": e.amount,
                "date": e.date,
                "order_id": e.order_id,
                "note": e.note,
                "timestamp": e.timestamp,
            }
            for e in entries
        ],
    }


@router.get("/stats/summary")
async def udhaar_stats(
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    """Get credit management summary statistics."""
    result = await db.execute(select(UdhaarLedger))
    all_ledgers = result.scalars().all()

    total = len(all_ledgers)
    active = [ledger for ledger in all_ledgers if ledger.balance > 0]
    total_outstanding = sum(ledger.balance for ledger in active)
    total_credit = sum(ledger.total_credit for ledger in all_ledgers)
    total_paid = sum(ledger.total_paid for ledger in all_ledgers)
    over_limit = [ledger for ledger in active if ledger.balance > ledger.credit_limit]

    return {
        "total_accounts": total,
        "active_accounts": len(active),
        "total_outstanding": round(total_outstanding, 2),
        "total_credit_issued": round(total_credit, 2),
        "total_paid": round(total_paid, 2),
        "recovery_rate": round(total_paid / total_credit * 100, 1) if total_credit > 0 else 0,
        "accounts_over_limit": len(over_limit),
        "avg_outstanding": round(total_outstanding / len(active), 2) if active else 0,
    }
