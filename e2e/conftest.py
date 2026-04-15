"""Playwright E2E test configuration."""

import os

import pytest


@pytest.fixture(scope="session")
def base_url():
    """Base URL for the RetailOS API server."""
    return os.environ.get("RETAILOS_E2E_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def dashboard_url():
    """Base URL for the React dashboard."""
    return os.environ.get("RETAILOS_E2E_DASHBOARD_URL", "http://localhost:5173")
