"""Business logic tests — dynamic pricer, webhook dispatch, plugin system."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from brain.dynamic_pricer import get_price_suggestion
from api.webhook_routes import dispatch_webhook_event, _webhooks, SUPPORTED_EVENTS
from plugins.loader import PluginContext, discover_plugins


# ── Dynamic Pricer ──────────────────────────────────────

class TestDynamicPricer:
    def test_unknown_sku_returns_error(self):
        result = get_price_suggestion("NONEXISTENT-SKU-999")
        assert "error" in result

    def test_suggestion_has_required_fields(self):
        # Use a SKU that exists in mock data
        result = get_price_suggestion("ITEM-001")
        if "error" not in result:
            assert "sku" in result
            assert "current_price" in result
            assert "suggested_price" in result
            assert "factors" in result

    def test_suggested_price_has_floor(self):
        """Suggested price should never go below 60% of current (estimated cost)."""
        result = get_price_suggestion("ITEM-001")
        if "error" not in result:
            assert result["suggested_price"] >= result["current_price"] * 0.6


# ── Webhook Dispatch ────────────────────────────────────

class TestWebhookDispatch:
    def setup_method(self):
        _webhooks.clear()

    def teardown_method(self):
        _webhooks.clear()

    @pytest.mark.asyncio
    async def test_dispatch_to_matching_webhook(self):
        _webhooks.append({
            "id": "wh_test1",
            "url": "https://example.com/hook",
            "events": ["order.created"],
            "secret": "",
            "is_active": True,
            "delivery_count": 0,
            "failure_count": 0,
        })

        import httpx
        mock_client = AsyncMock()
        mock_client.post = AsyncMock()
        with patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await dispatch_webhook_event("order.created", {"order_id": "ORD-001"})

            mock_client.post.assert_called_once()
            assert _webhooks[0]["delivery_count"] == 1

    @pytest.mark.asyncio
    async def test_dispatch_skips_non_matching_event(self):
        _webhooks.append({
            "id": "wh_test2",
            "url": "https://example.com/hook",
            "events": ["stock.low"],
            "secret": "",
            "is_active": True,
            "delivery_count": 0,
            "failure_count": 0,
        })

        import httpx
        mock_client = AsyncMock()
        with patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await dispatch_webhook_event("order.created", {"order_id": "ORD-001"})

            mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_skips_inactive_webhook(self):
        _webhooks.append({
            "id": "wh_test3",
            "url": "https://example.com/hook",
            "events": ["order.created"],
            "secret": "",
            "is_active": False,
            "delivery_count": 0,
            "failure_count": 0,
        })

        import httpx
        mock_client = AsyncMock()
        with patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await dispatch_webhook_event("order.created", {})

            mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_increments_failure_on_error(self):
        _webhooks.append({
            "id": "wh_test4",
            "url": "https://bad-url.invalid/hook",
            "events": ["order.created"],
            "secret": "",
            "is_active": True,
            "delivery_count": 0,
            "failure_count": 0,
        })

        import httpx
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        with patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await dispatch_webhook_event("order.created", {})

            assert _webhooks[0]["failure_count"] == 1
            assert _webhooks[0]["delivery_count"] == 0

    def test_supported_events_not_empty(self):
        assert len(SUPPORTED_EVENTS) > 10
        assert "order.created" in SUPPORTED_EVENTS
        assert "stock.low" in SUPPORTED_EVENTS
        assert "udhaar.payment" in SUPPORTED_EVENTS


# ── Plugin System ───────────────────────────────────────

class TestPluginSystem:
    def test_plugin_context_event_registration(self):
        ctx = PluginContext(app=MagicMock())
        handler = AsyncMock()
        ctx.on_event("order.created", handler)
        assert "order.created" in ctx._event_handlers

    @pytest.mark.asyncio
    async def test_plugin_context_dispatch_event(self):
        ctx = PluginContext(app=MagicMock())
        handler = AsyncMock()
        ctx.on_event("test.event", handler)

        await ctx.dispatch_event("test.event", {"key": "value"})

        handler.assert_called_once_with("test.event", {"key": "value"})

    @pytest.mark.asyncio
    async def test_plugin_context_dispatch_handles_error(self):
        ctx = PluginContext(app=MagicMock())
        bad_handler = AsyncMock(side_effect=ValueError("plugin error"))
        ctx.on_event("test.event", bad_handler)

        # Should not raise
        await ctx.dispatch_event("test.event", {})

    def test_discover_plugins_returns_list(self):
        result = discover_plugins()
        assert isinstance(result, list)

    def test_loaded_plugins_property(self):
        ctx = PluginContext(app=MagicMock())
        assert ctx.loaded_plugins == []
        ctx._plugins_loaded.append("test_plugin")
        assert ctx.loaded_plugins == ["test_plugin"]
