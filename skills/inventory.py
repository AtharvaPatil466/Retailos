import json
import time
from pathlib import Path
from typing import Any

from .base_skill import BaseSkill, SkillState

BASE_DIR = Path(__file__).resolve().parent.parent


class InventorySkill(BaseSkill):
    """Monitors stock levels and fires alerts when items cross thresholds.

    Pure math — no Gemini API calls. Intelligence comes from the orchestrator
    receiving the event and deciding what to do with it.
    """

    def __init__(self, memory=None, audit=None):
        super().__init__(name="inventory", memory=memory, audit=audit)
        self.inventory_data: list[dict] = []
        self.check_interval = 60  # seconds

    async def init(self) -> None:
        try:
            with open(BASE_DIR / "data" / "mock_inventory.json", "r") as f:
                self.inventory_data = json.load(f)
        except FileNotFoundError:
            self.inventory_data = []
        self.state = SkillState.RUNNING

    async def run(self, event: dict[str, Any]) -> dict[str, Any]:
        if not event:
            return {"status": "error", "message": "Event is None"}
            
        """Check inventory levels, return alerts for items crossing threshold."""
        alerts = []

        # If triggered with a specific SKU update, process just that
        if event.get("type") == "stock_update":
            sku = event["data"].get("sku")
            new_quantity = event["data"].get("quantity")
            item = self._find_item(sku)
            if item:
                item["current_stock"] = new_quantity
                alert = self._check_item(item)
                if alert:
                    alerts.append(alert)
        else:
            # Full scan
            for item in self.inventory_data:
                alert = self._check_item(item)
                if alert:
                    alerts.append(alert)

        if alerts and self.audit:
            for alert in alerts:
                await self.audit.log(
                    skill=self.name,
                    event_type="low_stock_detected",
                    decision=f"Stock alert for {alert['product_name']}",
                    reasoning=(
                        f"Current stock: {alert['current_stock']} units. "
                        f"Daily sales rate: {alert['daily_sales_rate']}/day. "
                        f"Days until stockout: {alert['days_until_stockout']:.1f}. "
                        f"Threshold: {alert['threshold']} units."
                    ),
                    outcome=json.dumps(alert, default=str),
                    status="alert",
                )

        return {"alerts": alerts, "total_checked": len(self.inventory_data)}

    def _find_item(self, sku: str) -> dict | None:
        for item in self.inventory_data:
            if item["sku"] == sku:
                return item
        return None

    def _check_item(self, item: dict) -> dict | None:
        """Check if item needs restocking based on stock level AND sales velocity."""
        current = item.get("current_stock", 0)
        daily_rate = item.get("daily_sales_rate", 0)
        threshold = item.get("reorder_threshold", 0)

        # Calculate days until stockout
        days_until_stockout = current / daily_rate if daily_rate > 0 else float("inf")

        # Alert if below threshold OR less than 5 days of stock remaining
        if current <= threshold or (daily_rate > 0 and days_until_stockout < 5):
            return {
                "sku": item["sku"],
                "product_name": item["product_name"],
                "category": item.get("category", ""),
                "current_stock": current,
                "threshold": threshold,
                "daily_sales_rate": daily_rate,
                "days_until_stockout": days_until_stockout,
                "last_restock_date": item.get("last_restock_date", "unknown"),
                "unit_price": item.get("unit_price", 0),
                "severity": "critical" if days_until_stockout < 2 else "warning",
            }

        return None

    async def get_full_inventory(self) -> list[dict]:
        """Return full inventory with computed fields."""
        result = []
        for item in self.inventory_data:
            daily_rate = item.get("daily_sales_rate", 0)
            current = item.get("current_stock", 0)
            days_left = current / daily_rate if daily_rate > 0 else float("inf")
            result.append({
                **item,
                "days_until_stockout": round(float(days_left), 1),
                "status": "critical" if days_left < 2 else "warning" if days_left < 5 else "ok",
            })
        return result

    async def update_stock(self, sku: str, quantity: int) -> dict:
        """Manually update stock for a SKU (used for demo)."""
        item = self._find_item(sku)
        if not item:
            return {"error": f"SKU {sku} not found"}
        old_stock = item["current_stock"]
        item["current_stock"] = quantity
        return {
            "sku": sku,
            "product_name": item["product_name"],
            "old_stock": old_stock,
            "new_stock": quantity,
        }
