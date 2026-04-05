"""Seed the SQLAlchemy database from existing JSON fixture files.

Run once to migrate mock data into the new DB layer.
Usage:  python -m db.seed
"""

import asyncio
import json
from pathlib import Path

from db.session import async_session_factory, init_db
from db.models import (
    Customer,
    DeliveryItem,
    DeliveryRequest,
    Order,
    OrderItem,
    Product,
    PurchaseHistoryEntry,
    Return,
    ReturnItem,
    ShelfProduct,
    ShelfZone,
    StoreProfile,
    Supplier,
    UdhaarEntry,
    UdhaarLedger,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(filename: str, default=None):
    try:
        with open(DATA_DIR / filename) as f:
            return json.load(f)
    except FileNotFoundError:
        return default if default is not None else []


async def seed():
    await init_db()

    async with async_session_factory() as session:
        # ── Store ──
        store = StoreProfile(
            id="store-001",
            store_name="RetailOS Supermart",
            phone="+91 98765 43210",
            address="MG Road, Pune",
            hours_json=json.dumps({
                "monday": "8:00 AM - 10:00 PM",
                "tuesday": "8:00 AM - 10:00 PM",
                "wednesday": "8:00 AM - 10:00 PM",
                "thursday": "8:00 AM - 10:00 PM",
                "friday": "8:00 AM - 10:30 PM",
                "saturday": "8:00 AM - 10:30 PM",
                "sunday": "9:00 AM - 9:00 PM",
            }),
            holiday_note="Holiday timings may vary on major festivals.",
        )
        session.add(store)

        # ── Products ──
        products = _load("mock_inventory.json", [])
        for p in products:
            session.add(Product(
                sku=p["sku"],
                product_name=p["product_name"],
                category=p.get("category", ""),
                image_url=p.get("image_url"),
                barcode=p.get("barcode"),
                current_stock=p.get("current_stock", 0),
                reorder_threshold=p.get("reorder_threshold", 0),
                daily_sales_rate=p.get("daily_sales_rate", 0),
                unit_price=p.get("unit_price", 0),
                last_restock_date=p.get("last_restock_date"),
                store_id="store-001",
            ))

        # ── Customers ──
        customers = _load("mock_customers.json", [])
        cust_id_map = {}
        for c in customers:
            cid = c.get("customer_id", c.get("id", ""))
            db_cust = Customer(
                customer_code=cid,
                name=c["name"],
                phone=c["phone"],
                whatsapp_opted_in=c.get("whatsapp_opted_in", False),
                last_offer_timestamp=c.get("last_offer_timestamp"),
                last_offer_category=c.get("last_offer_category"),
                store_id="store-001",
            )
            session.add(db_cust)
            await session.flush()
            cust_id_map[cid] = db_cust.id

            for ph in c.get("purchase_history", []):
                session.add(PurchaseHistoryEntry(
                    customer_id=db_cust.id,
                    product=ph.get("product", ""),
                    category=ph.get("category", ""),
                    quantity=ph.get("quantity", 1),
                    price=ph.get("price", 0),
                    timestamp=ph.get("timestamp", 0),
                ))

        # ── Suppliers ──
        for s in _load("mock_suppliers.json", []):
            session.add(Supplier(
                supplier_id=s["supplier_id"],
                supplier_name=s["supplier_name"],
                contact_phone=s.get("contact_phone"),
                products_json=json.dumps(s.get("products", [])),
                categories_json=json.dumps(s.get("categories", [])),
                price_per_unit=s.get("price_per_unit", 0),
                reliability_score=s.get("reliability_score", 3.0),
                delivery_days=s.get("delivery_days", 7),
                min_order_qty=s.get("min_order_qty", 1),
                payment_terms=s.get("payment_terms"),
                location=s.get("location"),
                store_id="store-001",
            ))

        # ── Orders ──
        orders_data = _load("mock_orders.json", {"customer_orders": []})
        for o in orders_data.get("customer_orders", []):
            cust_db_id = cust_id_map.get(o.get("customer_id"))
            db_order = Order(
                order_id=o["order_id"],
                customer_id=cust_db_id,
                customer_name=o.get("customer_name"),
                phone=o.get("phone"),
                total_amount=o.get("total_amount", 0),
                gst_amount=o.get("gst_amount", 0),
                status=o.get("status", "delivered"),
                payment_method=o.get("payment_method", "Cash"),
                source=o.get("source", "counter"),
                store_id="store-001",
                timestamp=o.get("timestamp", 0),
            )
            session.add(db_order)
            await session.flush()

            for item in o.get("items", []):
                session.add(OrderItem(
                    order_id=db_order.id,
                    sku=item.get("sku", ""),
                    product_name=item.get("product_name", ""),
                    qty=item.get("qty", 1),
                    unit_price=item.get("unit_price", 0),
                    total=item.get("total", 0),
                ))

        # ── Udhaar ──
        for u in _load("mock_udhaar.json", []):
            cust_db_id = cust_id_map.get(u.get("customer_id"))
            ledger = UdhaarLedger(
                udhaar_id=u["udhaar_id"],
                customer_id=cust_db_id or "",
                customer_name=u["customer_name"],
                phone=u["phone"],
                total_credit=u.get("total_credit", 0),
                total_paid=u.get("total_paid", 0),
                balance=u.get("balance", 0),
                last_reminder_sent=u.get("last_reminder_sent"),
                store_id="store-001",
                created_at=u.get("created_at", ""),
            )
            session.add(ledger)
            await session.flush()

            for entry in u.get("entries", []):
                session.add(UdhaarEntry(
                    ledger_id=ledger.id,
                    order_id=entry.get("order_id"),
                    entry_type=entry.get("type", "credit"),
                    amount=entry.get("amount", 0),
                    items_json=json.dumps(entry.get("items", [])),
                    note=entry.get("note"),
                    date=entry.get("date", ""),
                ))

        # ── Returns ──
        for r in _load("mock_returns.json", []):
            cust_db_id = cust_id_map.get(r.get("customer_id"))
            db_return = Return(
                return_id=r["return_id"],
                order_id=r["order_id"],
                customer_id=cust_db_id,
                customer_name=r["customer_name"],
                refund_amount=r.get("refund_amount", 0),
                refund_method=r.get("refund_method", "Cash"),
                status=r.get("status", "processed"),
                timestamp=r.get("timestamp", 0),
                processed_at=r.get("processed_at"),
            )
            session.add(db_return)
            await session.flush()

            for item in r.get("items", []):
                session.add(ReturnItem(
                    return_id=db_return.id,
                    sku=item.get("sku", ""),
                    product_name=item.get("product_name", ""),
                    qty=item.get("qty", 1),
                    unit_price=item.get("unit_price", 0),
                    reason=item.get("reason", ""),
                    action=item.get("action", "refund"),
                ))

        # ── Delivery Requests ──
        for d in _load("mock_delivery_requests.json", []):
            cust_db_id = cust_id_map.get(d.get("customer_id"))
            db_del = DeliveryRequest(
                request_id=d["request_id"],
                customer_id=cust_db_id,
                customer_name=d["customer_name"],
                phone=d["phone"],
                address=d["address"],
                total_amount=d.get("total_amount", 0),
                status=d.get("status", "pending"),
                delivery_slot=d.get("delivery_slot"),
                notes=d.get("notes"),
                store_id="store-001",
                requested_at=d.get("requested_at", 0),
            )
            session.add(db_del)
            await session.flush()

            for item in d.get("items", []):
                session.add(DeliveryItem(
                    delivery_id=db_del.id,
                    sku=item.get("sku", ""),
                    product_name=item.get("product_name", ""),
                    qty=item.get("qty", 1),
                    unit_price=item.get("unit_price", 0),
                ))

        # ── Shelf Zones ──
        shelf_data = _load("mock_shelf_zones.json", {"zones": []})
        for z in shelf_data.get("zones", []):
            db_zone = ShelfZone(
                zone_id=z["zone_id"],
                zone_name=z["zone_name"],
                zone_type=z["zone_type"],
                total_slots=z.get("total_slots", 10),
                store_id="store-001",
            )
            session.add(db_zone)
            await session.flush()

            for p in z.get("products", []):
                session.add(ShelfProduct(
                    zone_id=db_zone.id,
                    sku=p["sku"],
                    product_name=p["product_name"],
                    shelf_level=p.get("shelf_level", "lower"),
                    placed_date=p.get("placed_date"),
                    days_here=p.get("days_here", 0),
                ))

        await session.commit()
        print("[seed] Database seeded successfully from JSON fixtures.")


if __name__ == "__main__":
    asyncio.run(seed())
