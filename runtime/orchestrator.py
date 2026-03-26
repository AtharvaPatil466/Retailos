import asyncio
import json
import logging
import time
import traceback
from typing import Any

from google import genai

logger = logging.getLogger(__name__)

from runtime.audit import AuditLogger
from runtime.memory import Memory
from skills.base_skill import BaseSkill
from skills.scheduling import SchedulingSkill


ROUTING_SYSTEM_PROMPT = """You are the RetailOS orchestrator — an autonomous agent runtime for retail operations.

Your job: given an event and relevant memory context, decide which skill(s) to run and in what order.

Available skills:
- inventory: Monitors stock levels, calculates days-until-stockout
- procurement: Ranks suppliers using price, reliability, history
- negotiation: Handles the entire WhatsApp conversation, including sending outreach and parsing/evaluating supplier replies into deals
- customer: Segments customers and sends personalized offers
- analytics: Analyzes patterns in audit logs and purchase data
- scheduling: Manages staff shifts, reviews schedules, and optimizes staffing levels

You must respond with valid JSON only:
{
    "actions": [
        {
            "skill": "<skill_name>",
            "params": { ... },
            "reason": "<why this action, in plain English>"
        }
    ],
    "overall_reasoning": "<1-2 sentence summary of your decision>"
}

Consider memory context carefully. If we over-ordered a product recently, maybe hold off.
If a supplier has been unreliable, deprioritize them. Use the context — that's why it's there.

Be proactive: if an event indicates a potential problem (like low stock), don't just analyze it — trigger the necessary skills (e.g., both inventory and procurement) to solve it in parallel."""


class Orchestrator:
    """Core event loop — the brain of RetailOS.

    Takes events, fetches relevant memory, calls Gemini to decide
    what to do, routes to skills, and logs everything.
    """

    def __init__(
        self,
        memory: Memory,
        audit: AuditLogger,
        # skill_loader: SkillLoader, # Removed SkillLoader
        api_key: str,
    ):
        self.memory = memory
        self.audit = audit
        # self.skill_loader = skill_loader # Removed SkillLoader
        self.client = genai.Client(api_key=api_key) if api_key else None
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.running = False
        self.pending_approvals: dict[str, dict] = {}
        self.max_retries = 3
        self.retry_delay = 2  # seconds

        # Manually load core skills
        from skills.inventory import InventorySkill
        from skills.procurement import ProcurementSkill
        from skills.customer import CustomerSkill
        from skills.analytics import AnalyticsSkill
        from skills.negotiation import NegotiationSkill
        from skills.scheduling import SchedulingSkill
        
        skill_classes = [
            InventorySkill, ProcurementSkill, CustomerSkill, 
            AnalyticsSkill, NegotiationSkill, SchedulingSkill
        ]
        
        self.skills: dict[str, BaseSkill] = {}
        for skill_class in skill_classes:
            skill_instance = skill_class(memory=self.memory, audit=self.audit)
            self.skills[skill_instance.name] = skill_instance

    async def start(self) -> None:
        """Start the orchestrator event loop."""
        self.running = True
        await self.audit.log(
            skill="orchestrator",
            event_type="runtime_start",
            decision="Starting RetailOS runtime",
            reasoning="System initialization",
            outcome="Runtime started successfully",
            status="success",
        )

        # Start the main event processing loop
        asyncio.create_task(self._event_loop())

    async def stop(self) -> None:
        self.running = False
        await self.audit.log(
            skill="orchestrator",
            event_type="runtime_stop",
            decision="Stopping RetailOS runtime",
            reasoning="Shutdown requested",
            outcome="Runtime stopped",
            status="success",
        )

    async def emit_event(self, event: dict[str, Any]) -> None:
        """Push an event into the orchestrator's queue."""
        await self.event_queue.put(event)

    async def _event_loop(self) -> None:
        """Main loop — processes events as they arrive."""
        while self.running:
            try:
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                await self._process_event(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                await self.audit.log(
                    skill="orchestrator",
                    event_type="event_loop_error",
                    decision="Error in event loop",
                    reasoning=str(e),
                    outcome=traceback.format_exc(),
                    status="error",
                )

    async def _process_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Process a single event: fetch context, route via Gemini, execute."""
        if not isinstance(event, dict) or "type" not in event:
            await self.audit.log(
                skill="orchestrator",
                event_type="invalid_event",
                decision="Rejected malformed event",
                reasoning=f"Event missing 'type' field: {event!r}",
                outcome="Skipped",
                status="error",
            )
            return {"error": "Invalid event: missing 'type' field"}
        event_type = event.get("type", "unknown")

        # Intercept delivery and quality events to log them into the central DB
        if event_type == "delivery":
            from brain.decision_logger import log_delivery
            data = event.get("data", {})
            log_delivery(
                data.get("supplier_id", ""),
                data.get("order_id", ""),
                data.get("expected_date", ""),
                data.get("actual_date", "")
            )
            return {"status": "success", "message": "Delivery logged in brain"}
            
        if event_type == "quality_issue":
            from brain.decision_logger import log_quality_flag
            data = event.get("data", {})
            log_quality_flag(
                data.get("supplier_id", ""),
                data.get("order_id", ""),
                data.get("reason", "")
            )
            return {"status": "success", "message": "Quality issue logged in brain"}

        # Intercept daily analytics to also run churn detector
        if event_type == "daily_analytics":
            from pathlib import Path
            import json
            import asyncio
            base_dir = Path(__file__).resolve().parent.parent
            try:
                with open(base_dir / "data" / "mock_customers.json", "r") as f:
                    customers = json.load(f)
                from brain.churn_detector import detect_at_risk_customers
                churn_events = detect_at_risk_customers(customers)
                for ce in churn_events:
                    asyncio.create_task(self.emit_event(ce))
            except Exception as e:
                logger.error(f"Churn detection failed: {e}")
                
            # Expiry Alerter
            from brain.expiry_alerter import get_expiry_risks
            try:
                with open(base_dir / "data" / "mock_inventory.json", "r") as f:
                    inventory_items = json.load(f)
                expiry_events = get_expiry_risks(inventory_items)
                for ee in expiry_events:
                    asyncio.create_task(self.emit_event(ee))
            except Exception as e:
                logger.error(f"Expiry detection failed: {e}")
                
            # Competitor Price Monitor Auto-Fetch
            try:
                from brain.price_monitor import fetch_agmarknet_prices
                with open(base_dir / "data" / "mock_inventory.json", "r") as f:
                    inv_items = json.load(f)
                
                # Fetch top 20 items by sales volume
                sorted_items = sorted(inv_items, key=lambda x: x.get("daily_sales_rate", 0), reverse=True)
                top_20_skus = [i["sku"] for i in sorted_items[:20]]
                if top_20_skus:
                    fetch_agmarknet_prices(top_20_skus)
            except Exception as e:
                logger.error(f"Price fetching failed: {e}")
                
            # --- Staff Scheduling Auto-Review ---
            # Automatically push a shift_review event for tomorrow into the system natively
            try:
                from datetime import date, timedelta
                tomorrow = date.today() + timedelta(days=1)
                if "scheduling" in self.skills:
                    # Fire directly synchronously to prevent complex queue drops in testing
                    sched_result = await self.skills["scheduling"].run({
                        "type": "shift_review", 
                        "data": {"target_date": tomorrow.isoformat()}
                    })
                    if sched_result.get("needs_approval"):
                        self._add_to_approval_queue(sched_result)
            except Exception as e:
                logger.error(f"Daily scheduling review failed: {e}")

            # Do NOT return here, allow daily_analytics to proceed to the analytics skill

        # Fetch relevant memory
        context = await self.memory.get_relevant(event_type, event.get("data", {}))

        # Ask Gemini to route
        routing_decision = await self._route_with_gemini(event, context)

        results = []
        for action in routing_decision.get("actions", []):
            skill_name = action["skill"]
            params = action.get("params", {})
            reason = action.get("reason", "No reason provided")

            result = await self._execute_skill(skill_name, event, params, reason)
            results.append(result)

        return {
            "event": event,
            "routing": routing_decision,
            "results": results,
        }

    async def _route_with_gemini(self, event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """CALL 1 — Orchestrator routing. Gemini decides what to do."""
        prompt = f"""{ROUTING_SYSTEM_PROMPT}

Event received:
{json.dumps(event, indent=2, default=str)}

Relevant memory context:
{json.dumps(context, indent=2, default=str) if context else "No relevant memory found."}

Decide which skill(s) to run and why."""

        for attempt in range(self.max_retries):
            try:
                if not self.client:
                    raise ValueError("API key not configured")
                
                response = await self.client.aio.models.generate_content(
                    model="gemini-1.5-flash",
                    contents=prompt
                )

                text = response.text
                # Extract JSON from response
                try:
                    if "```json" in text:
                        parts = text.split("```json")
                        if len(parts) > 1:
                            inner = parts[1].split("```")
                            text = inner[0] if len(inner) > 1 else inner[0]
                    elif "```" in text:
                        parts = text.split("```")
                        if len(parts) > 2:
                            text = parts[1]
                except (IndexError, ValueError):
                    pass

                decision = json.loads(text.strip())

                await self.audit.log(
                    skill="orchestrator",
                    event_type="routing_decision",
                    decision=json.dumps(decision.get("actions", []), default=str),
                    reasoning=decision.get("overall_reasoning", ""),
                    outcome="Route determined",
                    status="success",
                    metadata={"event": event, "memory_keys": list(context.keys())},
                )

                return decision

            except Exception as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                    continue
                await self.audit.log(
                    skill="orchestrator",
                    event_type="gemini_api_error",
                    decision="API error after retries",
                    reasoning=f"Gemini API failed {self.max_retries} times: {e}",
                    outcome="Falling back to rule-based routing",
                    status="error",
                )
                return self._fallback_route(event)

        return self._fallback_route(event)  # pragma: no cover — safety net for max_retries=0

    def _fallback_route(self, event: dict[str, Any]) -> dict[str, Any]:
        """Rule-based fallback when Gemini API is unavailable."""
        event_type = event.get("type", "")
        actions = []

        if event_type == "low_stock" or event_type == "stock_update":
            actions = [
                {"skill": "procurement", "params": event.get("data", {}), "reason": "Fallback: stock level change triggers procurement check"},
            ]
        elif event_type == "seasonal_preempt":
            actions = [
                {"skill": "procurement", "params": event.get("data", {}), "reason": "Fallback: seasonal pattern detected, triggering proactive procurement"},
            ]
        elif event_type == "procurement_approved":
            actions = [
                {"skill": "negotiation", "params": event.get("data", {}), "reason": "Fallback: procurement approved triggers negotiation"},
            ]
        elif event_type == "supplier_reply":
            actions = [
                {"skill": "negotiation", "params": event.get("data", {}), "reason": "Fallback: supplier reply needs parsing"},
            ]
        elif event_type == "deal_confirmed":
            actions = [
                {"skill": "customer", "params": event.get("data", {}), "reason": "Fallback: deal confirmed triggers customer outreach"},
            ]
        elif event_type == "churn_risk":
            actions = [
                {"skill": "customer", "params": event.get("data", {}), "reason": "Fallback: churn risk detected, triggering re-engagement"},
            ]
        elif event_type == "expiry_risk":
            actions = [
                {"skill": "inventory", "params": event.get("data", {}), "reason": "Fallback: flag expiry risk on dashboard"},
                {"skill": "customer", "params": {**event.get("data", {}), "discount": "20% off (Flash Sale!)"}, "reason": "Fallback: chain targeted promotion for expiring product"},
            ]

        return {"actions": actions, "overall_reasoning": "Fallback rule-based routing (Gemini unavailable)"}

    async def _execute_skill(
        self, skill_name: str, event: dict[str, Any], params: dict[str, Any], reason: str
    ) -> dict[str, Any]:
        """Execute a skill with retry logic and failure handling."""
        skill = self.skill_loader.get_skill(skill_name)

        if not skill:
            await self.audit.log(
                skill=skill_name,
                event_type="skill_not_found",
                decision=f"Cannot execute {skill_name}",
                reasoning=f"Skill '{skill_name}' not registered",
                outcome="Skipped",
                status="error",
            )
            return {"skill": skill_name, "status": "not_found"}

        if skill.state == SkillState.PAUSED:
            await self.audit.log(
                skill=skill_name,
                event_type="skill_paused_skip",
                decision=f"Skipping {skill_name} — currently paused",
                reasoning=reason,
                outcome="Skipped",
                status="skipped",
            )
            return {"skill": skill_name, "status": "paused"}

        # Retry loop
        merged_event = {**event, "params": params}
        for attempt in range(self.max_retries):
            try:
                result = await skill._safe_run(merged_event)

                await self.audit.log(
                    skill=skill_name,
                    event_type=f"skill_executed",
                    decision=reason,
                    reasoning=f"Executed on attempt {attempt + 1}",
                    outcome=json.dumps(result, default=str)[:2000],
                    status="success",
                    metadata={"attempt": attempt + 1, "params": params},
                )

                # Check if result needs owner approval
                if result.get("needs_approval"):
                    details = result.get("approval_details", {})
                    supplier_id = details.get("supplier_id") or (details.get("top_supplier", {}).get("supplier_id") if details.get("top_supplier") else None)
                    amount = details.get("amount") or details.get("price") or details.get("total_cost") or (details.get("top_supplier", {}).get("price_per_unit", 0) * details.get("top_supplier", {}).get("min_order_qty", 1) if details.get("top_supplier") else None)

                    auto_approved = False
                    if supplier_id and amount is not None:
                        from brain.auto_approver import should_auto_approve
                        from brain.decision_logger import log_decision
                        
                        if should_auto_approve(supplier_id, amount):
                            auto_approved = True
                            log_decision(supplier_id, amount, "approved")
                            
                            follow_up = result.get("on_approval_event")
                            if follow_up:
                                asyncio.create_task(self.emit_event(follow_up))
                                
                            await self.audit.log(
                                skill=skill_name,
                                event_type="auto_approved",
                                decision="Silently approved via Brain subsystem",
                                reasoning=f"Trust score high and amount {amount} below ceiling",
                                outcome="Triggered follow-up event",
                                status="success"
                            )
                            return {"skill": skill_name, "status": "success", "result": result, "auto_approved": True}

                    approval_id = result.get("approval_id", f"{skill_name}_{int(time.time())}")
                    self.pending_approvals[approval_id] = {
                        "skill": skill_name,
                        "result": result,
                        "event": event,
                        "timestamp": time.time(),
                    }
                    await self.audit.log(
                        skill=skill_name,
                        event_type="approval_requested",
                        decision="Awaiting owner approval",
                        reasoning=result.get("approval_reason", "Significant action requires approval"),
                        outcome=json.dumps(result.get("approval_details", {}), default=str),
                        status="pending",
                    )

                return {"skill": skill_name, "status": "success", "result": result}

            except Exception as e:
                await self.audit.log(
                    skill=skill_name,
                    event_type="skill_error",
                    decision=f"Skill failed on attempt {attempt + 1}/{self.max_retries}",
                    reasoning=str(e),
                    outcome=traceback.format_exc()[:1000],
                    status="error",
                    metadata={"attempt": attempt + 1},
                )

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                    continue

                # All retries exhausted — escalate
                await self.audit.log(
                    skill=skill_name,
                    event_type="skill_escalation",
                    decision=f"Escalating {skill_name} failure to owner",
                    reasoning=f"Failed after {self.max_retries} attempts: {e}",
                    outcome="Owner notification sent",
                    status="escalated",
                )

                return {"skill": skill_name, "status": "failed", "error": str(e)}

        # All retries exhausted via exception path above; this is a safety net
        logger.warning("Skill %s: retry loop exited without return", skill_name)
        return {"skill": skill_name, "status": "failed"}

    async def approve(self, approval_id: str) -> dict[str, Any]:
        """Owner approves a pending action."""
        if approval_id not in self.pending_approvals:
            return {"error": "Approval not found"}

        approval = self.pending_approvals.pop(approval_id)
        
        from brain.decision_logger import log_decision
        details = approval["result"].get("approval_details", {})
        supplier_id = details.get("supplier_id") or (details.get("top_supplier", {}).get("supplier_id") if details.get("top_supplier") else None)
        amount = details.get("amount") or details.get("price") or details.get("total_cost") or (details.get("top_supplier", {}).get("price_per_unit", 0) * details.get("top_supplier", {}).get("min_order_qty", 1) if details.get("top_supplier") else None)
        if supplier_id and amount is not None:
            log_decision(supplier_id, amount, "approved")
            
        await self.audit.log(
            skill=approval["skill"],
            event_type="owner_approved",
            decision="Owner approved action",
            reasoning="Manual approval via dashboard",
            outcome=json.dumps(approval["result"].get("approval_details", {}), default=str),
            status="approved",
        )

        # Trigger any follow-up events
        follow_up = approval["result"].get("on_approval_event")
        if follow_up:
            await self.emit_event(follow_up)

        return {"status": "approved", "approval_id": approval_id}

    async def reject(self, approval_id: str, reason: str = "") -> dict[str, Any]:
        """Owner rejects a pending action."""
        if approval_id not in self.pending_approvals:
            return {"error": "Approval not found"}

        approval = self.pending_approvals.pop(approval_id)
        
        from brain.decision_logger import log_decision
        details = approval["result"].get("approval_details", {})
        supplier_id = details.get("supplier_id") or (details.get("top_supplier", {}).get("supplier_id") if details.get("top_supplier") else None)
        amount = details.get("amount") or details.get("price") or details.get("total_cost") or (details.get("top_supplier", {}).get("price_per_unit", 0) * details.get("top_supplier", {}).get("min_order_qty", 1) if details.get("top_supplier") else None)
        if supplier_id and amount is not None:
            log_decision(supplier_id, amount, "rejected")

        await self.audit.log(
            skill=approval["skill"],
            event_type="owner_rejected",
            decision="Owner rejected action",
            reasoning=reason or "No reason provided",
            outcome="Action cancelled",
            status="rejected",
        )

        return {"status": "rejected", "approval_id": approval_id}

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        return [
            {"id": k, **v}
            for k, v in self.pending_approvals.items()
        ]
