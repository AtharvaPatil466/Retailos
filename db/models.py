import time
import uuid
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base


def _gen_id() -> str:
    return str(uuid.uuid4())


def _now() -> float:
    return time.time()


# ── Users & Auth ──────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="staff")  # owner | manager | staff | cashier
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))
    created_at: Mapped[float] = mapped_column(Float, default=_now)
    last_login: Mapped[Optional[float]] = mapped_column(Float)

    store = relationship("StoreProfile", back_populates="users")


# ── Store / Multi-tenant ──────────────────────────────────

class StoreProfile(Base):
    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    store_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    address: Mapped[Optional[str]] = mapped_column(Text)
    gstin: Mapped[Optional[str]] = mapped_column(String(20))
    hours_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON string of operating hours
    holiday_note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, default=_now)

    users = relationship("User", back_populates="store")


# ── Products / Inventory ──────────────────────────────────

class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    sku: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    barcode: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    current_stock: Mapped[int] = mapped_column(Integer, default=0)
    reorder_threshold: Mapped[int] = mapped_column(Integer, default=0)
    daily_sales_rate: Mapped[float] = mapped_column(Float, default=0)
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    cost_price: Mapped[float] = mapped_column(Float, default=0)
    shelf_life_days: Mapped[Optional[int]] = mapped_column(Integer)
    last_restock_date: Mapped[Optional[str]] = mapped_column(String(20))
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[float] = mapped_column(Float, default=_now)

    __table_args__ = (Index("ix_products_category", "category"),)


# ── Customers ─────────────────────────────────────────────

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    customer_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    whatsapp_opted_in: Mapped[bool] = mapped_column(Boolean, default=False)
    last_offer_timestamp: Mapped[Optional[float]] = mapped_column(Float)
    last_offer_category: Mapped[Optional[str]] = mapped_column(String(100))
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))
    created_at: Mapped[float] = mapped_column(Float, default=_now)

    purchase_history = relationship("PurchaseHistoryEntry", back_populates="customer", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="customer")
    loyalty_account = relationship("LoyaltyAccount", back_populates="customer", uselist=False)


class PurchaseHistoryEntry(Base):
    __tablename__ = "purchase_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), index=True)
    product: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[float] = mapped_column(Float, default=0)
    timestamp: Mapped[float] = mapped_column(Float, default=_now)

    customer = relationship("Customer", back_populates="purchase_history")


# ── Suppliers ─────────────────────────────────────────────

class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    supplier_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20))
    whatsapp_number: Mapped[Optional[str]] = mapped_column(String(20))
    products_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON list of product names
    categories_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON list of categories
    price_per_unit: Mapped[float] = mapped_column(Float, default=0)
    reliability_score: Mapped[float] = mapped_column(Float, default=3.0)
    delivery_days: Mapped[int] = mapped_column(Integer, default=7)
    min_order_qty: Mapped[int] = mapped_column(Integer, default=1)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(100))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))
    created_at: Mapped[float] = mapped_column(Float, default=_now)


# ── Orders ────────────────────────────────────────────────

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    order_id: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    customer_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("customers.id"))
    customer_name: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    total_amount: Mapped[float] = mapped_column(Float, default=0)
    gst_amount: Mapped[float] = mapped_column(Float, default=0)
    discount_amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending | confirmed | delivered | cancelled
    payment_method: Mapped[str] = mapped_column(String(30), default="Cash")  # Cash | UPI | Card | Credit
    source: Mapped[str] = mapped_column(String(30), default="counter")  # counter | online | delivery
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))
    timestamp: Mapped[float] = mapped_column(Float, default=_now)

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_orders_timestamp", "timestamp"),
        Index("ix_orders_status", "status"),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id"), index=True)
    sku: Mapped[str] = mapped_column(String(30), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)

    order = relationship("Order", back_populates="items")


# ── Udhaar (Credit) ──────────────────────────────────────

class UdhaarLedger(Base):
    __tablename__ = "udhaar_ledgers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    udhaar_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), index=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    total_credit: Mapped[float] = mapped_column(Float, default=0)
    total_paid: Mapped[float] = mapped_column(Float, default=0)
    balance: Mapped[float] = mapped_column(Float, default=0)
    credit_limit: Mapped[float] = mapped_column(Float, default=5000)
    last_reminder_sent: Mapped[Optional[str]] = mapped_column(String(20))
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))
    created_at: Mapped[str] = mapped_column(String(20), nullable=False)

    entries = relationship("UdhaarEntry", back_populates="ledger", cascade="all, delete-orphan")


class UdhaarEntry(Base):
    __tablename__ = "udhaar_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    ledger_id: Mapped[str] = mapped_column(String(36), ForeignKey("udhaar_ledgers.id"), index=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(30))
    entry_type: Mapped[str] = mapped_column(String(10), nullable=False)  # credit | payment
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    items_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON list of items for credit entries
    note: Mapped[Optional[str]] = mapped_column(Text)
    date: Mapped[str] = mapped_column(String(20), nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, default=_now)

    ledger = relationship("UdhaarLedger", back_populates="entries")


# ── Returns & Refunds ─────────────────────────────────────

class Return(Base):
    __tablename__ = "returns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    return_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(30), nullable=False)
    customer_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("customers.id"))
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    refund_amount: Mapped[float] = mapped_column(Float, default=0)
    refund_method: Mapped[str] = mapped_column(String(30), default="Cash")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | processed | rejected
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))
    timestamp: Mapped[float] = mapped_column(Float, default=_now)
    processed_at: Mapped[Optional[float]] = mapped_column(Float)

    items = relationship("ReturnItem", back_populates="return_record", cascade="all, delete-orphan")


class ReturnItem(Base):
    __tablename__ = "return_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    return_id: Mapped[str] = mapped_column(String(36), ForeignKey("returns.id"), index=True)
    sku: Mapped[str] = mapped_column(String(30), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str] = mapped_column(String(255), default="")
    action: Mapped[str] = mapped_column(String(30), default="refund")  # refund | exchange | wastage

    return_record = relationship("Return", back_populates="items")


# ── Delivery ──────────────────────────────────────────────

class DeliveryRequest(Base):
    __tablename__ = "delivery_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    request_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    customer_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("customers.id"))
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | dispatched | delivered | cancelled
    delivery_slot: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(36))  # staff member id
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))
    requested_at: Mapped[float] = mapped_column(Float, default=_now)
    dispatched_at: Mapped[Optional[float]] = mapped_column(Float)
    delivered_at: Mapped[Optional[float]] = mapped_column(Float)

    items = relationship("DeliveryItem", back_populates="delivery", cascade="all, delete-orphan")


class DeliveryItem(Base):
    __tablename__ = "delivery_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    delivery_id: Mapped[str] = mapped_column(String(36), ForeignKey("delivery_requests.id"), index=True)
    sku: Mapped[str] = mapped_column(String(30), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0)

    delivery = relationship("DeliveryRequest", back_populates="items")


# ── Staff ─────────────────────────────────────────────────

class StaffMember(Base):
    __tablename__ = "staff_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    staff_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(50), default="cashier")  # cashier | floor | delivery | manager
    hourly_rate: Mapped[float] = mapped_column(Float, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))
    joined_at: Mapped[float] = mapped_column(Float, default=_now)

    shifts = relationship("StaffShift", back_populates="staff_member", cascade="all, delete-orphan")
    attendance_records = relationship("AttendanceRecord", back_populates="staff_member", cascade="all, delete-orphan")


class StaffShift(Base):
    __tablename__ = "staff_shifts_v2"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    staff_id: Mapped[str] = mapped_column(String(36), ForeignKey("staff_members.id"), index=True)
    shift_date: Mapped[str] = mapped_column(String(20), nullable=False)
    start_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    end_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled | completed | absent | swapped

    staff_member = relationship("StaffMember", back_populates="shifts")

    __table_args__ = (Index("ix_staff_shifts_date", "shift_date"),)


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    staff_id: Mapped[str] = mapped_column(String(36), ForeignKey("staff_members.id"), index=True)
    date: Mapped[str] = mapped_column(String(20), nullable=False)
    clock_in: Mapped[Optional[float]] = mapped_column(Float)
    clock_out: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="present")  # present | absent | late | half_day
    hours_worked: Mapped[float] = mapped_column(Float, default=0)

    staff_member = relationship("StaffMember", back_populates="attendance_records")

    __table_args__ = (UniqueConstraint("staff_id", "date", name="uq_attendance_staff_date"),)


# ── Shelf Zones ───────────────────────────────────────────

class ShelfZone(Base):
    __tablename__ = "shelf_zones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    zone_id: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    zone_name: Mapped[str] = mapped_column(String(100), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(30), nullable=False)  # high_traffic | standard | refrigerated | freezer
    total_slots: Mapped[int] = mapped_column(Integer, default=10)
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))

    products = relationship("ShelfProduct", back_populates="zone", cascade="all, delete-orphan")


class ShelfProduct(Base):
    __tablename__ = "shelf_products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    zone_id: Mapped[str] = mapped_column(String(36), ForeignKey("shelf_zones.id"), index=True)
    sku: Mapped[str] = mapped_column(String(30), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    shelf_level: Mapped[str] = mapped_column(String(20), default="lower")  # eye_level | upper | lower | bottom
    placed_date: Mapped[Optional[str]] = mapped_column(String(20))
    days_here: Mapped[int] = mapped_column(Integer, default=0)

    zone = relationship("ShelfZone", back_populates="products")


# ── Notifications ─────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # push | sms | email | whatsapp | in_app
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general")  # alert | approval | report | promotion
    priority: Mapped[str] = mapped_column(String(10), default="normal")  # low | normal | high | urgent
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[float] = mapped_column(Float, default=_now)
    read_at: Mapped[Optional[float]] = mapped_column(Float)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (Index("ix_notifications_user_read", "user_id", "is_read"),)


# ── Promotions ────────────────────────────────────────────

class Promotion(Base):
    __tablename__ = "promotions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    promo_code: Mapped[Optional[str]] = mapped_column(String(30), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    promo_type: Mapped[str] = mapped_column(String(30), nullable=False)  # percentage | flat | bogo | bundle | flash_sale
    discount_value: Mapped[float] = mapped_column(Float, default=0)  # percentage or flat amount
    min_order_amount: Mapped[float] = mapped_column(Float, default=0)
    applicable_skus_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON list of SKUs, null = all
    applicable_categories_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON list of categories
    max_uses: Mapped[int] = mapped_column(Integer, default=0)  # 0 = unlimited
    current_uses: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[float] = mapped_column(Float, nullable=False)
    ends_at: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))
    created_at: Mapped[float] = mapped_column(Float, default=_now)


# ── Loyalty ───────────────────────────────────────────────

class LoyaltyAccount(Base):
    __tablename__ = "loyalty_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), unique=True, index=True)
    points_balance: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_points: Mapped[int] = mapped_column(Integer, default=0)
    tier: Mapped[str] = mapped_column(String(20), default="bronze")  # bronze | silver | gold | platinum
    created_at: Mapped[float] = mapped_column(Float, default=_now)

    customer = relationship("Customer", back_populates="loyalty_account")
    transactions = relationship("LoyaltyTransaction", back_populates="account", cascade="all, delete-orphan")


class LoyaltyTransaction(Base):
    __tablename__ = "loyalty_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("loyalty_accounts.id"), index=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(30))
    points: Mapped[int] = mapped_column(Integer, nullable=False)  # positive = earned, negative = redeemed
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, default=_now)

    account = relationship("LoyaltyAccount", back_populates="transactions")


# ── Vendor Purchase Orders ────────────────────────────────

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    po_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | sent | confirmed | received | cancelled
    total_amount: Mapped[float] = mapped_column(Float, default=0)
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid")  # unpaid | partial | paid
    expected_delivery: Mapped[Optional[str]] = mapped_column(String(20))
    actual_delivery: Mapped[Optional[str]] = mapped_column(String(20))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))
    created_at: Mapped[float] = mapped_column(Float, default=_now)

    items = relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan")


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    po_id: Mapped[str] = mapped_column(String(36), ForeignKey("purchase_orders.id"), index=True)
    sku: Mapped[str] = mapped_column(String(30), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)
    received_qty: Mapped[int] = mapped_column(Integer, default=0)

    purchase_order = relationship("PurchaseOrder", back_populates="items")


# ── Audit Log (replacing in-memory/postgres) ─────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_id)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False, default=_now)
    skill: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    store_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("stores.id"))

    __table_args__ = (
        Index("ix_audit_logs_timestamp", "timestamp"),
        Index("ix_audit_logs_skill", "skill"),
        Index("ix_audit_logs_event_type", "event_type"),
    )
