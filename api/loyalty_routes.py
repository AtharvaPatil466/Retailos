"""Loyalty program & customer-facing features: points, tiers, digital receipts, online catalog."""

import json
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user, require_role
from db.models import Customer, LoyaltyAccount, LoyaltyTransaction, Order, OrderItem, Product, User
from db.session import get_db

router = APIRouter(tags=["customer-facing"])

# ── Loyalty Config ──
POINTS_PER_RUPEE = 1  # 1 point per ₹1 spent
TIER_THRESHOLDS = {"bronze": 0, "silver": 500, "gold": 2000, "platinum": 5000}
REDEMPTION_RATE = 100  # 100 points = ₹1 discount


# ── Loyalty Endpoints ──

@router.post("/api/loyalty/enroll/{customer_code}")
async def enroll_customer(
    customer_code: str,
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Customer).where(Customer.customer_code == customer_code))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    existing = await db.execute(select(LoyaltyAccount).where(LoyaltyAccount.customer_id == customer.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Customer already enrolled")

    account = LoyaltyAccount(customer_id=customer.id, points_balance=0, lifetime_points=0, tier="bronze")
    db.add(account)
    await db.flush()

    return {"status": "enrolled", "customer": customer.name, "tier": "bronze", "account_id": account.id}


@router.get("/api/loyalty/{customer_code}")
async def get_loyalty_status(
    customer_code: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Customer).where(Customer.customer_code == customer_code))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    result = await db.execute(select(LoyaltyAccount).where(LoyaltyAccount.customer_id == customer.id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Customer not enrolled in loyalty program")

    # Get recent transactions
    result = await db.execute(
        select(LoyaltyTransaction)
        .where(LoyaltyTransaction.account_id == account.id)
        .order_by(LoyaltyTransaction.timestamp.desc())
        .limit(20)
    )
    transactions = result.scalars().all()

    next_tier = None
    for tier_name, threshold in sorted(TIER_THRESHOLDS.items(), key=lambda x: x[1]):
        if threshold > account.lifetime_points:
            next_tier = {"tier": tier_name, "points_needed": threshold - account.lifetime_points}
            break

    return {
        "customer_name": customer.name,
        "points_balance": account.points_balance,
        "lifetime_points": account.lifetime_points,
        "tier": account.tier,
        "next_tier": next_tier,
        "recent_transactions": [
            {"points": t.points, "description": t.description, "timestamp": t.timestamp, "order_id": t.order_id}
            for t in transactions
        ],
    }


@router.post("/api/loyalty/{customer_code}/earn")
async def earn_points(
    customer_code: str,
    order_id: str,
    amount: float,
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Customer).where(Customer.customer_code == customer_code))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    result = await db.execute(select(LoyaltyAccount).where(LoyaltyAccount.customer_id == customer.id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Not enrolled in loyalty program")

    points = int(amount * POINTS_PER_RUPEE)
    account.points_balance += points
    account.lifetime_points += points

    # Update tier
    for tier_name, threshold in sorted(TIER_THRESHOLDS.items(), key=lambda x: x[1], reverse=True):
        if account.lifetime_points >= threshold:
            account.tier = tier_name
            break

    tx = LoyaltyTransaction(
        account_id=account.id, order_id=order_id, points=points,
        description=f"Earned {points} points on order {order_id} (₹{amount:.0f})",
    )
    db.add(tx)
    await db.flush()

    return {"points_earned": points, "new_balance": account.points_balance, "tier": account.tier}


@router.post("/api/loyalty/{customer_code}/redeem")
async def redeem_points(
    customer_code: str,
    points: int,
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    if points <= 0:
        raise HTTPException(status_code=400, detail="Points must be positive")

    result = await db.execute(select(Customer).where(Customer.customer_code == customer_code))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    result = await db.execute(select(LoyaltyAccount).where(LoyaltyAccount.customer_id == customer.id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Not enrolled")

    if account.points_balance < points:
        raise HTTPException(status_code=400, detail=f"Insufficient points. Balance: {account.points_balance}")

    discount = points / REDEMPTION_RATE
    account.points_balance -= points

    tx = LoyaltyTransaction(
        account_id=account.id, points=-points,
        description=f"Redeemed {points} points for ₹{discount:.2f} discount",
    )
    db.add(tx)
    await db.flush()

    return {"points_redeemed": points, "discount_amount": discount, "remaining_balance": account.points_balance}


# ── Digital Receipts ──

@router.get("/api/receipts/{order_id}")
async def get_digital_receipt(
    order_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.order_id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    items = result.scalars().all()

    from datetime import datetime
    return {
        "receipt": {
            "store_name": "RetailOS Supermart",
            "store_address": "MG Road, Pune",
            "store_phone": "+91 98765 43210",
            "order_id": order.order_id,
            "date": datetime.fromtimestamp(order.timestamp).strftime("%d %b %Y, %I:%M %p"),
            "customer_name": order.customer_name or "Walk-in Customer",
            "items": [
                {"product": i.product_name, "qty": i.qty, "unit_price": i.unit_price, "total": i.total}
                for i in items
            ],
            "subtotal": order.total_amount - order.gst_amount,
            "gst": order.gst_amount,
            "discount": order.discount_amount,
            "total": order.total_amount,
            "payment_method": order.payment_method,
            "loyalty_points_earned": int(order.total_amount * POINTS_PER_RUPEE),
        }
    }


# ── Online Catalog ──

@router.get("/api/catalog")
async def get_catalog(
    category: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Product).where(Product.is_active == True, Product.current_stock > 0)
    if category:
        query = query.where(Product.category == category)

    result = await db.execute(query.order_by(Product.product_name))
    products = result.scalars().all()

    if search:
        search_lower = search.lower()
        products = [p for p in products if search_lower in p.product_name.lower()]

    return {
        "products": [
            {
                "sku": p.sku,
                "product_name": p.product_name,
                "category": p.category,
                "unit_price": p.unit_price,
                "in_stock": p.current_stock > 0,
                "image_url": p.image_url,
            }
            for p in products
        ],
        "total": len(products),
    }


@router.get("/api/catalog/categories")
async def get_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product.category).where(Product.is_active == True).distinct()
    )
    categories = [row[0] for row in result.all() if row[0]]
    return {"categories": sorted(categories)}
