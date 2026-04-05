"""Multi-store management and cross-store analytics.

Owners can create/manage multiple stores and view aggregated analytics.
All data is tenant-scoped via store_id on the user.
"""

import uuid
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_role, get_store_id
from db.models import (
    User,
    StoreProfile,
    Product,
    Customer,
    Order,
    OrderItem,
    UdhaarLedger,
    StaffMember,
)
from db.session import get_db

router = APIRouter(prefix="/api/stores", tags=["stores"])


# ── Request / Response Models ────────────────────────────

class CreateStoreRequest(BaseModel):
    store_name: str
    phone: str = ""
    address: str = ""
    gstin: str = ""


class UpdateStoreRequest(BaseModel):
    store_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    hours_json: Optional[str] = None
    holiday_note: Optional[str] = None


class AssignUserRequest(BaseModel):
    user_id: str
    store_id: str


# ── Store CRUD ───────────────────────────────────────────

@router.post("")
async def create_store(
    body: CreateStoreRequest,
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new store. Only owners can create stores."""
    store = StoreProfile(
        id=str(uuid.uuid4()),
        store_name=body.store_name,
        phone=body.phone,
        address=body.address,
        gstin=body.gstin,
    )
    db.add(store)

    # If owner has no store, assign them to this one
    if not user.store_id:
        user.store_id = store.id

    await db.commit()
    return {"id": store.id, "store_name": store.store_name, "status": "created"}


@router.get("")
async def list_stores(
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """List all stores. Owners see all; others see only their store."""
    if user.role == "owner":
        result = await db.execute(select(StoreProfile).order_by(StoreProfile.store_name))
        stores = result.scalars().all()
    else:
        if not user.store_id:
            return {"stores": []}
        result = await db.execute(select(StoreProfile).where(StoreProfile.id == user.store_id))
        stores = result.scalars().all()

    return {
        "stores": [
            {
                "id": s.id,
                "store_name": s.store_name,
                "phone": s.phone,
                "address": s.address,
                "gstin": s.gstin,
                "created_at": s.created_at,
            }
            for s in stores
        ]
    }


@router.get("/{store_id}")
async def get_store(
    store_id: str,
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    """Get store details."""
    result = await db.execute(select(StoreProfile).where(StoreProfile.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    # Non-owners can only view their own store
    if user.role != "owner" and user.store_id != store_id:
        raise HTTPException(status_code=403, detail="Access denied to this store")

    # Get counts for this store
    product_count = (
        await db.execute(select(func.count()).where(Product.store_id == store_id))
    ).scalar() or 0
    customer_count = (
        await db.execute(select(func.count()).where(Customer.store_id == store_id))
    ).scalar() or 0
    user_count = (
        await db.execute(select(func.count()).where(User.store_id == store_id, User.is_active == True))
    ).scalar() or 0

    return {
        "id": store.id,
        "store_name": store.store_name,
        "phone": store.phone,
        "address": store.address,
        "gstin": store.gstin,
        "hours_json": store.hours_json,
        "holiday_note": store.holiday_note,
        "created_at": store.created_at,
        "stats": {
            "products": product_count,
            "customers": customer_count,
            "users": user_count,
        },
    }


@router.patch("/{store_id}")
async def update_store(
    store_id: str,
    body: UpdateStoreRequest,
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Update store details. Owner only."""
    result = await db.execute(select(StoreProfile).where(StoreProfile.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(store, field, value)

    await db.commit()
    return {"status": "updated", "store_id": store_id}


@router.post("/assign-user")
async def assign_user_to_store(
    body: AssignUserRequest,
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Assign a user to a specific store. Owner only."""
    # Verify store exists
    store = (await db.execute(select(StoreProfile).where(StoreProfile.id == body.store_id))).scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    # Verify target user exists
    target_user = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_user.store_id = body.store_id
    await db.commit()
    return {
        "status": "assigned",
        "user_id": body.user_id,
        "store_id": body.store_id,
        "store_name": store.store_name,
    }


# ── Cross-Store Analytics ────────────────────────────────

@router.get("/analytics/summary")
async def cross_store_summary(
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated analytics across all stores. Owner only."""
    stores_result = await db.execute(select(StoreProfile).order_by(StoreProfile.store_name))
    stores = stores_result.scalars().all()

    summaries = []
    for store in stores:
        sid = store.id

        product_count = (
            await db.execute(select(func.count()).where(Product.store_id == sid))
        ).scalar() or 0

        customer_count = (
            await db.execute(select(func.count()).where(Customer.store_id == sid))
        ).scalar() or 0

        order_count = (
            await db.execute(select(func.count()).where(Order.store_id == sid))
        ).scalar() or 0

        # Total revenue from orders
        revenue = (
            await db.execute(
                select(func.coalesce(func.sum(Order.total_amount), 0)).where(Order.store_id == sid)
            )
        ).scalar() or 0

        # Outstanding udhaar
        outstanding = (
            await db.execute(
                select(func.coalesce(func.sum(UdhaarLedger.balance), 0)).where(UdhaarLedger.store_id == sid)
            )
        ).scalar() or 0

        # Staff count
        staff_count = (
            await db.execute(select(func.count()).where(User.store_id == sid, User.is_active == True))
        ).scalar() or 0

        summaries.append({
            "store_id": sid,
            "store_name": store.store_name,
            "products": product_count,
            "customers": customer_count,
            "orders": order_count,
            "revenue": round(float(revenue), 2),
            "outstanding_udhaar": round(float(outstanding), 2),
            "staff": staff_count,
        })

    # Totals
    totals = {
        "total_stores": len(stores),
        "total_products": sum(s["products"] for s in summaries),
        "total_customers": sum(s["customers"] for s in summaries),
        "total_orders": sum(s["orders"] for s in summaries),
        "total_revenue": round(sum(s["revenue"] for s in summaries), 2),
        "total_outstanding_udhaar": round(sum(s["outstanding_udhaar"] for s in summaries), 2),
        "total_staff": sum(s["staff"] for s in summaries),
    }

    return {"totals": totals, "stores": summaries}


@router.get("/analytics/compare")
async def compare_stores(
    metric: str = Query("revenue", description="Metric to compare: revenue, orders, customers, products"),
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Compare a specific metric across all stores. Owner only."""
    stores_result = await db.execute(select(StoreProfile).order_by(StoreProfile.store_name))
    stores = stores_result.scalars().all()

    comparisons = []
    for store in stores:
        sid = store.id
        value = 0

        if metric == "revenue":
            value = (
                await db.execute(
                    select(func.coalesce(func.sum(Order.total_amount), 0)).where(Order.store_id == sid)
                )
            ).scalar() or 0
        elif metric == "orders":
            value = (
                await db.execute(select(func.count()).where(Order.store_id == sid))
            ).scalar() or 0
        elif metric == "customers":
            value = (
                await db.execute(select(func.count()).where(Customer.store_id == sid))
            ).scalar() or 0
        elif metric == "products":
            value = (
                await db.execute(select(func.count()).where(Product.store_id == sid))
            ).scalar() or 0
        else:
            raise HTTPException(status_code=400, detail=f"Unknown metric: {metric}")

        comparisons.append({
            "store_id": sid,
            "store_name": store.store_name,
            "metric": metric,
            "value": round(float(value), 2) if isinstance(value, float) else value,
        })

    # Rank by value descending
    comparisons.sort(key=lambda x: x["value"], reverse=True)
    for i, c in enumerate(comparisons, 1):
        c["rank"] = i

    return {"metric": metric, "comparisons": comparisons}


@router.get("/analytics/stock-transfer-opportunities")
async def stock_transfer_opportunities(
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Identify products that are overstocked in one store and understocked in another.
    Useful for multi-store owners to optimize inventory across locations."""
    # Get all products with their stock levels per store
    result = await db.execute(
        select(
            Product.sku,
            Product.product_name,
            Product.store_id,
            Product.current_stock,
            Product.reorder_threshold,
            Product.daily_sales_rate,
        )
        .where(Product.store_id.isnot(None), Product.is_active == True)
        .order_by(Product.sku)
    )
    rows = result.all()

    # Group by SKU
    sku_map: dict[str, list] = {}
    for sku, name, store_id, stock, threshold, rate in rows:
        sku_map.setdefault(sku, []).append({
            "store_id": store_id,
            "product_name": name,
            "current_stock": stock,
            "reorder_threshold": threshold,
            "daily_sales_rate": rate,
        })

    # Get store names
    stores_result = await db.execute(select(StoreProfile.id, StoreProfile.store_name))
    store_names = {sid: sname for sid, sname in stores_result.all()}

    opportunities = []
    for sku, store_entries in sku_map.items():
        if len(store_entries) < 2:
            continue

        # Find stores where understocked and overstocked
        understocked = [e for e in store_entries if e["current_stock"] < e["reorder_threshold"]]
        overstocked = [
            e for e in store_entries
            if e["current_stock"] > e["reorder_threshold"] * 3
        ]

        for under in understocked:
            for over in overstocked:
                if under["store_id"] == over["store_id"]:
                    continue
                transfer_qty = min(
                    over["current_stock"] - over["reorder_threshold"],
                    under["reorder_threshold"] - under["current_stock"],
                )
                if transfer_qty > 0:
                    opportunities.append({
                        "sku": sku,
                        "product_name": under["product_name"],
                        "from_store": store_names.get(over["store_id"], over["store_id"]),
                        "from_store_id": over["store_id"],
                        "from_stock": over["current_stock"],
                        "to_store": store_names.get(under["store_id"], under["store_id"]),
                        "to_store_id": under["store_id"],
                        "to_stock": under["current_stock"],
                        "suggested_transfer_qty": transfer_qty,
                    })

    return {"opportunities": opportunities, "count": len(opportunities)}
