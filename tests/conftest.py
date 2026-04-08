"""Shared test fixtures for integration tests."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Force test database before any app imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///data/test_retailos.db"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"

from db.session import Base, async_session_factory, engine
from api.routes import create_app


def _make_mock_orchestrator():
    """Create a minimal mock orchestrator for testing."""
    orch = MagicMock()
    orch.skills = {}
    orch.audit = MagicMock()
    orch.audit.on_log = None
    orch.audit.log = AsyncMock()
    orch.memory = MagicMock()
    return orch


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def setup_db():
    """Create all tables for the test session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(setup_db):
    """Provide a clean DB session per test."""
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="session")
async def app(setup_db):
    """Create the FastAPI app with a mock orchestrator."""
    orch = _make_mock_orchestrator()
    application = create_app(orch)
    return application


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def authed_client(app):
    """Async HTTP client with owner-level auth token pre-set."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/auth/register", json={
            "username": "authed_fixture_user",
            "email": "authed_fixture@test.com",
            "password": "TestPass123!",
            "full_name": "Authed Fixture",
            "role": "owner",
        })
        token = resp.json().get("access_token", "")
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac


async def register_user(client: AsyncClient, username="testuser", role="owner") -> dict:
    """Helper: register a user and return {"token": ..., "user": ...}."""
    resp = await client.post("/api/auth/register", json={
        "username": username,
        "email": f"{username}@test.com",
        "password": "TestPass123!",
        "full_name": f"Test {username.title()}",
        "role": role,
    })
    data = resp.json()
    return {"token": data.get("access_token", ""), "user": data.get("user", {}), "status": resp.status_code}


def auth_header(token: str) -> dict:
    """Helper: build Authorization header."""
    return {"Authorization": f"Bearer {token}"}
