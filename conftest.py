"""Shared fixtures for root-level tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def isolated_brain_db(tmp_path, monkeypatch):
    """Point brain modules at a temp SQLite file for each test."""
    import brain.db as db_mod

    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "brain.db")
    monkeypatch.setattr(db_mod, "_initialized", False)
    return db_mod.DB_PATH


@pytest.fixture
def audit_mock():
    """Async audit logger mock."""
    audit = MagicMock()
    audit.log = AsyncMock()
    return audit


@pytest.fixture
def gemini_client_factory():
    """Build a lightweight mock Gemini client (legacy compat)."""

    def factory(*, text: str | None = None, side_effect=None):
        generate_content = AsyncMock(side_effect=side_effect)
        if side_effect is None:
            generate_content.return_value = SimpleNamespace(text=text or "")
        return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))

    return factory


@pytest.fixture
def mock_llm_factory():
    """Build a mock LLMClient for testing skills/orchestrator."""

    def factory(*, text: str | None = None, side_effect=None):
        mock = MagicMock()
        mock.generate = AsyncMock(side_effect=side_effect, return_value=text or "")
        mock.generate_sync = MagicMock(return_value=text or "")
        mock.get_raw_client = MagicMock(return_value=None)
        return mock

    return factory
