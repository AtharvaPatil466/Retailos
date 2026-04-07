"""Database model tests — CRUD operations, constraints, relationships."""

import pytest
from sqlalchemy import select

from db.models import (
    User,
    StoreProfile,
    Product,
    Customer,
    Order,
    OrderItem,
    UdhaarLedger,
    LoyaltyAccount,
    Notification,
    Promotion,
)
from auth.security import hash_password


@pytest.mark.asyncio
async def test_create_store(db_session):
    store = StoreProfile(
        id="test-store-1",
        store_name="Test Kirana",
        phone="9876543210",
        address="123 Main St",
        gstin="22AAAAA0000A1Z5",
    )
    db_session.add(store)
    await db_session.flush()

    result = await db_session.execute(select(StoreProfile).where(StoreProfile.id == "test-store-1"))
    fetched = result.scalar_one()
    assert fetched.store_name == "Test Kirana"
    assert fetched.gstin == "22AAAAA0000A1Z5"


@pytest.mark.asyncio
async def test_create_user_with_store(db_session):
    store = StoreProfile(id="test-store-2", store_name="User Test Store")
    db_session.add(store)
    await db_session.flush()

    user = User(
        id="test-user-1",
        username="model_test_user",
        email="model@test.com",
        password_hash=hash_password("test123"),
        full_name="Model Tester",
        role="owner",
        store_id="test-store-2",
    )
    db_session.add(user)
    await db_session.flush()

    result = await db_session.execute(select(User).where(User.id == "test-user-1"))
    fetched = result.scalar_one()
    assert fetched.username == "model_test_user"
    assert fetched.role == "owner"
    assert fetched.store_id == "test-store-2"


@pytest.mark.asyncio
async def test_create_product(db_session):
    product = Product(
        id="test-prod-1",
        sku="TEST-SKU-001",
        product_name="Test Rice 5kg",
        category="Staples",
        current_stock=100,
        reorder_threshold=20,
        unit_price=250.0,
        cost_price=200.0,
        barcode="8901234567890",
    )
    db_session.add(product)
    await db_session.flush()

    result = await db_session.execute(select(Product).where(Product.sku == "TEST-SKU-001"))
    fetched = result.scalar_one()
    assert fetched.product_name == "Test Rice 5kg"
    assert fetched.current_stock == 100
    assert fetched.barcode == "8901234567890"


@pytest.mark.asyncio
async def test_create_customer(db_session):
    customer = Customer(
        id="test-cust-1",
        customer_code="CUST-TEST-001",
        name="Raj Kumar",
        phone="9998887770",
    )
    db_session.add(customer)
    await db_session.flush()

    result = await db_session.execute(select(Customer).where(Customer.customer_code == "CUST-TEST-001"))
    fetched = result.scalar_one()
    assert fetched.name == "Raj Kumar"


@pytest.mark.asyncio
async def test_create_order_with_items(db_session):
    customer = Customer(
        id="test-cust-2",
        customer_code="CUST-TEST-002",
        name="Order Customer",
        phone="9998887771",
    )
    db_session.add(customer)
    await db_session.flush()

    order = Order(
        id="test-order-1",
        order_id="ORD-TEST-001",
        customer_id="test-cust-2",
        total_amount=500.0,
        status="pending",
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        id="test-item-1",
        order_id="test-order-1",
        sku="TEST-SKU-001",
        product_name="Test Rice 5kg",
        qty=2,
        unit_price=250.0,
    )
    db_session.add(item)
    await db_session.flush()

    result = await db_session.execute(select(Order).where(Order.order_id == "ORD-TEST-001"))
    fetched = result.scalar_one()
    assert fetched.total_amount == 500.0
    assert fetched.status == "pending"


@pytest.mark.asyncio
async def test_create_udhaar_ledger(db_session):
    ledger = UdhaarLedger(
        id="test-udhaar-1",
        udhaar_id="UDH-TEST-001",
        customer_id="test-cust-1",
        customer_name="Raj Kumar",
        phone="9998887770",
        total_credit=1000.0,
        total_paid=300.0,
        balance=700.0,
        credit_limit=5000.0,
        created_at="2026-04-01",
    )
    db_session.add(ledger)
    await db_session.flush()

    result = await db_session.execute(select(UdhaarLedger).where(UdhaarLedger.udhaar_id == "UDH-TEST-001"))
    fetched = result.scalar_one()
    assert fetched.balance == 700.0
    assert fetched.credit_limit == 5000.0


@pytest.mark.asyncio
async def test_create_loyalty_account(db_session):
    account = LoyaltyAccount(
        id="test-loyalty-1",
        customer_id="test-cust-1",
        points_balance=500,
        lifetime_points=1200,
        tier="silver",
    )
    db_session.add(account)
    await db_session.flush()

    result = await db_session.execute(select(LoyaltyAccount).where(LoyaltyAccount.customer_id == "test-cust-1"))
    fetched = result.scalar_one()
    assert fetched.tier == "silver"
    assert fetched.points_balance == 500
    assert fetched.lifetime_points == 1200


@pytest.mark.asyncio
async def test_create_notification(db_session):
    notif = Notification(
        id="test-notif-1",
        title="Low Stock Alert",
        body="Rice is below reorder threshold",
        channel="in_app",
        priority="high",
    )
    db_session.add(notif)
    await db_session.flush()

    result = await db_session.execute(select(Notification).where(Notification.id == "test-notif-1"))
    fetched = result.scalar_one()
    assert fetched.title == "Low Stock Alert"
    assert fetched.is_read is False


@pytest.mark.asyncio
async def test_create_promotion(db_session):
    promo = Promotion(
        id="test-promo-1",
        title="Summer Sale",
        promo_type="percentage",
        discount_value=10.0,
        min_order_amount=500.0,
        starts_at=1000000.0,
        ends_at=9999999999.0,
        is_active=True,
    )
    db_session.add(promo)
    await db_session.flush()

    result = await db_session.execute(select(Promotion).where(Promotion.id == "test-promo-1"))
    fetched = result.scalar_one()
    assert fetched.title == "Summer Sale"
    assert fetched.discount_value == 10.0


@pytest.mark.asyncio
async def test_user_defaults(db_session):
    user = User(
        username="defaults_user",
        email="defaults@test.com",
        password_hash="fakehash",
        full_name="Defaults",
    )
    db_session.add(user)
    await db_session.flush()

    assert user.role == "staff"
    assert user.is_active is True
    assert user.id is not None
    assert user.created_at is not None


@pytest.mark.asyncio
async def test_product_defaults(db_session):
    product = Product(
        sku="DEF-SKU-001",
        product_name="Default Product",
    )
    db_session.add(product)
    await db_session.flush()

    assert product.current_stock == 0
    assert product.is_active is True
    assert product.category == ""
