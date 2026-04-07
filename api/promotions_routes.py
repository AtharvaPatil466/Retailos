"""Promotions engine: coupons, flash sales, bundle deals."""

import json
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_role
from db.models import Promotion, User
from db.session import get_db

router = APIRouter(prefix="/api/v2/promotions", tags=["promotions"])


class CreatePromoRequest(BaseModel):
    title: str
    description: str = ""
    promo_type: str  # percentage | flat | bogo | bundle | flash_sale
    promo_code: str | None = None
    discount_value: float = 0
    min_order_amount: float = 0
    applicable_skus: list[str] | None = None
    applicable_categories: list[str] | None = None
    max_uses: int = 0
    starts_at: float
    ends_at: float
    model_config = ConfigDict(json_schema_extra={"examples": [{"title": "Diwali Special 20% Off", "description": "Flat 20% off on all grocery items", "promo_type": "percentage", "promo_code": "DIWALI20", "discount_value": 20, "min_order_amount": 500, "applicable_categories": ["Grocery", "Pulses"], "max_uses": 100, "starts_at": 1730400000, "ends_at": 1731009600}]})


@router.post("")
async def create_promotion(
    body: CreatePromoRequest,
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    if body.promo_code:
        existing = await db.execute(select(Promotion).where(Promotion.promo_code == body.promo_code))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Promo code already exists")

    promo = Promotion(
        promo_code=body.promo_code,
        title=body.title,
        description=body.description,
        promo_type=body.promo_type,
        discount_value=body.discount_value,
        min_order_amount=body.min_order_amount,
        applicable_skus_json=json.dumps(body.applicable_skus) if body.applicable_skus else None,
        applicable_categories_json=json.dumps(body.applicable_categories) if body.applicable_categories else None,
        max_uses=body.max_uses,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        store_id=user.store_id,
    )
    db.add(promo)
    await db.flush()

    return {"id": promo.id, "promo_code": promo.promo_code, "title": promo.title, "status": "created"}


@router.get("")
async def list_promotions(
    active_only: bool = True,
    user: User = Depends(require_role("staff")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Promotion).order_by(Promotion.created_at.desc())
    if active_only:
        now = time.time()
        query = query.where(Promotion.is_active, Promotion.starts_at <= now, Promotion.ends_at >= now)

    result = await db.execute(query)
    promos = result.scalars().all()

    return {
        "promotions": [
            {
                "id": p.id,
                "promo_code": p.promo_code,
                "title": p.title,
                "description": p.description,
                "promo_type": p.promo_type,
                "discount_value": p.discount_value,
                "min_order_amount": p.min_order_amount,
                "max_uses": p.max_uses,
                "current_uses": p.current_uses,
                "starts_at": p.starts_at,
                "ends_at": p.ends_at,
                "is_active": p.is_active,
            }
            for p in promos
        ]
    }


@router.post("/validate/{promo_code}")
async def validate_promo_code(
    promo_code: str,
    order_amount: float = 0,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Promotion).where(Promotion.promo_code == promo_code))
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Invalid promo code")

    now = time.time()
    if not promo.is_active:
        return {"valid": False, "reason": "Promotion is inactive"}
    if now < promo.starts_at:
        return {"valid": False, "reason": "Promotion hasn't started yet"}
    if now > promo.ends_at:
        return {"valid": False, "reason": "Promotion has expired"}
    if promo.max_uses > 0 and promo.current_uses >= promo.max_uses:
        return {"valid": False, "reason": "Promotion usage limit reached"}
    if order_amount < promo.min_order_amount:
        return {"valid": False, "reason": f"Minimum order amount is ₹{promo.min_order_amount}"}

    # Calculate discount
    discount = 0
    if promo.promo_type == "percentage":
        discount = order_amount * (promo.discount_value / 100)
    elif promo.promo_type == "flat":
        discount = promo.discount_value
    elif promo.promo_type == "bogo":
        discount = order_amount * 0.5  # Simplified BOGO

    return {
        "valid": True,
        "promo_code": promo_code,
        "title": promo.title,
        "promo_type": promo.promo_type,
        "discount_amount": round(discount, 2),
    }


@router.post("/{promo_id}/deactivate")
async def deactivate_promotion(
    promo_id: str,
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Promotion).where(Promotion.id == promo_id))
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")

    promo.is_active = False
    await db.flush()
    return {"id": promo_id, "status": "deactivated"}


# ── Combo Deals / Bundle Pricing ──

class ComboDeal(BaseModel):
    title: str
    products: list[dict]  # [{"sku": "SKU-001", "qty": 1}, ...]
    bundle_price: float
    original_price: float = 0
    starts_at: float = 0
    ends_at: float = 0


@router.post("/combo")
async def create_combo_deal(
    body: ComboDeal,
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    """Create a combo/bundle deal with a fixed price for multiple products."""
    savings = body.original_price - body.bundle_price if body.original_price else 0

    promo = Promotion(
        promo_code=f"COMBO-{int(time.time())}",
        title=body.title,
        description=f"Bundle deal: {body.title}. Save ₹{savings:.0f}!",
        promo_type="bundle",
        discount_value=savings,
        applicable_skus_json=json.dumps(body.products),
        starts_at=body.starts_at or time.time(),
        ends_at=body.ends_at or (time.time() + 30 * 86400),
        store_id=user.store_id,
    )
    db.add(promo)
    await db.flush()

    return {
        "promo_code": promo.promo_code,
        "title": body.title,
        "bundle_price": body.bundle_price,
        "original_price": body.original_price,
        "savings": round(savings, 2),
        "savings_pct": round(savings / body.original_price * 100, 1) if body.original_price else 0,
    }


# ── Flash Sales ──

class FlashSale(BaseModel):
    title: str
    discount_pct: float  # e.g., 30 for 30%
    applicable_categories: list[str] = []
    applicable_skus: list[str] = []
    duration_hours: float = 2  # auto-end after N hours


@router.post("/flash-sale")
async def create_flash_sale(
    body: FlashSale,
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Create a time-bound flash sale with automatic start/end."""
    now = time.time()
    end = now + body.duration_hours * 3600

    promo = Promotion(
        promo_code=f"FLASH-{int(now)}",
        title=f"FLASH: {body.title}",
        description=f"{body.discount_pct}% off for {body.duration_hours}h!",
        promo_type="flash_sale",
        discount_value=body.discount_pct,
        applicable_skus_json=json.dumps(body.applicable_skus) if body.applicable_skus else None,
        applicable_categories_json=json.dumps(body.applicable_categories) if body.applicable_categories else None,
        starts_at=now,
        ends_at=end,
        store_id=user.store_id,
    )
    db.add(promo)
    await db.flush()

    return {
        "promo_code": promo.promo_code,
        "title": promo.title,
        "discount_pct": body.discount_pct,
        "starts_at": now,
        "ends_at": end,
        "duration_hours": body.duration_hours,
        "status": "active",
    }


# ── Apply Coupon to Cart ──

class CartItem(BaseModel):
    sku: str
    product_name: str = ""
    category: str = ""
    qty: int = 1
    unit_price: float = 0


class ApplyCouponRequest(BaseModel):
    promo_code: str
    cart_items: list[CartItem]


@router.post("/apply")
async def apply_coupon_to_cart(
    body: ApplyCouponRequest,
    db: AsyncSession = Depends(get_db),
):
    """Apply a coupon/promo code to a shopping cart and calculate discounts."""
    result = await db.execute(select(Promotion).where(Promotion.promo_code == body.promo_code))
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Invalid promo code")

    now = time.time()
    if not promo.is_active or now < promo.starts_at or now > promo.ends_at:
        raise HTTPException(status_code=400, detail="Promo not currently active")
    if promo.max_uses > 0 and promo.current_uses >= promo.max_uses:
        raise HTTPException(status_code=400, detail="Promo usage limit reached")

    cart_total = sum(item.unit_price * item.qty for item in body.cart_items)

    if cart_total < promo.min_order_amount:
        raise HTTPException(status_code=400, detail=f"Minimum order ₹{promo.min_order_amount}")

    # Filter applicable items
    applicable_skus = json.loads(promo.applicable_skus_json) if promo.applicable_skus_json else None
    applicable_cats = json.loads(promo.applicable_categories_json) if promo.applicable_categories_json else None

    applicable_total = 0
    for item in body.cart_items:
        if applicable_skus and item.sku not in [s if isinstance(s, str) else s.get("sku", "") for s in applicable_skus]:
            continue
        if applicable_cats and item.category not in applicable_cats:
            continue
        applicable_total += item.unit_price * item.qty

    if applicable_total == 0:
        applicable_total = cart_total  # Apply to all if no filter

    # Calculate discount
    if promo.promo_type == "percentage" or promo.promo_type == "flash_sale":
        discount = applicable_total * (promo.discount_value / 100)
    elif promo.promo_type == "flat":
        discount = min(promo.discount_value, applicable_total)
    elif promo.promo_type == "bogo":
        cheapest = min((item.unit_price for item in body.cart_items), default=0)
        discount = cheapest
    elif promo.promo_type == "bundle":
        discount = promo.discount_value
    else:
        discount = 0

    # Increment usage
    promo.current_uses += 1
    await db.flush()

    return {
        "promo_code": body.promo_code,
        "promo_type": promo.promo_type,
        "cart_total": round(cart_total, 2),
        "discount": round(discount, 2),
        "final_total": round(cart_total - discount, 2),
        "savings_pct": round(discount / cart_total * 100, 1) if cart_total else 0,
    }


@router.get("/active-flash-sales")
async def list_flash_sales(db: AsyncSession = Depends(get_db)):
    """List currently active flash sales."""
    now = time.time()
    result = await db.execute(
        select(Promotion).where(
            Promotion.promo_type == "flash_sale",
            Promotion.is_active,
            Promotion.starts_at <= now,
            Promotion.ends_at >= now,
        )
    )
    sales = result.scalars().all()
    return {
        "flash_sales": [
            {
                "promo_code": s.promo_code,
                "title": s.title,
                "discount_pct": s.discount_value,
                "ends_at": s.ends_at,
                "time_remaining_mins": round((s.ends_at - now) / 60, 0),
            }
            for s in sales
        ]
    }
