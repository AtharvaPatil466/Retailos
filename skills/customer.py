import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from google import genai

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent

from .base_skill import BaseSkill, SkillState


MESSAGE_SYSTEM_PROMPT = """You are writing a personalized WhatsApp message from a supermart to a customer about a special deal.
The message should feel personal — reference the customer's actual purchase history.
Keep it under 100 words, friendly, and conversational. No formal language.
Write the message only, no explanation or formatting.

{template_context}"""

RE_ENGAGE_PROMPT = """You are writing a re-engagement WhatsApp message from a supermart to a lapsed customer.
This customer used to buy every {avg_gap} days but hasn't visited in {days_absent} days.
The message should feel personal, warm, and offer an incentive to return.
Keep it under 100 words. No formal language.
Write the message only, no explanation or formatting."""


class CustomerSkill(BaseSkill):
    """Segments customers and sends personalized WhatsApp offers.

    CALL 4 — Gemini writes personalized messages based on customer purchase history.
    Not templates — each message references the customer's actual behavior.
    """

    def __init__(self, memory=None, audit=None):
        super().__init__(name="customer", memory=memory, audit=audit)
        self.customers_data: list[dict] = []
        self.client: genai.Client | None = None

    async def init(self) -> None:
        try:
            with open(BASE_DIR / "data" / "mock_customers.json", "r") as f:
                self.customers_data = json.load(f)
        except FileNotFoundError:
            self.customers_data = []
        self.state = SkillState.RUNNING

    async def run(self, event: dict[str, Any]) -> dict[str, Any]:
        if not event:
            return {"status": "error", "message": "Event is None"}
        
        event_type = event.get("type", "")
        
        # Handle churn risk re-engagement
        if event_type == "churn_risk":
            return await self._handle_churn_risk(event.get("data", {}))
            
        data = event.get("data", event.get("params", {}))
        if not data:
            data = {}
        product_name = data.get("product_name", "Unknown")
        category = data.get("category", "")
        sku = data.get("sku", "")
        deal = data.get("deal", {})
        discount = deal.get("discount", data.get("discount", "special pricing"))

        # Segment customers
        total_customers = len(self.customers_data)
        target = category or product_name
        if not target or not target.strip():
            return {
                "status": "no_target",
                "message": "No category or product specified for customer segmentation",
                "messages_sent": 0,
            }
        segment, criteria_log = self._segment_customers(target)

        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="customer_segmentation",
                decision=f"Segmented {total_customers} customers → {len(segment)} qualified",
                reasoning=json.dumps(criteria_log, indent=2),
                outcome=f"{len(segment)} customers will receive personalized offers",
                status="success",
                metadata={
                    "total_customers": total_customers,
                    "qualified": len(segment),
                    "product": product_name,
                    "criteria": criteria_log,
                },
            )

        # Generate personalized messages for each customer
        messages = []
        for customer in segment[:10]:  # Cap at 10 for demo
            message = await self._write_message(customer, product_name, discount)
            
            customer_id = customer.get("phone", customer.get("id", ""))
            message_id = f"msg_{customer_id}_{int(time.time())}"
            
            # Track the outbound message
            from brain.message_tracker import log_message_sent
            template_used = self._detect_template(message)
            log_message_sent(customer_id, message_id, template_used)
            
            msg_entry = {
                "customer_name": customer.get("name", "Customer"),
                "phone": customer.get("phone", ""),
                "message": message,
                "message_id": message_id,
                "template_used": template_used,
                "product": product_name,
                "timestamp": time.time(),
            }
            messages.append(msg_entry)

            # Update last_offer in memory
            if self.memory:
                await self.memory.set(
                    f"customer:{customer.get('phone', '')}:last_offer",
                    {"product": product_name, "message_id": message_id, "timestamp": time.time()},
                )

        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="offers_sent",
                decision=f"Sent {len(messages)} personalized offers for {product_name}",
                reasoning=f"Each message personalized using customer purchase history via Gemini",
                outcome=json.dumps([{"customer": m["customer_name"], "message": m["message"][:100]} for m in messages], default=str),
                status="success",
            )

        return {
            "status": "offers_sent",
            "product": product_name,
            "total_customers": total_customers,
            "qualified_customers": len(segment),
            "messages_sent": len(messages),
            "messages": messages,
            "segmentation_criteria": criteria_log,
        }

    def _segment_customers(self, category_or_product: str) -> tuple[list[dict], dict]:
        """Apply segmentation filter and log each criterion's impact."""
        now = time.time()
        ninety_days_ago = now - (90 * 86400)
        seven_days_ago = now - (7 * 86400)
        target = category_or_product.lower()

        criteria_log: dict[str, Any] = {
            "total_customers": len(self.customers_data),
            "criteria_applied": [],
        }

        # Criterion 1: Bought this category 2+ times in last 90 days
        after_criterion_1 = []
        for c in self.customers_data:
            purchases = c.get("purchase_history", [])
            relevant_count = sum(
                1 for p in purchases
                if (target in p.get("category", "").lower() or target in p.get("product", "").lower())
                and p.get("timestamp", 0) > ninety_days_ago
            )
            if relevant_count >= 2:
                after_criterion_1.append(c)

        applied_list: list[dict[str, Any]] = []
        applied_list.append({
            "criterion": f"Bought '{category_or_product}' category 2+ times in last 90 days",
            "before": len(self.customers_data),
            "after": len(after_criterion_1),
            "filtered_out": len(self.customers_data) - len(after_criterion_1),
        })
        criteria_log["criteria_applied"] = applied_list

        # Criterion 2: Not sent an offer for this category in last 7 days
        after_criterion_2 = []
        for c in after_criterion_1:
            last_offer = c.get("last_offer_timestamp", 0)
            last_offer_category = c.get("last_offer_category", "").lower()
            if last_offer_category != target or last_offer < seven_days_ago:
                after_criterion_2.append(c)

        applied_list.append({
            "criterion": "Not sent an offer for this category in last 7 days",
            "before": len(after_criterion_1),
            "after": len(after_criterion_2),
            "filtered_out": len(after_criterion_1) - len(after_criterion_2),
        })

        # Criterion 3: Opted in to WhatsApp communications
        after_criterion_3 = [c for c in after_criterion_2 if c.get("whatsapp_opted_in", False)]

        applied_list.append({
            "criterion": "Opted in to WhatsApp communications at billing",
            "before": len(after_criterion_2),
            "after": len(after_criterion_3),
            "filtered_out": len(after_criterion_2) - len(after_criterion_3),
        })

        criteria_log["final_count"] = len(after_criterion_3)

        return after_criterion_3, criteria_log

    async def _write_message(self, customer: dict, product_name: str, discount: Any) -> str:
        if not self.client:
            import os
            api_key = os.environ.get("GEMINI_API_KEY", "")
            if api_key:
                self.client = genai.Client(api_key=api_key)
            else:
                return self._template_message(customer, product_name, discount)

        # Build purchase context
        recent_purchases = customer.get("purchase_history", [])[-5:]
        purchase_summary = ", ".join(
            p.get("product", "item") for p in recent_purchases
        )

        # Inject template performance data
        from brain.conversion_scorer import get_template_context
        template_ctx = get_template_context()

        prompt = f"""{MESSAGE_SYSTEM_PROMPT.format(template_context=template_ctx if template_ctx else 'No template performance data yet.')}

Customer: {customer.get('name', 'Customer')}
Recent purchases: {purchase_summary}
Product on offer: {product_name}
Discount/deal: {discount}

Write a personalized WhatsApp message."""

        try:
            response = await self.client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            logger.warning("Customer message generation failed: %s", e)
            return self._template_message(customer, product_name, discount)

    def _template_message(self, customer: dict, product_name: str, discount: Any) -> str:
        name = customer.get("name", "there")
        return (
            f"Hi {name}! We just got a great deal on {product_name} — "
            f"{discount}. Since you've been picking this up regularly, "
            f"thought you'd want to know first. Want us to keep some aside for you?"
        )

    def _detect_template(self, message: str) -> str:
        """Simple heuristic to classify the message style for A/B tracking."""
        msg_lower = message.lower()
        if any(w in msg_lower for w in ["hurry", "limited", "last chance", "running out", "don't miss"]):
            return "urgency-based"
        elif any(w in msg_lower for w in ["discount", "% off", "save", "deal", "offer"]):
            return "discount-led"
        elif any(w in msg_lower for w in ["hi ", "hey ", "noticed you", "since you"]):
            return "personalized-name"
        else:
            return "general"

    async def _handle_churn_risk(self, data: dict[str, Any]) -> dict[str, Any]:
        """Generate a re-engagement message for an at-risk customer."""
        customer_id = data.get("customer_id", "")
        customer_name = data.get("customer_name", "Customer")
        avg_gap = data.get("avg_gap_days", 7)
        days_absent = data.get("days_absent", 14)

        # Find full customer data
        customer = None
        for c in self.customers_data:
            if c.get("phone") == customer_id or c.get("id") == customer_id:
                customer = c
                break

        if not customer:
            customer = {"name": customer_name, "phone": customer_id}

        message = await self._write_reengage_message(customer, avg_gap, days_absent)

        # Track the outbound message
        from brain.message_tracker import log_message_sent
        message_id = f"churn_{customer_id}_{int(time.time())}"
        log_message_sent(customer_id, message_id, "re-engagement")

        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="churn_reengage",
                decision=f"Sent re-engagement to {customer_name} (churn score: {data.get('churn_score', 'N/A')})",
                reasoning=f"Customer usually buys every {avg_gap} days but absent for {days_absent} days",
                outcome=message[:200],
                status="success",
            )

        return {
            "status": "reengage_sent",
            "customer_name": customer_name,
            "customer_id": customer_id,
            "message": message,
            "message_id": message_id,
            "churn_score": data.get("churn_score"),
        }

    async def _write_reengage_message(self, customer: dict, avg_gap: float, days_absent: float) -> str:
        if not self.client:
            import os
            api_key = os.environ.get("GEMINI_API_KEY", "")
            if api_key:
                self.client = genai.Client(api_key=api_key)
            else:
                name = customer.get("name", "there")
                return f"Hi {name}! We haven't seen you in a while and we miss you. Come back this week for a special 15% off your next purchase!"

        recent_purchases = customer.get("purchase_history", [])[-3:]
        purchase_summary = ", ".join(p.get("product", "item") for p in recent_purchases) if recent_purchases else "various items"

        prompt = f"""{RE_ENGAGE_PROMPT.format(avg_gap=avg_gap, days_absent=days_absent)}

Customer: {customer.get('name', 'Customer')}
Recent purchases: {purchase_summary}

Write a re-engagement WhatsApp message."""

        try:
            response = await self.client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            logger.warning("Re-engagement message generation failed: %s", e)
            name = customer.get("name", "there")
            return f"Hi {name}! We haven't seen you in a while and we miss you. Come back this week for a special 15% off your next purchase!"
