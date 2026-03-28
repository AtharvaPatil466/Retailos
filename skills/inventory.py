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
        self.inventory_path = BASE_DIR / "data" / "mock_inventory.json"

    async def init(self) -> None:
        try:
            with open(self.inventory_path, "r") as f:
                raw_inventory = json.load(f)
                self.inventory_data = [self._normalize_item(item) for item in raw_inventory]
        except FileNotFoundError:
            self.inventory_data = []
        self.state = SkillState.RUNNING

    async def run(self, event: dict[str, Any]) -> dict[str, Any]:
        if not event:
            return {"status": "error", "message": "Event is None"}
            
        """Check inventory levels, return alerts for items crossing threshold."""
        alerts = []

        # Handle explicit expiry risk
        if event.get("type") == "expiry_risk":
            data = event.get("data", {})
            alert = {
                "sku": data.get("product_id"),
                "product_name": data.get("product_name"),
                "severity": "critical",
                "days_to_expiry": data.get("days_to_expiry"),
                "expected_unsold": data.get("expected_unsold"),
                "reason": f"Expiring in {data.get('days_to_expiry')} days. At current velocity, ~{data.get('expected_unsold')} units will expire."
            }
            if self.audit:
                await self.audit.log(
                    skill=self.name,
                    event_type="expiry_risk_detected",
                    decision=f"Flagged expiry risk for {data.get('product_name')}",
                    reasoning=alert["reason"],
                    outcome=json.dumps(alert, default=str),
                    status="alert",
                )
            return {"alerts": [alert]}

        # If triggered with a specific SKU update, process just that
        if event.get("type") == "stock_update":
            sku = event["data"].get("sku")
            new_quantity = event["data"].get("quantity")
            item = self._find_item(sku)
            if item:
                old_qty = item["current_stock"]
                qty_change = new_quantity - old_qty
                
                # Log the movement
                if qty_change != 0:
                    movement_type = event["data"].get("movement_type")
                    if not movement_type:
                        movement_type = "restock" if qty_change > 0 else "sale"
                    from brain.wastage_tracker import log_movement
                    log_movement(sku, qty_change, movement_type)

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

        result = {"alerts": alerts, "total_checked": len(self.inventory_data)}
        
        # Only create approval if explicitly updated, to prevent infinite loops of auto-checks
        if alerts and event.get("type") in ["stock_update", "inventory_check"]:
            main_alert = alerts[0]
            result.update({
                "needs_approval": True,
                "approval_id": f"restock_{main_alert['sku']}_{int(time.time())}",
                "approval_reason": f"Low Stock Alert: {main_alert['product_name']} only has {main_alert['current_stock']} units left. Approve AI restock sequence?",
                "approval_details": {
                    "product": main_alert["product_name"],
                    "current_stock": main_alert["current_stock"],
                    "threshold": main_alert["threshold"],
                    "action_plan": "Approve to unleash the Procurement and Negotiation agents to find the best supplier and secure a deal."
                },
                "on_approval_event": {
                    "type": "start_procurement",
                    "data": {
                        "product_name": main_alert["product_name"],
                        "sku": main_alert["sku"],
                        "category": main_alert.get("category", ""),
                        "daily_sales_rate": main_alert.get("daily_sales_rate", 10)
                    }
                }
            })
            
        return result

    def _find_item(self, sku: str) -> dict | None:
        for item in self.inventory_data:
            if item["sku"] == sku:
                return item
        return None

    def _normalize_item(self, item: dict) -> dict:
        normalized = dict(item)
        normalized["image_url"] = normalized.get("image_url")
        normalized["barcode"] = normalized.get("barcode")
        normalized["unit_price"] = float(normalized.get("unit_price", 0))
        normalized["category"] = normalized.get("category", "")
        normalized["reorder_threshold"] = normalized.get("reorder_threshold", normalized.get("threshold", 0))
        normalized["threshold"] = normalized["reorder_threshold"]
        return normalized

    def _save_inventory(self) -> None:
        serialized = []
        for item in self.inventory_data:
            stored_item = dict(item)
            stored_item.pop("threshold", None)
            serialized.append(stored_item)

        with open(self.inventory_path, "w") as f:
            json.dump(serialized, f, indent=2)
            f.write("\n")

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
                "image_url": item.get("image_url"),
                "barcode": item.get("barcode"),
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
                "threshold": item.get("reorder_threshold", item.get("threshold", 0)),
                "days_until_stockout": round(float(days_left), 1),
                "status": "critical" if days_left < 2 else "warning" if days_left < 5 else "ok",
            })
        return result

    async def update_stock(
        self,
        sku: str,
        quantity: int,
        movement_type: str = "",
        unit_price: float | None = None,
        image_url: str | None = None,
        category: str | None = None,
    ) -> dict:
        """Manually update stock for a SKU (used for demo)."""
        item = self._find_item(sku)
        if not item:
            return {"error": f"SKU {sku} not found"}
        old_stock = item["current_stock"]
        qty_change = quantity - old_stock
        
        # Log the movement
        if qty_change != 0:
            derived_type = movement_type if movement_type else ("restock" if qty_change > 0 else "sale")
            from brain.wastage_tracker import log_movement
            log_movement(sku, qty_change, derived_type)
            
        item["current_stock"] = quantity
        if unit_price is not None:
            item["unit_price"] = float(unit_price)
        if image_url is not None:
            item["image_url"] = image_url
        if category is not None:
            item["category"] = category

        item["threshold"] = item.get("reorder_threshold", item.get("threshold", 0))
        self._save_inventory()
        return {
            "sku": sku,
            "product_name": item["product_name"],
            "old_stock": old_stock,
            "new_stock": quantity,
            "unit_price": item.get("unit_price"),
            "image_url": item.get("image_url"),
            "category": item.get("category"),
        }

    async def register_product(self, product: dict[str, Any]) -> dict:
        sku = product["sku"]
        if self._find_item(sku):
            return {"error": f"SKU {sku} already exists"}

        new_item = self._normalize_item({
            "sku": sku,
            "product_name": product["product_name"],
            "category": product["category"],
            "image_url": product.get("image_url"),
            "barcode": product.get("barcode"),
            "current_stock": product.get("current_stock", 0),
            "reorder_threshold": product["threshold"],
            "daily_sales_rate": product["daily_sales_rate"],
            "unit_price": product["unit_price"],
            "last_restock_date": product.get("last_restock_date", time.strftime("%Y-%m-%d")),
        })

        self.inventory_data.append(new_item)
        self._save_inventory()
        return new_item

    async def patch_item(
        self,
        sku: str,
        *,
        unit_price: float | None = None,
        image_url: str | None = None,
        category: str | None = None,
        barcode: str | None = None,
    ) -> dict:
        item = self._find_item(sku)
        if not item:
            return {"error": f"SKU {sku} not found"}

        if unit_price is not None:
            item["unit_price"] = float(unit_price)
        if image_url is not None:
            item["image_url"] = image_url
        if category is not None:
            item["category"] = category
        if barcode is not None:
            item["barcode"] = barcode

        item["threshold"] = item.get("reorder_threshold", item.get("threshold", 0))
        self._save_inventory()
        return item

    async def record_sale(self, items: list[dict[str, Any]]) -> dict:
        if not items:
            return {"error": "No sale items provided"}

        sale_lines = []
        total_amount = 0.0

        for sale_item in items:
            sku = sale_item["sku"]
            qty = int(sale_item["qty"])
            if qty <= 0:
                return {"error": f"Invalid quantity for SKU {sku}"}

            item = self._find_item(sku)
            if not item:
                return {"error": f"SKU {sku} not found"}
            if item["current_stock"] < qty:
                return {"error": f"Insufficient stock for SKU {sku}"}

            sale_lines.append((item, qty))

        order_id = f"sale_{int(time.time())}"
        from brain.wastage_tracker import log_movement

        result_lines = []
        for item, qty in sale_lines:
            item["current_stock"] -= qty
            item["threshold"] = item.get("reorder_threshold", item.get("threshold", 0))
            line_total = float(item.get("unit_price", 0)) * qty
            total_amount += line_total
            log_movement(item["sku"], -qty, "sale", order_id=order_id)
            result_lines.append({
                "sku": item["sku"],
                "product_name": item["product_name"],
                "qty": qty,
                "unit_price": float(item.get("unit_price", 0)),
                "line_total": round(line_total, 2),
                "remaining_stock": item["current_stock"],
            })

        self._save_inventory()
        return {
            "order_id": order_id,
            "items": result_lines,
            "total_amount": round(total_amount, 2),
        }
