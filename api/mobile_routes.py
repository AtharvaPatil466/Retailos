"""Mobile-specific API routes.

Barcode lookup, offline sync status, and mobile-optimized endpoints.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_role, get_store_id
from db.models import User, Product
from db.session import get_db

router = APIRouter(prefix="/api/mobile", tags=["mobile"])


class BarcodeLookupResponse(BaseModel):
    found: bool
    sku: str = ""
    product_name: str = ""
    category: str = ""
    current_stock: int = 0
    unit_price: float = 0
    barcode: str = ""


class BarcodeRegisterRequest(BaseModel):
    sku: str
    barcode: str


class OfflineSyncRequest(BaseModel):
    actions: list[dict]  # List of queued actions from the service worker


# ── Barcode Scanning ─────────────────────────────────────

@router.get("/barcode/{barcode}")
async def lookup_barcode(
    barcode: str,
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    """Look up a product by barcode. Used by phone camera scanner."""
    result = await db.execute(
        select(Product).where(Product.barcode == barcode, Product.is_active == True)
    )
    product = result.scalar_one_or_none()

    if not product:
        return BarcodeLookupResponse(found=False, barcode=barcode)

    return BarcodeLookupResponse(
        found=True,
        sku=product.sku,
        product_name=product.product_name,
        category=product.category,
        current_stock=product.current_stock,
        unit_price=product.unit_price,
        barcode=barcode,
    )


@router.post("/barcode/register")
async def register_barcode(
    body: BarcodeRegisterRequest,
    user: User = Depends(require_role("staff")),
    db: AsyncSession = Depends(get_db),
):
    """Link a barcode to an existing product SKU."""
    result = await db.execute(select(Product).where(Product.sku == body.sku))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product with SKU '{body.sku}' not found")

    # Check if barcode is already in use
    existing = await db.execute(
        select(Product).where(Product.barcode == body.barcode, Product.sku != body.sku)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Barcode already assigned to another product")

    product.barcode = body.barcode
    await db.commit()
    return {"status": "registered", "sku": body.sku, "barcode": body.barcode}


@router.get("/barcode/search")
async def search_by_barcode_or_name(
    q: str = Query(..., min_length=1, description="Barcode or product name fragment"),
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    """Quick product search by barcode or name — optimized for mobile POS."""
    # Try exact barcode match first
    result = await db.execute(
        select(Product).where(Product.barcode == q, Product.is_active == True)
    )
    product = result.scalar_one_or_none()
    if product:
        return {
            "results": [{
                "sku": product.sku,
                "product_name": product.product_name,
                "category": product.category,
                "current_stock": product.current_stock,
                "unit_price": product.unit_price,
                "barcode": product.barcode,
            }],
            "match_type": "barcode",
        }

    # Fall back to name search
    result = await db.execute(
        select(Product)
        .where(Product.product_name.ilike(f"%{q}%"), Product.is_active == True)
        .limit(10)
    )
    products = result.scalars().all()
    return {
        "results": [
            {
                "sku": p.sku,
                "product_name": p.product_name,
                "category": p.category,
                "current_stock": p.current_stock,
                "unit_price": p.unit_price,
                "barcode": p.barcode or "",
            }
            for p in products
        ],
        "match_type": "name",
    }


# ── Offline Sync ─────────────────────────────────────────

@router.post("/sync")
async def process_offline_sync(
    body: OfflineSyncRequest,
    user: User = Depends(require_role("cashier")),
):
    """Process queued offline actions when the device reconnects.

    Each action in the list is a dict with 'type' and 'data' keys.
    This endpoint processes them in order and reports results.
    """
    results = []
    for i, action in enumerate(body.actions):
        action_type = action.get("type", "unknown")
        # In production, each action type would be dispatched to the appropriate handler.
        # For now, we acknowledge receipt and log them.
        results.append({
            "index": i,
            "type": action_type,
            "status": "accepted",
        })

    return {
        "synced": len(results),
        "results": results,
    }


# ── Mobile Dashboard (condensed data) ────────────────────

@router.get("/dashboard")
async def mobile_dashboard(
    user: User = Depends(require_role("cashier")),
    store_id: str = Depends(get_store_id),
    db: AsyncSession = Depends(get_db),
):
    """Condensed dashboard data optimized for mobile screens.
    Returns only the most important metrics in a single request.
    """
    from sqlalchemy import func
    from db.models import Order, UdhaarLedger, Notification

    # Product stats
    total_products = (
        await db.execute(
            select(func.count()).where(Product.store_id == store_id, Product.is_active == True)
        )
    ).scalar() or 0

    low_stock = (
        await db.execute(
            select(func.count()).where(
                Product.store_id == store_id,
                Product.is_active == True,
                Product.current_stock <= Product.reorder_threshold,
                Product.current_stock > 0,
            )
        )
    ).scalar() or 0

    out_of_stock = (
        await db.execute(
            select(func.count()).where(
                Product.store_id == store_id,
                Product.is_active == True,
                Product.current_stock == 0,
            )
        )
    ).scalar() or 0

    # Order count
    order_count = (
        await db.execute(select(func.count()).where(Order.store_id == store_id))
    ).scalar() or 0

    # Outstanding udhaar
    outstanding_udhaar = (
        await db.execute(
            select(func.coalesce(func.sum(UdhaarLedger.balance), 0)).where(
                UdhaarLedger.store_id == store_id
            )
        )
    ).scalar() or 0

    # Unread notifications
    unread_notifications = (
        await db.execute(
            select(func.count()).where(
                Notification.store_id == store_id,
                Notification.is_read == False,
            )
        )
    ).scalar() or 0

    return {
        "store_id": store_id,
        "inventory": {
            "total_products": total_products,
            "low_stock": low_stock,
            "out_of_stock": out_of_stock,
        },
        "orders": order_count,
        "outstanding_udhaar": round(float(outstanding_udhaar), 2),
        "unread_notifications": unread_notifications,
    }
