"""Shared test fixtures for integration tests."""

import asyncio
import os

import pytest
import pytest_asyncio

# Force test database
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///data/test_retailos.db"

from db.session import Base, async_session_factory, engine, init_db


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
