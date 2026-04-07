"""Integration tests for promotions, payments, and notification endpoints."""

import time
import pytest

from tests.conftest import register_user, auth_header


@pytest.mark.asyncio
async def test_create_promotion(client):
    reg = await register_user(client, "promo_owner", "owner")
    resp = await client.post("/api/v2/promotions", headers=auth_header(reg["token"]), json={
        "title": "Test Sale 10% Off",
        "promo_type": "percentage",
        "promo_code": "TEST10",
        "discount_value": 10,
        "min_order_amount": 200,
        "starts_at": time.time(),
        "ends_at": time.time() + 86400,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["promo_code"] == "TEST10"
    assert data["status"] == "created"


@pytest.mark.asyncio
async def test_list_promotions(client):
    reg = await register_user(client, "promo_lister", "owner")
    resp = await client.get("/api/v2/promotions", headers=auth_header(reg["token"]))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_combo_deal(client):
    reg = await register_user(client, "combo_owner", "owner")
    resp = await client.post("/api/v2/promotions/combo", headers=auth_header(reg["token"]), json={
        "name": "Rice + Dal Combo",
        "items": [
            {"sku": "RICE-5KG", "qty": 1, "price": 275},
            {"sku": "TOOR-DAL-1KG", "qty": 1, "price": 160},
        ],
        "combo_price": 400,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["savings"] > 0


@pytest.mark.asyncio
async def test_payment_config(client):
    reg = await register_user(client, "pay_user", "owner")
    resp = await client.get("/api/payments/config", headers=auth_header(reg["token"]))
    assert resp.status_code == 200
    data = resp.json()
    assert "razorpay_configured" in data


@pytest.mark.asyncio
async def test_record_offline_payment(client):
    reg = await register_user(client, "pay_cashier", "cashier")
    resp = await client.post("/api/payments/record-offline", headers=auth_header(reg["token"]), json={
        "order_id": "ORD-TEST-001",
        "amount": 750.0,
        "method": "cash",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "recorded"


@pytest.mark.asyncio
async def test_payment_history(client):
    reg = await register_user(client, "pay_history", "owner")
    resp = await client.get("/api/payments/history", headers=auth_header(reg["token"]))
    assert resp.status_code == 200
    assert "payments" in resp.json()


@pytest.mark.asyncio
async def test_push_status(client):
    resp = await client.get("/api/push/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "configured" in data


@pytest.mark.asyncio
async def test_sms_status(client):
    resp = await client.get("/api/sms/status")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_digest_status(client):
    resp = await client.get("/api/digests/status")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_tally_status(client):
    resp = await client.get("/api/tally/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "demo"


@pytest.mark.asyncio
async def test_shelf_audit_status(client):
    resp = await client.get("/api/shelf-audit/status")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_encryption_status(client):
    resp = await client.get("/api/encryption/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["algorithm"] == "Fernet (AES-128-CBC)"


@pytest.mark.asyncio
async def test_compliance_purposes(client):
    resp = await client.get("/api/compliance/purposes")
    assert resp.status_code == 200
    purposes = resp.json()
    assert isinstance(purposes, list)
    assert len(purposes) > 0


@pytest.mark.asyncio
async def test_compliance_retention(client):
    resp = await client.get("/api/compliance/retention")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_version_endpoint(client):
    resp = await client.get("/api/version")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_version"] == "v1"
    assert "v1" in data["supported_versions"]


@pytest.mark.asyncio
async def test_versioned_endpoint_works(client):
    """Test that /api/v1/ prefix works via versioning middleware."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-API-Version") == "v1"


@pytest.mark.asyncio
async def test_legacy_endpoint_deprecation_header(client):
    """Test that legacy /api/ routes include deprecation headers."""
    resp = await client.get("/api/webhooks/events")
    assert resp.status_code == 200
    assert resp.headers.get("Deprecation") == "true"


@pytest.mark.asyncio
async def test_websocket_stats(client):
    resp = await client.get("/api/ws/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "active_connections" in data
    assert "available_channels" in data


@pytest.mark.asyncio
async def test_scheduler_jobs(client):
    reg = await register_user(client, "sched_user", "owner")
    resp = await client.get("/api/scheduler/jobs", headers=auth_header(reg["token"]))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_backup_status(client):
    reg = await register_user(client, "backup_user", "owner")
    resp = await client.get("/api/backup/list", headers=auth_header(reg["token"]))
    assert resp.status_code == 200
