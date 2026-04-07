"""Cross-store analytics — benchmarking, comparisons, and aggregate insights.

Requires owner role. Compares metrics across stores for multi-tenant deployments.
"""

import time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_role
from db.models import Customer, Order, OrderItem, Product, StoreProfile, User
from db.session import get_db

router = APIRouter(prefix="/api/analytics/cross-store", tags=["analytics"])


@router.get("/summary")
async def cross_store_summary(
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate metrics across all stores the owner has access to."""
    stores_result = await db.execute(select(StoreProfile))
    stores = stores_result.scalars().all()

    store_metrics = []
    for store in stores:
        # Revenue
        revenue_result = await db.execute(
            select(func.sum(Order.total_amount), func.count(Order.id))
            .where(Order.store_id == store.id, Order.status != "cancelled")
        )
        row = revenue_result.one()
        total_revenue = row[0] or 0
        order_count = row[1] or 0

        # Products
        product_count = (await db.execute(
            select(func.count(Product.id)).where(Product.store_id == store.id, Product.is_active.is_(True))
        )).scalar() or 0

        # Customers
        customer_count = (await db.execute(
            select(func.count(Customer.id)).where(Customer.store_id == store.id)
        )).scalar() or 0

        # Staff
        staff_count = (await db.execute(
            select(func.count(User.id)).where(User.store_id == store.id, User.is_active.is_(True))
        )).scalar() or 0

        # Average order value
        avg_order = round(total_revenue / max(order_count, 1), 2)

        store_metrics.append({
            "store_id": store.id,
            "store_name": store.store_name,
            "total_revenue": round(total_revenue, 2),
            "order_count": order_count,
            "avg_order_value": avg_order,
            "product_count": product_count,
            "customer_count": customer_count,
            "staff_count": staff_count,
        })

    # Sort by revenue descending
    store_metrics.sort(key=lambda x: x["total_revenue"], reverse=True)

    # Aggregate totals
    total_revenue = sum(s["total_revenue"] for s in store_metrics)
    total_orders = sum(s["order_count"] for s in store_metrics)

    return {
        "total_stores": len(stores),
        "aggregate": {
            "total_revenue": round(total_revenue, 2),
            "total_orders": total_orders,
            "avg_order_value": round(total_revenue / max(total_orders, 1), 2),
            "total_products": sum(s["product_count"] for s in store_metrics),
            "total_customers": sum(s["customer_count"] for s in store_metrics),
        },
        "stores": store_metrics,
    }


@router.get("/revenue-comparison")
async def revenue_comparison(
    days: int = 30,
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Compare revenue across stores for the last N days."""
    cutoff = time.time() - (days * 86400)

    stores_result = await db.execute(select(StoreProfile))
    stores = {s.id: s.store_name for s in stores_result.scalars().all()}

    comparisons = []
    for store_id, store_name in stores.items():
        result = await db.execute(
            select(func.sum(Order.total_amount), func.count(Order.id))
            .where(
                Order.store_id == store_id,
                Order.timestamp >= cutoff,
                Order.status != "cancelled",
            )
        )
        row = result.one()
        revenue = row[0] or 0
        orders = row[1] or 0

        comparisons.append({
            "store_id": store_id,
            "store_name": store_name,
            "revenue": round(revenue, 2),
            "orders": orders,
            "avg_daily_revenue": round(revenue / max(days, 1), 2),
            "avg_order_value": round(revenue / max(orders, 1), 2),
        })

    comparisons.sort(key=lambda x: x["revenue"], reverse=True)

    return {
        "period_days": days,
        "stores": comparisons,
    }


@router.get("/top-products")
async def top_products_across_stores(
    limit: int = 20,
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Top-selling products across all stores by quantity sold."""
    result = await db.execute(
        select(
            OrderItem.sku,
            OrderItem.product_name,
            func.sum(OrderItem.qty).label("total_qty"),
            func.sum(OrderItem.total).label("total_revenue"),
            func.count(OrderItem.id).label("order_count"),
        )
        .group_by(OrderItem.sku, OrderItem.product_name)
        .order_by(func.sum(OrderItem.qty).desc())
        .limit(limit)
    )
    rows = result.all()

    return {
        "top_products": [
            {
                "sku": r.sku,
                "product_name": r.product_name,
                "total_qty_sold": r.total_qty,
                "total_revenue": round(r.total_revenue, 2),
                "order_count": r.order_count,
            }
            for r in rows
        ],
    }


@router.get("/benchmarks")
async def store_benchmarks(
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Performance benchmarks — identifies best/worst performing stores per metric."""
    stores_result = await db.execute(select(StoreProfile))
    stores = stores_result.scalars().all()

    if not stores:
        return {"message": "No stores found", "benchmarks": {}}

    metrics = {}
    for store in stores:
        rev = (await db.execute(
            select(func.sum(Order.total_amount))
            .where(Order.store_id == store.id, Order.status != "cancelled")
        )).scalar() or 0

        orders = (await db.execute(
            select(func.count(Order.id)).where(Order.store_id == store.id)
        )).scalar() or 0

        customers = (await db.execute(
            select(func.count(Customer.id)).where(Customer.store_id == store.id)
        )).scalar() or 0

        products = (await db.execute(
            select(func.count(Product.id))
            .where(Product.store_id == store.id, Product.is_active.is_(True))
        )).scalar() or 0

        metrics[store.id] = {
            "store_name": store.store_name,
            "revenue": round(rev, 2),
            "orders": orders,
            "customers": customers,
            "products": products,
            "avg_order_value": round(rev / max(orders, 1), 2),
            "revenue_per_customer": round(rev / max(customers, 1), 2),
        }

    def _best_worst(metric_key):
        sorted_stores = sorted(metrics.items(), key=lambda x: x[1][metric_key], reverse=True)
        if not sorted_stores:
            return {}
        best_id, best = sorted_stores[0]
        worst_id, worst = sorted_stores[-1]
        avg_val = sum(m[metric_key] for m in metrics.values()) / len(metrics)
        return {
            "best": {"store": best["store_name"], "value": best[metric_key]},
            "worst": {"store": worst["store_name"], "value": worst[metric_key]},
            "average": round(avg_val, 2),
        }

    return {
        "store_count": len(stores),
        "benchmarks": {
            "revenue": _best_worst("revenue"),
            "order_count": _best_worst("orders"),
            "avg_order_value": _best_worst("avg_order_value"),
            "customer_count": _best_worst("customers"),
            "revenue_per_customer": _best_worst("revenue_per_customer"),
        },
        "all_stores": metrics,
    }
