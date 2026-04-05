"""Promotions engine: coupons, flash sales, bundle deals."""

import json
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
        query = query.where(Promotion.is_active == True, Promotion.starts_at <= now, Promotion.ends_at >= now)

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
