"""Tests for WebSocket channel manager."""

import pytest
from unittest.mock import AsyncMock

from api.websocket_manager import ChannelManager


@pytest.fixture
def manager():
    return ChannelManager()


def _mock_ws(accept=True):
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect_default_channels(manager):
    ws = _mock_ws()
    await manager.connect(ws)
    assert manager.connection_count == 1
    # Should subscribe to all channels by default
    assert manager._connections[ws] == manager.CHANNELS


@pytest.mark.asyncio
async def test_connect_specific_channels(manager):
    ws = _mock_ws()
    await manager.connect(ws, channels=["inventory", "sales"])
    assert manager._connections[ws] == {"inventory", "sales"}


@pytest.mark.asyncio
async def test_disconnect(manager):
    ws = _mock_ws()
    await manager.connect(ws)
    assert manager.connection_count == 1
    manager.disconnect(ws)
    assert manager.connection_count == 0


@pytest.mark.asyncio
async def test_subscribe(manager):
    ws = _mock_ws()
    await manager.connect(ws, channels=["inventory"])
    assert "sales" not in manager._connections[ws]
    manager.subscribe(ws, "sales")
    assert "sales" in manager._connections[ws]


@pytest.mark.asyncio
async def test_unsubscribe(manager):
    ws = _mock_ws()
    await manager.connect(ws, channels=["inventory", "sales"])
    manager.unsubscribe(ws, "sales")
    assert "sales" not in manager._connections[ws]
    assert "inventory" in manager._connections[ws]


@pytest.mark.asyncio
async def test_broadcast_reaches_subscribed(manager):
    ws1 = _mock_ws()
    ws2 = _mock_ws()
    await manager.connect(ws1, channels=["inventory"])
    await manager.connect(ws2, channels=["sales"])

    await manager.broadcast("inventory", "stock.updated", {"sku": "RICE"})

    ws1.send_text.assert_called_once()
    ws2.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_skips_unsubscribed(manager):
    ws = _mock_ws()
    await manager.connect(ws, channels=["orders"])

    await manager.broadcast("inventory", "stock.low", {"sku": "OIL"})
    ws.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_disconnects_on_send_error(manager):
    ws = _mock_ws()
    ws.send_text.side_effect = Exception("connection closed")
    await manager.connect(ws)
    assert manager.connection_count == 1

    await manager.broadcast("inventory", "test", {})
    assert manager.connection_count == 0


@pytest.mark.asyncio
async def test_get_stats(manager):
    ws = _mock_ws()
    await manager.connect(ws, channels=["inventory", "orders"])
    stats = manager.get_stats()
    assert stats["active_connections"] == 1
    assert stats["channel_subscribers"]["inventory"] == 1
    assert stats["channel_subscribers"]["orders"] == 1
    assert "inventory" in stats["available_channels"]


@pytest.mark.asyncio
async def test_invalid_channel_ignored(manager):
    ws = _mock_ws()
    await manager.connect(ws, channels=["inventory"])
    manager.subscribe(ws, "nonexistent_channel")
    # Should not add invalid channel
    assert "nonexistent_channel" not in manager._connections[ws]
