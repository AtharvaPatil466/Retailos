"""API integration tests — auth flow, CRUD endpoints, error handling."""

import pytest

from tests.conftest import register_user, auth_header


@pytest.mark.asyncio
async def test_register_user(client):
    resp = await client.post("/api/auth/register", json={
        "username": "api_user1",
        "email": "api_user1@test.com",
        "password": "Pass1234!",
        "full_name": "API User One",
        "role": "owner",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["username"] == "api_user1"
    assert data["user"]["role"] == "owner"


@pytest.mark.asyncio
async def test_register_duplicate_username(client):
    await client.post("/api/auth/register", json={
        "username": "dup_user",
        "email": "dup1@test.com",
        "password": "Pass1234!",
        "full_name": "Dup User",
        "role": "staff",
    })
    resp = await client.post("/api/auth/register", json={
        "username": "dup_user",
        "email": "dup2@test.com",
        "password": "Pass1234!",
        "full_name": "Dup User 2",
        "role": "staff",
    })
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_invalid_role(client):
    resp = await client.post("/api/auth/register", json={
        "username": "bad_role_user",
        "email": "badrole@test.com",
        "password": "Pass1234!",
        "full_name": "Bad Role",
        "role": "superadmin",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_login_success(client):
    await client.post("/api/auth/register", json={
        "username": "login_user",
        "email": "login_user@test.com",
        "password": "MyPass123!",
        "full_name": "Login User",
        "role": "staff",
    })
    resp = await client.post("/api/auth/login", json={
        "username": "login_user",
        "password": "MyPass123!",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/api/auth/register", json={
        "username": "login_wrong",
        "email": "login_wrong@test.com",
        "password": "CorrectPass1!",
        "full_name": "Wrong Pass User",
        "role": "staff",
    })
    resp = await client.post("/api/auth/login", json={
        "username": "login_wrong",
        "password": "WrongPass!",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client):
    resp = await client.post("/api/auth/login", json={
        "username": "ghost_user",
        "password": "whatever",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client):
    reg = await register_user(client, "me_user", "staff")
    resp = await client.get("/api/auth/me", headers=auth_header(reg["token"]))
    assert resp.status_code == 200
    assert resp.json()["username"] == "me_user"


@pytest.mark.asyncio
async def test_get_me_no_token(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_ready(client):
    resp = await client.get("/health/ready")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_live(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_webhook_events_list(client):
    resp = await client.get("/api/webhooks/events")
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert "order.created" in events
    assert "stock.low" in events


@pytest.mark.asyncio
async def test_i18n_languages(client):
    resp = await client.get("/api/i18n/languages")
    assert resp.status_code == 200
    codes = [lang["code"] for lang in resp.json()["languages"]]
    assert "en" in codes
    assert "hi" in codes


@pytest.mark.asyncio
async def test_i18n_translations(client):
    resp = await client.get("/api/i18n/translations/hi")
    assert resp.status_code == 200
    translations = resp.json()["translations"]
    assert translations["inventory.title"] == "इन्वेंटरी"


@pytest.mark.asyncio
async def test_i18n_translate_key(client):
    resp = await client.get("/api/i18n/translate", params={"key": "common.yes", "lang": "hi"})
    assert resp.status_code == 200
    assert resp.json()["text"] == "हाँ"


@pytest.mark.asyncio
async def test_plugins_endpoint(client):
    reg = await register_user(client, "plugin_user", "owner")
    resp = await client.get("/api/plugins", headers=auth_header(reg["token"]))
    assert resp.status_code == 200
    assert "plugins" in resp.json()
