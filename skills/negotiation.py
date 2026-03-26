import json
import logging
import os
import time
from typing import Any

from google import genai

logger = logging.getLogger(__name__)

from .base_skill import BaseSkill, SkillState


OUTREACH_SYSTEM_PROMPT = """You are writing a WhatsApp message from a supermart owner to a supplier.
Keep it professional but warm. Reference past relationship if context is available.
The message should include: product needed, approximate quantity, and a request for pricing.
Keep it under 150 words. Write naturally, as a real store owner would."""

PARSE_REPLY_PROMPT = """You are parsing a supplier's WhatsApp reply. The reply may be in Hinglish (Hindi + English mixed), may have typos, and may be missing information.

Extract the following fields if present:
- price_per_unit: number or null
- min_order_qty: number or null
- delivery_date: string or null
- delivery_days: number or null
- conditions: string or null
- accepted: boolean or null (did they agree to supply?)

Also identify any MISSING critical fields that we need to follow up on.

Respond with valid JSON only:
{
    "parsed": {
        "price_per_unit": null,
        "min_order_qty": null,
        "delivery_date": null,
        "delivery_days": null,
        "conditions": null,
        "accepted": null
    },
    "missing_fields": ["list of missing critical fields"],
    "needs_clarification": true/false,
    "clarification_message": "Follow-up message to send if clarification needed (or null)",
    "reasoning": "What you understood from the message and what's missing"
}"""


class NegotiationSkill(BaseSkill):
    """Handles supplier outreach via WhatsApp and parses replies.

    CALL 3 — Gemini parses messy supplier replies (Hinglish, typos, partial info).
    This is the hardest NLP problem in the system and the most impressive demo moment.
    """

    def __init__(self, memory=None, audit=None):
        super().__init__(name="negotiation", memory=memory, audit=audit)
        self.client: genai.Client | None = None
        self.active_negotiations: dict[str, dict] = {}
        self.message_log: list[dict] = []  # WhatsApp conversation log

    async def init(self) -> None:
        self.state = SkillState.RUNNING

    async def run(self, event: dict[str, Any]) -> dict[str, Any]:
        if not event:
            return {"status": "error", "message": "Event is None"}
            
        event_type = event.get("type", "")
        data = event.get("data", event.get("params", {}))
        if not data:
            data = {}

        if event_type == "procurement_approved":
            return await self._start_negotiation(data)
        elif event_type == "supplier_reply":
            return await self._handle_reply(data)
        elif event_type == "mock_supplier_reply":
            return await self._handle_reply(data)
        else:
            # Default: start negotiation with ranked suppliers
            return await self._start_negotiation(data)

    async def _start_negotiation(self, data: dict[str, Any]) -> dict[str, Any]:
        ranked = data.get("ranked_suppliers", [])
        product_name = data.get("product_name", "Unknown")
        sku = data.get("sku", "")

        if not ranked:
            return {"status": "no_suppliers", "message": "No ranked suppliers to negotiate with"}

        top_supplier = ranked[0]
        supplier_id = top_supplier["supplier_id"]
        supplier_name = top_supplier["supplier_name"]

        # Get relationship history from memory
        relationship = {}
        if self.memory:
            relationship = await self.memory.get(f"supplier:{supplier_id}:history") or {}

        # Fetch Market Context
        from brain.price_monitor import get_market_reference
        market_ref = get_market_reference(sku)
        price_context = ""
        if market_ref.get("median_price"):
            price_context = (
                f"Market Reference Constraints: We recently saw this product heavily discounted at ₹{market_ref['lowest_price']} ({market_ref['lowest_source']}). "
                f"The general market median is ₹{market_ref['median_price']}. "
                f"If you ask for a price, explicitly mention the ₹{market_ref['lowest_price']} external reference naturally to pressure them downwards!"
            )

        # Draft outreach message using Gemini
        message = await self._draft_outreach(product_name, top_supplier, relationship, price_context)

        # Log the outreach as a WhatsApp message
        negotiation_id = f"neg_{sku}_{supplier_id}_{int(time.time())}"
        outreach_entry = {
            "negotiation_id": negotiation_id,
            "direction": "outbound",
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "product_name": product_name,
            "message": message,
            "timestamp": time.time(),
        }
        self.message_log.append(outreach_entry)

        # Track active negotiation
        self.active_negotiations[negotiation_id] = {
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "product_name": product_name,
            "sku": sku,
            "ranked_suppliers": ranked,
            "current_supplier_index": 0,
            "attempt": 1,
            "outreach_message": message,
            "status": "awaiting_reply",
            "started_at": time.time(),
        }

        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="outreach_sent",
                decision=f"Sent WhatsApp outreach to {supplier_name} for {product_name}",
                reasoning=f"Top-ranked supplier (Rank #{top_supplier.get('rank', 1)}). {top_supplier.get('reasoning', '')}",
                outcome=json.dumps({"message": message, "negotiation_id": negotiation_id}, default=str),
                status="success",
                metadata={"supplier_id": supplier_id, "product": product_name},
            )

        return {
            "status": "outreach_sent",
            "negotiation_id": negotiation_id,
            "supplier": supplier_name,
            "message": message,
            "whatsapp_thread": [outreach_entry],
        }

    async def _handle_reply(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse a supplier's reply — the most impressive demo moment."""
        negotiation_id = data.get("negotiation_id", "")
        raw_reply = data.get("message", data.get("reply", ""))
        supplier_name = data.get("supplier_name", "Unknown")
        supplier_id = data.get("supplier_id", "")

        # Log inbound message
        reply_entry = {
            "negotiation_id": negotiation_id,
            "direction": "inbound",
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "message": raw_reply,
            "timestamp": time.time(),
        }
        self.message_log.append(reply_entry)

        # Parse the reply with Gemini
        parsed = await self._parse_reply(raw_reply, supplier_name)

        negotiation = self.active_negotiations.get(negotiation_id, {})

        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="reply_parsed",
                decision=f"Parsed reply from {supplier_name}",
                reasoning=parsed.get("reasoning", ""),
                outcome=json.dumps(parsed, default=str),
                status="success",
                metadata={
                    "raw_reply": raw_reply,
                    "missing_fields": parsed.get("missing_fields", []),
                    "needs_clarification": parsed.get("needs_clarification", False),
                },
            )

        # If clarification needed — draft and send follow-up
        if parsed.get("needs_clarification"):
            clarification = parsed.get("clarification_message", "")
            if not clarification:
                clarification = await self._draft_clarification(raw_reply, parsed.get("missing_fields", []))

            clarification_entry = {
                "negotiation_id": negotiation_id,
                "direction": "outbound",
                "supplier_id": supplier_id,
                "supplier_name": supplier_name,
                "message": clarification,
                "timestamp": time.time(),
                "type": "clarification",
            }
            self.message_log.append(clarification_entry)

            if self.audit:
                await self.audit.log(
                    skill=self.name,
                    event_type="clarification_sent",
                    decision=f"Sent clarification to {supplier_name}",
                    reasoning=f"Missing fields: {', '.join(parsed.get('missing_fields', []))}. Original reply was partial/unclear.",
                    outcome=json.dumps({
                        "original_reply": raw_reply,
                        "missing": parsed.get("missing_fields", []),
                        "clarification": clarification,
                    }, default=str),
                    status="success",
                )

            if negotiation_id in self.active_negotiations:
                self.active_negotiations[negotiation_id]["status"] = "clarification_sent"
                self.active_negotiations[negotiation_id]["attempt"] += 1

            return {
                "status": "clarification_sent",
                "negotiation_id": negotiation_id,
                "parsed": parsed,
                "clarification_message": clarification,
                "whatsapp_thread": self._get_thread(negotiation_id),
            }

        # Reply is complete — prepare deal for approval
        deal = parsed.get("parsed", {})
        product_name = negotiation.get("product_name", data.get("product_name", "Unknown"))

        if negotiation_id in self.active_negotiations:
            self.active_negotiations[negotiation_id]["status"] = "deal_ready"
            self.active_negotiations[negotiation_id]["deal"] = deal

        # Update supplier memory
        if self.memory and supplier_id:
            history = await self.memory.get(f"supplier:{supplier_id}:history") or {}
            if not isinstance(history, dict):
                history = {}
            history["last_negotiation"] = {
                "timestamp": time.time(),
                "product": product_name,
                "deal": deal,
            }
            await self.memory.set(f"supplier:{supplier_id}:history", history)

        result = {
            "status": "deal_ready",
            "negotiation_id": negotiation_id,
            "supplier_name": supplier_name,
            "product_name": product_name,
            "deal": deal,
            "whatsapp_thread": self._get_thread(negotiation_id),
            "needs_approval": True,
            "approval_id": f"deal_{negotiation_id}",
            "approval_reason": f"Supplier deal ready: {supplier_name} for {product_name}",
            "approval_details": {
                "supplier": supplier_name,
                "product": product_name,
                "price_per_unit": deal.get("price_per_unit"),
                "min_order_qty": deal.get("min_order_qty"),
                "delivery_days": deal.get("delivery_days"),
                "conditions": deal.get("conditions"),
            },
            "on_approval_event": {
                "type": "deal_confirmed",
                "data": {
                    "supplier_id": supplier_id,
                    "supplier_name": supplier_name,
                    "product_name": product_name,
                    "sku": negotiation.get("sku", ""),
                    "deal": deal,
                },
            },
        }

        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="deal_ready",
                decision=f"Deal ready with {supplier_name} for {product_name}",
                reasoning=parsed.get("reasoning", ""),
                outcome=json.dumps(result["approval_details"], default=str),
                status="pending_approval",
            )

        return result

    def _get_thread(self, negotiation_id: str) -> list[dict]:
        return [m for m in self.message_log if m.get("negotiation_id") == negotiation_id]

    async def _draft_outreach(self, product_name: str, supplier: dict, relationship: dict, price_context: str = "") -> str:
        if not self.client:
            import os
            api_key = os.environ.get("GEMINI_API_KEY", "")
            if api_key:
                self.client = genai.Client(api_key=api_key)
            else:
                return self._template_outreach(product_name, supplier)

        prompt = f"""{OUTREACH_SYSTEM_PROMPT}

Draft a WhatsApp message to this supplier:
Supplier: {supplier.get('supplier_name', 'Unknown')}
Product needed: {product_name}
Past relationship: {json.dumps(relationship, default=str) if relationship else 'First time ordering'}
{price_context}

Write the message only, no explanation."""

        try:
            response = await self.client.aio.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            logger.warning("Negotiation outreach draft failed: %s", e)
            return self._template_outreach(product_name, supplier)

    def _template_outreach(self, product_name: str, supplier: dict) -> str:
        return (
            f"Hi {supplier.get('supplier_name', 'there')}, this is from RetailOS Supermart. "
            f"We need to restock {product_name}. Could you share your best price per unit, "
            f"minimum order quantity, and expected delivery time? Thanks!"
        )

    async def _parse_reply(self, raw_reply: str, supplier_name: str) -> dict[str, Any]:
        if not self.client:
            import os
            api_key = os.environ.get("GEMINI_API_KEY", "")
            if api_key:
                self.client = genai.Client(api_key=api_key)
            else:
                return self._fallback_parse(raw_reply)

        prompt = f"""{PARSE_REPLY_PROMPT}

Supplier name: {supplier_name}
Their reply (may be Hinglish, messy, or partial):
"{raw_reply}"

Parse this reply and identify what information is present and what's missing."""

        try:
            response = await self.client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )

            text = response.text
            try:
                if "```json" in text:
                    parts = text.split("```json")
                    if len(parts) > 1:
                        text = parts[1].split("```")[0]
                elif "```" in text:
                    parts = text.split("```")
                    if len(parts) > 2:
                        text = parts[1]
            except (IndexError, ValueError):
                pass

            return json.loads(text.strip())
        except Exception as e:
            logger.warning("Negotiation reply parse failed: %s", e)
            return self._fallback_parse(raw_reply)

    def _fallback_parse(self, raw_reply: str) -> dict[str, Any]:
        """Simple regex-based extraction when Gemini is unavailable."""
        import re
        
        reply_lower = raw_reply.lower()
        
        # Simple extraction logic
        price_match = re.search(r'(?:rs|inr|₹)\s*(\d+)', reply_lower)
        qty_match = re.search(r'(\d+)\s*units?', reply_lower)
        days_match = re.search(r'(\d+)\s*days?', reply_lower)
        
        price = int(price_match.group(1)) if price_match else None
        qty = int(qty_match.group(1)) if qty_match else None
        days = int(days_match.group(1)) if days_match else None
        
        missing = []
        if price is None: missing.append("price_per_unit")
        if qty is None: missing.append("min_order_qty")
        if days is None: missing.append("delivery_days")
        
        return {
            "parsed": {
                "price_per_unit": price,
                "min_order_qty": qty,
                "delivery_date": None,
                "delivery_days": days,
                "conditions": None,
                "accepted": True if (price or qty or days) else None,
            },
            "missing_fields": missing,
            "needs_clarification": len(missing) > 0,
            "clarification_message": f"Thanks! Could you confirm the missing details: {', '.join(missing)}?" if missing else None,
            "reasoning": f"Fallback parse (Regex): extracted price={price}, qty={qty}, days={days}",
        }

    async def _draft_clarification(self, original_reply: str, missing_fields: list[str]) -> str:
        fields_text = ", ".join(missing_fields)
        return f"Thanks for the quick reply! Just need a couple more details — could you confirm the {fields_text}? That'll help us finalize the order."

    async def handle_timeout(self, negotiation_id: str) -> dict[str, Any]:
        """Handle supplier non-response — move to next supplier."""
        negotiation = self.active_negotiations.get(negotiation_id)
        if not negotiation:
            return {"error": "Negotiation not found"}

        idx = negotiation.get("current_supplier_index", 0) + 1
        ranked = negotiation.get("ranked_suppliers", [])

        if idx >= len(ranked):
            if self.audit:
                await self.audit.log(
                    skill=self.name,
                    event_type="all_suppliers_exhausted",
                    decision="All suppliers unresponsive — escalating to owner",
                    reasoning=f"Tried {len(ranked)} suppliers with no response",
                    outcome="Escalation needed",
                    status="escalated",
                )
            return {"status": "escalated", "message": "All suppliers unresponsive"}

        next_supplier = ranked[idx]
        negotiation["current_supplier_index"] = idx

        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="supplier_timeout",
                decision=f"Moving to next supplier: {next_supplier.get('supplier_name', 'Unknown')}",
                reasoning=f"Previous supplier did not respond within timeout window",
                outcome=f"Contacting supplier #{idx + 1}",
                status="rerouted",
            )

        return await self._start_negotiation({
            **negotiation,
            "ranked_suppliers": ranked[idx:],
        })
