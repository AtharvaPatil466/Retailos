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
from runtime.skill_loader import SkillLoader
from skills.base_skill import SkillState


ROUTING_SYSTEM_PROMPT = """You are the RetailOS orchestrator — an autonomous agent runtime for retail operations.

Your job: given an event and relevant memory context, decide which skill(s) to run and in what order.

Available skills:
- inventory: Monitors stock levels, calculates days-until-stockout
- procurement: Ranks suppliers using price, reliability, history
- negotiation: Handles the entire WhatsApp conversation, including sending outreach and parsing/evaluating supplier replies into deals
- customer: Segments customers and sends personalized offers
- analytics: Analyzes patterns in audit logs and purchase data

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
        skill_loader: SkillLoader,
        api_key: str,
    ):
        self.memory = memory
        self.audit = audit
        self.skill_loader = skill_loader
        self.client = genai.Client(api_key=api_key) if api_key else None
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.running = False
        self.pending_approvals: dict[str, dict] = {}
        self.max_retries = 3
        self.retry_delay = 2  # seconds

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
