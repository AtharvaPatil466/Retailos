"""Playwright E2E test configuration."""

import pytest


@pytest.fixture(scope="session")
def base_url():
    """Base URL for the RetailOS API server."""
    return "http://localhost:8000"


@pytest.fixture(scope="session")
def dashboard_url():
    """Base URL for the React dashboard."""
    return "http://localhost:5173"
