"""Load testing for RetailOS using Locust.

Run with:
    locust -f loadtest/locustfile.py --host http://localhost:8000

Or headless:
    locust -f loadtest/locustfile.py --host http://localhost:8000 \
        --headless -u 50 -r 5 --run-time 60s
"""

import random
import time

from locust import HttpUser, task, between


class RetailOSUser(HttpUser):
    """Simulates a typical RetailOS user (cashier/staff/owner)."""

    wait_time = between(0.5, 2)
    token = None

    def on_start(self):
        """Register and login at session start."""
        username = f"loadtest_{int(time.time())}_{random.randint(1000, 9999)}"
        resp = self.client.post("/api/auth/register", json={
            "username": username,
            "email": f"{username}@loadtest.com",
            "password": "LoadTest123!",
            "full_name": f"Load Tester {username}",
            "role": "owner",
        })
        if resp.status_code == 200:
            self.token = resp.json().get("access_token", "")

    @property
    def auth_headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    # ── Health & Status ──────────────────────────────────

    @task(10)
    def health_check(self):
        self.client.get("/health")

    @task(3)
    def health_ready(self):
        self.client.get("/health/ready")

    # ── Auth ─────────────────────────────────────────────

    @task(5)
    def get_me(self):
        self.client.get("/api/auth/me", headers=self.auth_headers)

    # ── i18n ─────────────────────────────────────────────

    @task(3)
    def list_languages(self):
        self.client.get("/api/i18n/languages")

    @task(3)
    def get_translations(self):
        lang = random.choice(["en", "hi", "mr", "ta"])
        self.client.get(f"/api/i18n/translations/{lang}")

    @task(2)
    def voice_command(self):
        commands = [
            "check stock of rice",
            "show daily report",
            "show low stock",
            "चावल का स्टॉक बताओ",
        ]
        self.client.post("/api/i18n/voice-command", json={
            "text": random.choice(commands),
        })

    # ── Webhooks ─────────────────────────────────────────

    @task(2)
    def list_webhook_events(self):
        self.client.get("/api/webhooks/events")

    # ── Payments ─────────────────────────────────────────

    @task(3)
    def payment_config(self):
        self.client.get("/api/payments/config", headers=self.auth_headers)

    @task(2)
    def payment_history(self):
        self.client.get("/api/payments/history", headers=self.auth_headers)

    @task(1)
    def record_payment(self):
        self.client.post("/api/payments/record-offline", headers=self.auth_headers, json={
            "order_id": f"ORD-LOAD-{random.randint(1, 10000)}",
            "amount": round(random.uniform(50, 5000), 2),
            "method": random.choice(["cash", "upi", "card"]),
        })

    # ── Scheduler ────────────────────────────────────────

    @task(1)
    def list_scheduled_jobs(self):
        self.client.get("/api/scheduler/jobs", headers=self.auth_headers)

    # ── WhatsApp ─────────────────────────────────────────

    @task(1)
    def whatsapp_status(self):
        self.client.get("/api/whatsapp/status", headers=self.auth_headers)

    # ── Plugins ──────────────────────────────────────────

    @task(1)
    def list_plugins(self):
        self.client.get("/api/plugins", headers=self.auth_headers)


class CashierUser(HttpUser):
    """Simulates a cashier doing rapid POS lookups."""

    wait_time = between(0.2, 1)
    token = None

    def on_start(self):
        username = f"cashier_{int(time.time())}_{random.randint(1000, 9999)}"
        resp = self.client.post("/api/auth/register", json={
            "username": username,
            "email": f"{username}@loadtest.com",
            "password": "Cashier123!",
            "full_name": f"Cashier {username}",
            "role": "cashier",
        })
        if resp.status_code == 200:
            self.token = resp.json().get("access_token", "")

    @property
    def auth_headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    @task(10)
    def barcode_search(self):
        queries = ["rice", "dal", "sugar", "oil", "milk", "bread", "tea", "soap"]
        self.client.get(
            f"/api/mobile/barcode/search?q={random.choice(queries)}",
            headers=self.auth_headers,
        )

    @task(5)
    def barcode_lookup(self):
        barcodes = ["8901234567890", "8901030000000", "0000000000000"]
        self.client.get(
            f"/api/mobile/barcode/{random.choice(barcodes)}",
            headers=self.auth_headers,
        )

    @task(3)
    def record_sale(self):
        self.client.post("/api/payments/record-offline", headers=self.auth_headers, json={
            "order_id": f"POS-{random.randint(1, 99999)}",
            "amount": round(random.uniform(10, 2000), 2),
            "method": "cash",
        })
