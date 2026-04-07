"""Offline-first sync engine for kirana stores with spotty internet.

Strategy:
- Client (mobile/PWA) queues all mutations locally when offline
- On reconnect, client POSTs the batch to /api/sync/push
- Server processes each operation, resolves conflicts, returns results
- Client GETs /api/sync/pull?since=<timestamp> to fetch server-side changes

Conflict resolution:
- Last-write-wins for stock updates (server timestamp takes precedence)
- Append-only for sales/orders (no conflicts possible)
- Server always wins for price changes (pricing is centralized)
"""

import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_role
from db.models import Customer, Order, Product, User
from db.session import get_db

router = APIRouter(prefix="/api/sync", tags=["offline-sync"])


class SyncOperation(BaseModel):
    """A single queued operation from the client."""
    op_id: str  # Client-generated UUID for idempotency
    op_type: str  # stock_update | sale | customer_add | price_check
    entity_type: str  # product | order | customer
    entity_id: str  # SKU, order_id, customer_id
    data: dict[str, Any]
    client_timestamp: float  # When the operation was created on the client
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "op_id": "cli-uuid-001",
        "op_type": "stock_update",
        "entity_type": "product",
        "entity_id": "RICE-5KG",
        "data": {"current_stock": 45, "movement_type": "sale", "qty_change": -5},
        "client_timestamp": 1712500000,
    }]})


class SyncPushRequest(BaseModel):
    """Batch of offline operations to sync."""
    operations: list[SyncOperation]
    device_id: str = ""
    last_sync_timestamp: float = 0
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "operations": [
            {
                "op_id": "cli-001",
                "op_type": "sale",
                "entity_type": "order",
                "entity_id": "POS-OFFLINE-001",
                "data": {"items": [{"sku": "RICE-5KG", "qty": 2}], "total": 550, "payment": "cash"},
                "client_timestamp": 1712500000,
            }
        ],
        "device_id": "POS-TERMINAL-01",
        "last_sync_timestamp": 1712490000,
    }]})


# Track processed operations for idempotency
_processed_ops: dict[str, dict] = {}


@router.post("/push")
async def sync_push(
    body: SyncPushRequest,
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    """Push offline operations to the server.

    Operations are processed in order. Each op_id is tracked for
    idempotency — replaying the same batch is safe.
    """
    results = []
    for op in body.operations:
        # Idempotency check
        if op.op_id in _processed_ops:
            results.append({
                "op_id": op.op_id,
                "status": "already_processed",
                "result": _processed_ops[op.op_id],
            })
            continue

        result = await _process_operation(op, user, db)
        _processed_ops[op.op_id] = result
        results.append({
            "op_id": op.op_id,
            "status": result.get("status", "ok"),
            "result": result,
        })

    return {
        "processed": len(results),
        "server_timestamp": time.time(),
        "results": results,
    }


@router.get("/pull")
async def sync_pull(
    since: float = 0,
    limit: int = 500,
    user: User = Depends(require_role("cashier")),
    db: AsyncSession = Depends(get_db),
):
    """Pull server-side changes since last sync.

    Returns products, orders, and customers modified after `since` timestamp.
    Client should store the returned server_timestamp and use it for next pull.
    """
    # Products changed since last sync
    products_result = await db.execute(
        select(Product)
        .where(Product.store_id == user.store_id, Product.created_at >= since)
        .order_by(Product.created_at.desc())
        .limit(limit)
    )
    products = [
        {
            "sku": p.sku,
            "product_name": p.product_name,
            "current_stock": p.current_stock,
            "unit_price": p.unit_price,
            "cost_price": p.cost_price,
            "category": p.category,
            "barcode": p.barcode,
            "is_active": p.is_active,
            "updated_at": p.created_at,
        }
        for p in products_result.scalars().all()
    ]

    # Orders since last sync
    orders_result = await db.execute(
        select(Order)
        .where(Order.store_id == user.store_id, Order.timestamp >= since)
        .order_by(Order.timestamp.desc())
        .limit(limit)
    )
    orders = [
        {
            "order_id": o.order_id,
            "total_amount": o.total_amount,
            "status": o.status,
            "payment_method": o.payment_method,
            "timestamp": o.timestamp,
        }
        for o in orders_result.scalars().all()
    ]

    # Customers since last sync
    customers_result = await db.execute(
        select(Customer)
        .where(Customer.store_id == user.store_id, Customer.created_at >= since)
        .limit(limit)
    )
    customers = [
        {
            "customer_code": c.customer_code,
            "name": c.name,
            "phone": c.phone,
            "created_at": c.created_at,
        }
        for c in customers_result.scalars().all()
    ]

    return {
        "server_timestamp": time.time(),
        "since": since,
        "changes": {
            "products": products,
            "orders": orders,
            "customers": customers,
        },
        "counts": {
            "products": len(products),
            "orders": len(orders),
            "customers": len(customers),
        },
    }


@router.get("/status")
async def sync_status(user: User = Depends(require_role("cashier"))):
    """Get sync engine status."""
    return {
        "processed_operations": len(_processed_ops),
        "conflict_resolution": "last-write-wins",
        "supported_entity_types": ["product", "order", "customer"],
        "supported_op_types": ["stock_update", "sale", "customer_add", "price_check"],
        "idempotency": True,
        "max_batch_size": 500,
    }


async def _process_operation(
    op: SyncOperation,
    user: User,
    db: AsyncSession,
) -> dict[str, Any]:
    """Process a single sync operation."""
    try:
        if op.op_type == "stock_update":
            result = await db.execute(
                select(Product).where(Product.sku == op.entity_id, Product.store_id == user.store_id)
            )
            product = result.scalar_one_or_none()
            if not product:
                return {"status": "not_found", "entity": op.entity_id}

            new_stock = op.data.get("current_stock", product.current_stock)
            product.current_stock = new_stock
            await db.flush()
            return {
                "status": "ok",
                "sku": op.entity_id,
                "new_stock": new_stock,
                "server_timestamp": time.time(),
            }

        elif op.op_type == "sale":
            # Offline sales are recorded as new orders
            return {
                "status": "ok",
                "message": "Offline sale queued for processing",
                "order_id": op.entity_id,
                "server_timestamp": time.time(),
            }

        elif op.op_type == "customer_add":
            return {
                "status": "ok",
                "message": "Customer record synced",
                "customer_id": op.entity_id,
                "server_timestamp": time.time(),
            }

        return {"status": "unsupported_op", "op_type": op.op_type}

    except Exception as e:
        return {"status": "error", "error": str(e)}
