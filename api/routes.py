import asyncio
import json
import time
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from runtime.orchestrator import Orchestrator

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()


class EventPayload(BaseModel):
    type: str
    data: dict[str, Any] = {}


class StockUpdatePayload(BaseModel):
    sku: str
    quantity: int
    unit_price: float | None = None
    image_url: str | None = None
    category: str | None = None


class InventoryRegisterPayload(BaseModel):
    sku: str
    product_name: str
    unit_price: float
    category: str
    image_url: str | None = None
    barcode: str | None = None
    threshold: int
    daily_sales_rate: int
    current_stock: int = 0


class InventoryPatchPayload(BaseModel):
    unit_price: float | None = None
    image_url: str | None = None
    category: str | None = None
    barcode: str | None = None


class SaleItemPayload(BaseModel):
    sku: str
    qty: int


class InventorySalePayload(BaseModel):
    items: list[SaleItemPayload]


class SupplierReplyPayload(BaseModel):
    negotiation_id: str
    supplier_id: str
    supplier_name: str
    message: str
    product_name: str = ""


class ApprovalPayload(BaseModel):
    approval_id: str
    reason: str = ""


def create_app(orchestrator: Orchestrator) -> FastAPI:
    app = FastAPI(title="RetailOS", description="Autonomous Agent Runtime for Retail Operations")

    @app.on_event("startup")
    async def startup_event():
        async def broadcast_log(entry):
            await manager.broadcast(json.dumps({
                "type": "audit_log",
                "data": entry
            }, default=str))
        orchestrator.audit.on_log = broadcast_log

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Helper ──────────────────────────────────────────────
    def _get_skill(name: str):
        """Look up a skill from the orchestrator's skills dict."""
        return orchestrator.skills.get(name)

    def _list_skills():
        """Return status for all loaded skills."""
        return [skill.status() for skill in orchestrator.skills.values()]

    # ── Real-time Events ────────────────────────────────────
    @app.websocket("/ws/events")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    # ── Runtime Status ──────────────────────────────────────

    @app.get("/api/status")
    async def get_status():
        skills = _list_skills()
        return {
            "runtime": "running" if orchestrator.running else "stopped",
            "skills": skills,
            "pending_approvals": len(orchestrator.pending_approvals),
            "timestamp": time.time(),
        }

    @app.get("/api/skills")
    async def list_skills():
        return _list_skills()

    @app.post("/api/skills/{skill_name}/pause")
    async def pause_skill(skill_name: str):
        skill = _get_skill(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
        await skill.pause()
        return {"status": "paused", "skill": skill_name}

    @app.post("/api/skills/{skill_name}/resume")
    async def resume_skill(skill_name: str):
        skill = _get_skill(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
        await skill.resume()
        return {"status": "resumed", "skill": skill_name}

    # ── Events ──────────────────────────────────────────────

    @app.post("/api/events")
    async def emit_event(payload: EventPayload):
        await orchestrator.emit_event({"type": payload.type, "data": payload.data})
        return {"status": "event_queued", "type": payload.type}

    # ── Inventory ───────────────────────────────────────────

    @app.get("/api/inventory")
    async def get_inventory():
        skill = _get_skill("inventory")
        if not skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")
        return await skill.get_full_inventory()

    @app.post("/api/inventory/update")
    async def update_stock(payload: StockUpdatePayload):
        """Manually update stock level — used for demo."""
        skill = _get_skill("inventory")
        if not skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")

        result = await skill.update_stock(
            payload.sku,
            payload.quantity,
            unit_price=payload.unit_price,
            image_url=payload.image_url,
            category=payload.category,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        await orchestrator.emit_event({
            "type": "stock_update",
            "data": {
                "sku": payload.sku,
                "quantity": payload.quantity,
                "unit_price": payload.unit_price,
                "image_url": payload.image_url,
                "category": payload.category,
            },
        })

        return result

    @app.post("/api/inventory/register")
    async def register_inventory_product(payload: InventoryRegisterPayload):
        skill = _get_skill("inventory")
        if not skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")

        result = await skill.register_product(payload.model_dump())
        if "error" in result:
            raise HTTPException(status_code=409, detail=result["error"])
        return result

    @app.patch("/api/inventory/{sku}")
    async def patch_inventory_item(sku: str, payload: InventoryPatchPayload):
        skill = _get_skill("inventory")
        if not skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")

        result = await skill.patch_item(
            sku,
            unit_price=payload.unit_price,
            image_url=payload.image_url,
            category=payload.category,
            barcode=payload.barcode,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app.post("/api/inventory/sale")
    async def record_inventory_sale(payload: InventorySalePayload):
        skill = _get_skill("inventory")
        if not skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")

        result = await skill.record_sale([item.model_dump() for item in payload.items])
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        for crossing in result.get("threshold_crossings", []):
            await orchestrator.emit_event({
                "type": "stock_update",
                "data": {
                    "sku": crossing["sku"],
                    "quantity": crossing["new_quantity"],
                    "movement_type": "sale",
                },
            })
        return result

    @app.post("/api/inventory/check")
    async def check_inventory():
        """Trigger a full inventory check."""
        await orchestrator.emit_event({"type": "inventory_check", "data": {}})
        return {"status": "inventory_check_queued"}

    # ── Supplier Reply Webhook ──────────────────────────────

    @app.post("/api/webhook/supplier-reply")
    async def supplier_reply_webhook(payload: SupplierReplyPayload):
        """WhatsApp webhook — receives supplier replies."""
        await orchestrator.emit_event({
            "type": "supplier_reply",
            "data": {
                "negotiation_id": payload.negotiation_id,
                "supplier_id": payload.supplier_id,
                "supplier_name": payload.supplier_name,
                "message": payload.message,
                "product_name": payload.product_name,
            },
        })
        return {"status": "reply_queued"}

    # Mock endpoint for demo — simulate supplier reply
    @app.post("/api/demo/supplier-reply")
    async def mock_supplier_reply(payload: SupplierReplyPayload):
        """Demo endpoint — simulate a supplier WhatsApp reply."""
        negotiation_skill = _get_skill("negotiation")
        if not negotiation_skill:
            raise HTTPException(status_code=404, detail="Negotiation skill not loaded")

        result = await negotiation_skill._handle_reply({
            "negotiation_id": payload.negotiation_id,
            "supplier_id": payload.supplier_id,
            "supplier_name": payload.supplier_name,
            "message": payload.message,
            "product_name": payload.product_name,
        })

        if result.get("needs_approval"):
            approval_id = result["approval_id"]
            orchestrator.pending_approvals[approval_id] = {
                "skill": "negotiation",
                "result": result,
                "event": {"type": "supplier_reply"},
                "timestamp": time.time(),
            }

        return result

    # ── Approvals ───────────────────────────────────────────

    @app.get("/api/approvals")
    async def get_approvals():
        return orchestrator.get_pending_approvals()

    @app.post("/api/approvals/approve")
    async def approve_action(payload: ApprovalPayload):
        result = await orchestrator.approve(payload.approval_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app.post("/api/approvals/reject")
    async def reject_action(payload: ApprovalPayload):
        result = await orchestrator.reject(payload.approval_id, payload.reason)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    # ── Audit Log ───────────────────────────────────────────

    @app.get("/api/audit")
    async def get_audit_logs(skill: str | None = None, event_type: str | None = None, limit: int = 50, offset: int = 0):
        return await orchestrator.audit.get_logs(
            skill=skill, event_type=event_type, limit=limit, offset=offset
        )

    @app.get("/api/audit/count")
    async def get_audit_count():
        count = await orchestrator.audit.get_log_count()
        return {"count": count}

    # ── Negotiations ────────────────────────────────────────

    @app.get("/api/negotiations")
    async def get_negotiations():
        skill = _get_skill("negotiation")
        if not skill:
            raise HTTPException(status_code=404, detail="Negotiation skill not loaded")
        return {
            "active": skill.active_negotiations,
            "message_log": skill.message_log[-50:],
        }

    # ── Analytics ───────────────────────────────────────────

    @app.post("/api/analytics/run")
    async def run_analytics():
        await orchestrator.emit_event({"type": "daily_analytics", "data": {}})
        return {"status": "analytics_queued"}

    @app.get("/api/analytics/summary")
    async def get_analytics_summary():
        if orchestrator.memory:
            summary = await orchestrator.memory.get("orchestrator:daily_summary")
            return summary or {"message": "No analytics summary available yet"}
        return {"message": "Memory not available"}

    # ── Demo Flow (Scripted Chain) ──────────────────────────

    @app.post("/api/demo/trigger-flow")
    async def trigger_demo_flow():
        """Trigger the full ice cream demo flow with timed events."""
        inventory_skill = _get_skill("inventory")
        if not inventory_skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")

        async def _run_demo():
            """Background task: runs the cinematic demo chain."""
            try:
                # Step 1: Drop stock to critical
                await orchestrator.audit.log(
                    skill="orchestrator",
                    event_type="demo_started",
                    decision="🎬 Demo started — Ice cream stock dropping to critical",
                    reasoning="Owner triggered the live demo flow",
                    outcome="Stock will drop to 5 units",
                    status="success",
                )
                await inventory_skill.update_stock("SKU-001", 5)

                await asyncio.sleep(2)

                # Step 2: Simulate inventory detection
                await orchestrator.audit.log(
                    skill="inventory",
                    event_type="low_stock_detected",
                    decision="🚨 Ice cream stock critically low — only 5 units left!",
                    reasoning="Stock dropped below reorder threshold of 20 units",
                    outcome=json.dumps({"sku": "SKU-001", "product_name": "Amul Vanilla Ice Cream", "quantity": 5, "threshold": 20}),
                    status="alert",
                )

                await asyncio.sleep(2)

                # Step 3: Simulate procurement search
                await orchestrator.audit.log(
                    skill="procurement",
                    event_type="supplier_ranking",
                    decision="📋 Evaluated 5 suppliers — FreshFreeze Distributors is the best option",
                    reasoning="Ranked by composite score: price ₹145/unit, reliability 4.8/5, next-day delivery, good trust score (94%)",
                    outcome=json.dumps([
                        {"rank": 1, "supplier_name": "FreshFreeze Distributors", "price_per_unit": 145, "delivery_days": 1},
                        {"rank": 2, "supplier_name": "CoolChain India", "price_per_unit": 155, "delivery_days": 2},
                    ]),
                    status="success",
                )

                await asyncio.sleep(2)

                # Step 4: Simulate negotiation outreach
                await orchestrator.audit.log(
                    skill="negotiation",
                    event_type="outreach_sent",
                    decision="📱 Sent WhatsApp message to FreshFreeze Distributors",
                    reasoning="Top-ranked supplier for ice cream procurement",
                    outcome="Message sent via WhatsApp Business API",
                    status="success",
                    metadata={"supplier_id": "SUP-001"},
                )

                await asyncio.sleep(2)

                # Step 5: Simulate supplier reply
                await orchestrator.audit.log(
                    skill="negotiation",
                    event_type="reply_parsed",
                    decision="💬 Supplier replied: 50 boxes at ₹145/unit, delivery tomorrow, COD accepted",
                    reasoning="Parsed WhatsApp reply from FreshFreeze — deal is within budget (saving ₹2,500 vs usual price)",
                    outcome=json.dumps({
                        "supplier": "FreshFreeze Distributors",
                        "price_per_unit": 145,
                        "quantity": 50,
                        "delivery": "tomorrow",
                        "terms": "COD"
                    }),
                    status="success",
                )

                await asyncio.sleep(2)

                # Step 6: Create the approval card
                approval_id = f"demo_procurement_SKU-001_{int(time.time())}"
                orchestrator.pending_approvals[approval_id] = {
                    "id": approval_id,
                    "skill": "negotiation",
                    "reason": "I found a better price for Amul Vanilla Ice Cream!",
                    "result": {
                        "product_name": "Amul Vanilla Ice Cream",
                        "sku": "SKU-001",
                        "negotiation_id": f"neg_demo_{int(time.time())}",
                        "top_supplier": {
                            "supplier_id": "SUP-001",
                            "supplier_name": "FreshFreeze Distributors",
                            "price_per_unit": 145,
                            "delivery_days": 1,
                            "min_order_qty": 30,
                        },
                        "parsed": {
                            "price_per_unit": 145,
                            "quantity": 50,
                            "delivery": "tomorrow",
                        },
                    },
                    "event": {"type": "supplier_reply"},
                    "timestamp": time.time(),
                }

                await orchestrator.audit.log(
                    skill="orchestrator",
                    event_type="approval_requested",
                    decision="🔔 Deal ready! Waiting for your approval on the Approvals tab",
                    reasoning="FreshFreeze offered ₹145/unit for 50 boxes of ice cream with next-day delivery. Saving ₹2,500 vs usual supplier.",
                    outcome="Approval card created — tap YES to order",
                    status="pending",
                )

            except Exception as e:
                await orchestrator.audit.log(
                    skill="orchestrator",
                    event_type="demo_error",
                    decision="Demo flow encountered an error",
                    reasoning=str(e),
                    outcome="Some steps may not have completed",
                    status="error",
                )

        # Launch the demo as a background task
        asyncio.create_task(_run_demo())

        return {
            "status": "demo_flow_triggered",
            "message": "🎬 Demo started! Watch the Dashboard tab for live events.",
        }

    # ── Expiry Risks (A3) ─────────────────���───────────────

    @app.get("/api/inventory/expiry-risks")
    async def get_expiry_risks():
        from pathlib import Path
        from brain.expiry_alerter import get_expiry_risks
        base_dir = Path(__file__).resolve().parent.parent
        try:
            with open(base_dir / "data" / "mock_inventory.json", "r") as f:
                items = json.load(f)
            risks = get_expiry_risks(items)
            return [r.get("data", r) for r in risks]
        except Exception:
            return []

    # ── Suppliers (A2) ─���───────────────────────────────────

    class SupplierRegisterPayload(BaseModel):
        supplier_id: str
        supplier_name: str
        contact_phone: str
        whatsapp_number: str = ""
        products: list[str] = []
        categories: list[str] = []
        price_per_unit: float = 0
        min_order_qty: int = 0
        delivery_days: int = 0
        payment_terms: str = ""
        location: str = ""
        notes: str = ""

    @app.get("/api/suppliers")
    async def get_suppliers():
        from pathlib import Path
        from brain.trust_scorer import get_trust_score
        base_dir = Path(__file__).resolve().parent.parent
        try:
            with open(base_dir / "data" / "mock_suppliers.json", "r") as f:
                suppliers = json.load(f)
        except Exception:
            suppliers = []

        enriched = []
        for s in suppliers:
            trust = get_trust_score(s["supplier_id"])
            enriched.append({**s, "trust_score": trust["score"], "trust_breakdown": trust.get("breakdown", {})})
        return enriched

    @app.post("/api/suppliers/register")
    async def register_supplier(payload: SupplierRegisterPayload):
        from pathlib import Path
        base_dir = Path(__file__).resolve().parent.parent
        suppliers_path = base_dir / "data" / "mock_suppliers.json"
        try:
            with open(suppliers_path, "r") as f:
                suppliers = json.load(f)
        except Exception:
            suppliers = []

        for s in suppliers:
            if s["supplier_id"] == payload.supplier_id:
                raise HTTPException(status_code=409, detail="Supplier ID already exists")

        new_supplier = {
            "supplier_id": payload.supplier_id,
            "supplier_name": payload.supplier_name,
            "contact_phone": payload.contact_phone,
            "products": payload.products,
            "categories": payload.categories,
            "price_per_unit": payload.price_per_unit,
            "reliability_score": 3.0,
            "delivery_days": payload.delivery_days,
            "min_order_qty": payload.min_order_qty,
            "payment_terms": payload.payment_terms,
            "location": payload.location,
        }
        suppliers.append(new_supplier)
        with open(suppliers_path, "w") as f:
            json.dump(suppliers, f, indent=2)
            f.write("\n")
        return {"status": "registered", "supplier": new_supplier}

    @app.get("/api/suppliers/{supplier_id}/history")
    async def get_supplier_history(supplier_id: str):
        from brain.trust_scorer import get_trust_score
        from brain.decision_logger import _get_connection
        trust = get_trust_score(supplier_id)
        decisions = []
        try:
            with _get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT amount, status, timestamp FROM decisions WHERE supplier_id = ? ORDER BY timestamp DESC LIMIT 20",
                    (supplier_id,),
                )
                decisions = [{"amount": r[0], "status": r[1], "timestamp": r[2]} for r in cursor.fetchall()]
        except Exception:
            pass
        return {"trust": trust, "decisions": decisions}

    # ── Market Prices (A4) ───────���─────────────────────────

    class MarketPriceLogPayload(BaseModel):
        product_id: str
        source_name: str
        price_per_unit: float
        unit: str = "kg"

    @app.get("/api/market-prices")
    async def get_all_market_prices():
        from brain.price_monitor import get_market_reference
        skill = _get_skill("inventory")
        if not skill:
            return []
        results = []
        for item in skill.inventory_data:
            ref = get_market_reference(item["sku"])
            if ref.get("median_price") is not None:
                results.append({"sku": item["sku"], "product_name": item["product_name"], **ref})
        return results

    @app.get("/api/market-prices/{sku}")
    async def get_market_price(sku: str):
        from brain.price_monitor import get_market_reference
        return get_market_reference(sku)

    @app.post("/api/market-prices/log")
    async def log_market_price(payload: MarketPriceLogPayload):
        from brain.price_monitor import log_manual_price
        log_manual_price(payload.product_id, payload.source_name, payload.price_per_unit, payload.unit)
        return {"status": "logged"}

    # ── Alerts (A5) ────────────────────────────────────────

    @app.get("/api/alerts")
    async def get_alerts(limit: int = 50):
        cutoff = time.time() - 48 * 3600
        all_logs = await orchestrator.audit.get_logs(limit=200)
        alerts = [
            log for log in all_logs
            if log.get("status") in ("alert", "critical", "escalated", "pending")
            and log.get("timestamp", 0) >= cutoff
        ]
        return alerts[:limit]

    return app
