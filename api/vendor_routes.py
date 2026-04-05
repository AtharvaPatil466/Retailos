"""Vendor portal: supplier self-service, digital purchase orders."""

import json
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_role
from db.models import PurchaseOrder, PurchaseOrderItem, Supplier, User
from db.session import get_db

router = APIRouter(prefix="/api/v2/vendor", tags=["vendor-portal"])


# ── Purchase Orders ──

class POItemRequest(BaseModel):
    sku: str
    product_name: str
    qty: int
    unit_price: float


class CreatePORequest(BaseModel):
    supplier_code: str
    items: list[POItemRequest]
    expected_delivery: str | None = None
    notes: str = ""


@router.post("/purchase-orders")
async def create_purchase_order(
    body: CreatePORequest,
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Supplier).where(Supplier.supplier_id == body.supplier_code))
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    po_number = f"PO-{int(time.time())}"
    total = sum(item.qty * item.unit_price for item in body.items)

    po = PurchaseOrder(
        po_number=po_number,
        supplier_id=supplier.id,
        status="draft",
        total_amount=total,
        expected_delivery=body.expected_delivery,
        notes=body.notes,
        store_id=user.store_id,
    )
    db.add(po)
    await db.flush()

    for item in body.items:
        db.add(PurchaseOrderItem(
            po_id=po.id,
            sku=item.sku,
            product_name=item.product_name,
            qty=item.qty,
            unit_price=item.unit_price,
            total=item.qty * item.unit_price,
        ))

    await db.flush()
    return {"po_number": po_number, "status": "draft", "total_amount": total, "supplier": supplier.supplier_name}


@router.post("/purchase-orders/{po_number}/send")
async def send_purchase_order(
    po_number: str,
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    po.status = "sent"
    await db.flush()
    return {"po_number": po_number, "status": "sent"}


@router.post("/purchase-orders/{po_number}/confirm")
async def confirm_purchase_order(
    po_number: str,
    db: AsyncSession = Depends(get_db),
):
    """Supplier confirms they will fulfill the PO."""
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    po.status = "confirmed"
    await db.flush()
    return {"po_number": po_number, "status": "confirmed"}


@router.post("/purchase-orders/{po_number}/receive")
async def receive_purchase_order(
    po_number: str,
    user: User = Depends(require_role("staff")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")

    po.status = "received"
    po.actual_delivery = time.strftime("%Y-%m-%d")
    po.payment_status = "unpaid"

    # Mark all items as received
    items_result = await db.execute(select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id))
    for item in items_result.scalars().all():
        item.received_qty = item.qty

    await db.flush()
    return {"po_number": po_number, "status": "received"}


@router.post("/purchase-orders/{po_number}/pay")
async def pay_purchase_order(
    po_number: str,
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    po.payment_status = "paid"
    await db.flush()
    return {"po_number": po_number, "payment_status": "paid"}


@router.get("/purchase-orders")
async def list_purchase_orders(
    status: str | None = None,
    limit: int = 50,
    user: User = Depends(require_role("staff")),
    db: AsyncSession = Depends(get_db),
):
    query = select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
    if status:
        query = query.where(PurchaseOrder.status == status)

    result = await db.execute(query.limit(limit))
    pos = result.scalars().all()

    output = []
    for po in pos:
        items_result = await db.execute(select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id))
        items = items_result.scalars().all()

        supplier_result = await db.execute(select(Supplier).where(Supplier.id == po.supplier_id))
        supplier = supplier_result.scalar_one_or_none()

        output.append({
            "po_number": po.po_number,
            "supplier_name": supplier.supplier_name if supplier else "Unknown",
            "status": po.status,
            "payment_status": po.payment_status,
            "total_amount": po.total_amount,
            "expected_delivery": po.expected_delivery,
            "actual_delivery": po.actual_delivery,
            "created_at": po.created_at,
            "items": [{"sku": i.sku, "product_name": i.product_name, "qty": i.qty, "unit_price": i.unit_price, "received_qty": i.received_qty} for i in items],
        })

    return {"purchase_orders": output}


# ── Supplier Self-Service ──

@router.get("/suppliers/{supplier_code}/profile")
async def get_supplier_profile(
    supplier_code: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Supplier).where(Supplier.supplier_id == supplier_code))
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    return {
        "supplier_id": supplier.supplier_id,
        "supplier_name": supplier.supplier_name,
        "contact_phone": supplier.contact_phone,
        "products": json.loads(supplier.products_json) if supplier.products_json else [],
        "categories": json.loads(supplier.categories_json) if supplier.categories_json else [],
        "price_per_unit": supplier.price_per_unit,
        "delivery_days": supplier.delivery_days,
        "min_order_qty": supplier.min_order_qty,
        "payment_terms": supplier.payment_terms,
        "location": supplier.location,
    }


class SupplierUpdateRequest(BaseModel):
    price_per_unit: float | None = None
    delivery_days: int | None = None
    min_order_qty: int | None = None
    contact_phone: str | None = None


@router.patch("/suppliers/{supplier_code}/profile")
async def update_supplier_profile(
    supplier_code: str,
    body: SupplierUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Supplier self-service: update their own pricing and delivery terms."""
    result = await db.execute(select(Supplier).where(Supplier.supplier_id == supplier_code))
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    if body.price_per_unit is not None:
        supplier.price_per_unit = body.price_per_unit
    if body.delivery_days is not None:
        supplier.delivery_days = body.delivery_days
    if body.min_order_qty is not None:
        supplier.min_order_qty = body.min_order_qty
    if body.contact_phone is not None:
        supplier.contact_phone = body.contact_phone

    await db.flush()
    return {"status": "updated", "supplier_id": supplier_code}
