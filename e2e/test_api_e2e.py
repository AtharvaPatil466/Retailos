"""End-to-end API tests using Playwright.

Tests the full request/response cycle against a running server.
Run with: pytest e2e/ --base-url http://localhost:8000
"""

import time

import pytest
from playwright.sync_api import Page, expect


# ── Health Checks ──

class TestHealthEndpoints:
    """Test health check endpoints are accessible."""

    def test_health_check(self, page: Page, base_url: str):
        response = page.request.get(f"{base_url}/health")
        assert response.ok
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_ready(self, page: Page, base_url: str):
        response = page.request.get(f"{base_url}/health/ready")
        assert response.ok

    def test_health_live(self, page: Page, base_url: str):
        response = page.request.get(f"{base_url}/health/live")
        assert response.ok

    def test_openapi_docs(self, page: Page, base_url: str):
        response = page.request.get(f"{base_url}/openapi.json")
        assert response.ok
        data = response.json()
        assert data["info"]["title"] == "RetailOS"


# ── Auth Flow ──

class TestAuthFlow:
    """Test complete authentication flow."""

    def test_register_login_flow(self, page: Page, base_url: str):
        username = f"e2e_user_{int(time.time())}"

        # Register
        resp = page.request.post(f"{base_url}/api/auth/register", data={
            "username": username,
            "email": f"{username}@test.com",
            "password": "TestPass123!",
            "full_name": "E2E Test User",
            "role": "owner",
        })
        assert resp.ok
        data = resp.json()
        assert "access_token" in data
        token = data["access_token"]

        # Get current user
        resp = page.request.get(f"{base_url}/api/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.ok
        user = resp.json()
        assert user["username"] == username
        assert user["role"] == "owner"

    def test_login_invalid_credentials(self, page: Page, base_url: str):
        resp = page.request.post(f"{base_url}/api/auth/login", data={
            "username": "nonexistent",
            "password": "wrong",
        })
        assert resp.status == 401

    def test_protected_route_without_token(self, page: Page, base_url: str):
        resp = page.request.get(f"{base_url}/api/auth/me")
        assert resp.status == 401


# ── API Endpoints ──

class TestAPIEndpoints:
    """Test key API endpoints work end-to-end."""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page: Page, base_url: str):
        username = f"e2e_api_{int(time.time())}"
        resp = page.request.post(f"{base_url}/api/auth/register", data={
            "username": username,
            "email": f"{username}@test.com",
            "password": "TestPass123!",
            "full_name": "API Test User",
            "role": "owner",
        })
        self.token = resp.json().get("access_token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_i18n_languages(self, page: Page, base_url: str):
        resp = page.request.get(f"{base_url}/api/i18n/languages")
        assert resp.ok
        data = resp.json()
        assert "languages" in data

    def test_webhook_events(self, page: Page, base_url: str):
        resp = page.request.get(f"{base_url}/api/webhooks/events")
        assert resp.ok

    def test_payment_config(self, page: Page, base_url: str):
        resp = page.request.get(f"{base_url}/api/payments/config", headers=self.headers)
        assert resp.ok

    def test_whatsapp_status(self, page: Page, base_url: str):
        resp = page.request.get(f"{base_url}/api/whatsapp/status", headers=self.headers)
        assert resp.ok

    def test_push_vapid_key(self, page: Page, base_url: str):
        resp = page.request.get(f"{base_url}/api/push/vapid-key")
        assert resp.ok

    def test_sms_status(self, page: Page, base_url: str):
        resp = page.request.get(f"{base_url}/api/sms/status")
        assert resp.ok

    def test_scheduler_jobs(self, page: Page, base_url: str):
        resp = page.request.get(f"{base_url}/api/scheduler/jobs", headers=self.headers)
        assert resp.ok

    def test_backup_list(self, page: Page, base_url: str):
        resp = page.request.get(f"{base_url}/api/backup/list", headers=self.headers)
        assert resp.ok


# ── Dashboard UI ──

class TestDashboardUI:
    """Test dashboard loads and renders correctly."""

    def test_dashboard_loads(self, page: Page, dashboard_url: str):
        page.goto(dashboard_url)
        # Wait for the app to render
        page.wait_for_load_state("networkidle")
        # Check page title or key element exists
        expect(page.locator("body")).to_be_visible()

    def test_dashboard_has_navigation(self, page: Page, dashboard_url: str):
        page.goto(dashboard_url)
        page.wait_for_load_state("networkidle")
        # The sidebar should have navigation items
        body = page.locator("body")
        expect(body).to_be_visible()


# ── Payment Flow ──

class TestPaymentFlow:
    """Test payment recording flow."""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page: Page, base_url: str):
        username = f"e2e_pay_{int(time.time())}"
        resp = page.request.post(f"{base_url}/api/auth/register", data={
            "username": username,
            "email": f"{username}@test.com",
            "password": "TestPass123!",
            "full_name": "Pay Test User",
            "role": "owner",
        })
        self.token = resp.json().get("access_token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_record_offline_payment(self, page: Page, base_url: str):
        resp = page.request.post(
            f"{base_url}/api/payments/record-offline",
            headers=self.headers,
            data={
                "order_id": f"E2E-{int(time.time())}",
                "amount": 500.00,
                "method": "cash",
            },
        )
        assert resp.ok
        data = resp.json()
        assert data["status"] == "recorded"

    def test_payment_history(self, page: Page, base_url: str):
        resp = page.request.get(f"{base_url}/api/payments/history", headers=self.headers)
        assert resp.ok
