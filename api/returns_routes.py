"""Returns & refunds system with proper DB-backed workflow."""

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_role
from db.models import Customer, Order, Return, ReturnItem, User
from db.session import get_db

router = APIRouter(prefix="/api/v2/returns", tags=["returns"])


class ReturnItemRequest(BaseModel):
    sku: str
    product_name: str
    qty: int = 1
    unit_price: float = 0
    reason: str = ""
    action: str = "refund"  # refund | exchange | wastage


class CreateReturnRequest(BaseModel):
    order_id: str
    customer_code: str | None = None
    customer_name: str = "Walk-in"
    items: list[ReturnItemRequest]
    refund_method: str = "Cash"


@router.post("")
async def create_return(
    body: CreateReturnRequest,
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    # Look up customer if provided
    customer_db_id = None
    if body.customer_code:
        result = await db.execute(select(Customer).where(Customer.customer_code == body.customer_code))
        cust = result.scalar_one_or_none()
        if cust:
            customer_db_id = cust.id

    refund_amount = sum(item.unit_price * item.qty for item in body.items)
    return_id = f"RET-{int(time.time())}"

    db_return = Return(
        return_id=return_id,
        order_id=body.order_id,
        customer_id=customer_db_id,
        customer_name=body.customer_name,
        refund_amount=refund_amount,
        refund_method=body.refund_method,
        status="pending",
    )
    db.add(db_return)
    await db.flush()

    for item in body.items:
        db.add(ReturnItem(
            return_id=db_return.id,
            sku=item.sku,
            product_name=item.product_name,
            qty=item.qty,
            unit_price=item.unit_price,
            reason=item.reason,
            action=item.action,
        ))

    await db.flush()

    return {
        "return_id": return_id,
        "status": "pending",
        "refund_amount": refund_amount,
        "refund_method": body.refund_method,
        "items_count": len(body.items),
    }


@router.post("/{return_id}/process")
async def process_return(
    return_id: str,
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.return_id == return_id))
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=404, detail="Return not found")
    if ret.status == "processed":
        raise HTTPException(status_code=400, detail="Already processed")

    ret.status = "processed"
    ret.processed_at = time.time()
    await db.flush()

    return {"return_id": return_id, "status": "processed", "refund_amount": ret.refund_amount}


@router.post("/{return_id}/reject")
async def reject_return(
    return_id: str,
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.return_id == return_id))
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=404, detail="Return not found")

    ret.status = "rejected"
    await db.flush()
    return {"return_id": return_id, "status": "rejected"}


@router.get("")
async def list_returns(
    status: str | None = None,
    limit: int = 50,
    user: User = Depends(require_role("staff")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Return).order_by(Return.timestamp.desc())
    if status:
        query = query.where(Return.status == status)

    result = await db.execute(query.limit(limit))
    returns = result.scalars().all()

    output = []
    for r in returns:
        items_result = await db.execute(select(ReturnItem).where(ReturnItem.return_id == r.id))
        items = items_result.scalars().all()
        output.append({
            "return_id": r.return_id,
            "order_id": r.order_id,
            "customer_name": r.customer_name,
            "refund_amount": r.refund_amount,
            "refund_method": r.refund_method,
            "status": r.status,
            "timestamp": r.timestamp,
            "processed_at": r.processed_at,
            "items": [{"sku": i.sku, "product_name": i.product_name, "qty": i.qty, "reason": i.reason, "action": i.action} for i in items],
        })

    return {"returns": output}
