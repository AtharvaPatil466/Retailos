"""Enhanced WebSocket manager with channel-based subscriptions.

Supports real-time dashboard updates across multiple channels:
- inventory: stock changes, low-stock alerts, expiry warnings
- orders: new orders, status changes, returns
- sales: live sale events, revenue updates
- alerts: system alerts, audit events, threshold breaches
- notifications: push/SMS/email delivery status
"""

import asyncio
import json
import time
from typing import Any

from fastapi import WebSocket


class ChannelManager:
    """WebSocket connection manager with channel subscriptions."""

    def __init__(self):
        self._connections: dict[WebSocket, set[str]] = {}
        self._channel_stats: dict[str, int] = {}

    # Available channels
    CHANNELS = {
        "inventory", "orders", "sales", "alerts",
        "notifications", "audit", "system",
    }

    async def connect(self, websocket: WebSocket, channels: list[str] | None = None):
        """Accept a WebSocket and subscribe to channels."""
        await websocket.accept()
        subscribed = set(channels or self.CHANNELS) & self.CHANNELS
        if not subscribed:
            subscribed = self.CHANNELS.copy()
        self._connections[websocket] = subscribed

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self._connections.pop(websocket, None)

    def subscribe(self, websocket: WebSocket, channel: str):
        """Subscribe a connection to an additional channel."""
        if websocket in self._connections and channel in self.CHANNELS:
            self._connections[websocket].add(channel)

    def unsubscribe(self, websocket: WebSocket, channel: str):
        """Unsubscribe a connection from a channel."""
        if websocket in self._connections:
            self._connections[websocket].discard(channel)

    async def broadcast(self, channel: str, event_type: str, data: dict[str, Any]):
        """Broadcast a message to all connections subscribed to a channel."""
        message = json.dumps({
            "channel": channel,
            "event": event_type,
            "data": data,
            "timestamp": time.time(),
        }, default=str)

        self._channel_stats[channel] = self._channel_stats.get(channel, 0) + 1
        disconnected = []

        for ws, channels in self._connections.items():
            if channel in channels:
                try:
                    await ws.send_text(message)
                except Exception:
                    disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)

    async def send_to(self, websocket: WebSocket, data: dict[str, Any]):
        """Send a message to a specific connection."""
        try:
            await websocket.send_text(json.dumps(data, default=str))
        except Exception:
            self.disconnect(websocket)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def get_stats(self) -> dict[str, Any]:
        """Get WebSocket stats for monitoring."""
        channel_subscribers: dict[str, int] = {}
        for channels in self._connections.values():
            for ch in channels:
                channel_subscribers[ch] = channel_subscribers.get(ch, 0) + 1

        return {
            "active_connections": self.connection_count,
            "channel_subscribers": channel_subscribers,
            "messages_sent": dict(self._channel_stats),
            "available_channels": sorted(self.CHANNELS),
        }


# Singleton
channel_manager = ChannelManager()


# ── Convenience broadcast helpers ──

async def emit_inventory_update(sku: str, action: str, details: dict[str, Any] | None = None):
    await channel_manager.broadcast("inventory", f"inventory.{action}", {
        "sku": sku,
        **(details or {}),
    })


async def emit_order_event(order_id: str, action: str, details: dict[str, Any] | None = None):
    await channel_manager.broadcast("orders", f"order.{action}", {
        "order_id": order_id,
        **(details or {}),
    })


async def emit_sale_event(sale_data: dict[str, Any]):
    await channel_manager.broadcast("sales", "sale.completed", sale_data)


async def emit_alert(alert_type: str, message: str, severity: str = "info", details: dict[str, Any] | None = None):
    await channel_manager.broadcast("alerts", f"alert.{alert_type}", {
        "message": message,
        "severity": severity,
        **(details or {}),
    })
