import json
import logging
import os
import time
from pathlib import Path
from typing import Any, cast

from google import genai

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent

from .base_skill import BaseSkill, SkillState


RANKING_SYSTEM_PROMPT = """You are a procurement analyst for a retail supermart. Given a list of suppliers and memory context about past orders, rank the top 2-3 suppliers with detailed reasoning.

{wastage_context}
{market_context}

Consider these factors:
1. Price per unit (lower is better)
2. Reliability score (1-5, higher is better)
3. Delivery time (fewer days is better)
4. Minimum order quantity (flexibility matters)
5. Past relationship from memory (reliable partners preferred)
6. Payment terms

Respond with valid JSON only:
{
    "ranked_suppliers": [
        {
            "rank": 1,
            "supplier_id": "...",
            "supplier_name": "...",
            "price_per_unit": 0.0,
            "delivery_days": 0,
            "min_order_qty": 0,
            "reasoning": "Detailed explanation of why this supplier was ranked here"
        }
    ],
    "overall_reasoning": "1-2 sentence summary of ranking logic"
}"""


class ProcurementSkill(BaseSkill):
    """Ranks suppliers for a given product using Gemini + memory context.

    CALL 2 — Gemini receives supplier list + memory of past orders
    and returns a ranked list with written reasoning per supplier.
    """

    def __init__(self, memory=None, audit=None):
        super().__init__(name="procurement", memory=memory, audit=audit)
        self.suppliers_data: list[dict] = []
        self.client: genai.Client | None = None

    async def init(self) -> None:
        try:
            with open(BASE_DIR / "data" / "mock_suppliers.json", "r") as f:
                self.suppliers_data = json.load(f)
        except FileNotFoundError:
            self.suppliers_data = []
        self.state = SkillState.RUNNING

    async def run(self, event: dict[str, Any]) -> dict[str, Any]:
        if not event:
            return {"status": "error", "message": "Event is None"}
            
        data = event.get("data", event.get("params", {}))
        if not data:
            data = {}
            
        product_name = data.get("product_name", "Unknown Product")
        sku = data.get("sku", "")
        category = data.get("category", "")
        daily_sales = data.get("daily_sales_rate", 10)
        lead_time = data.get("lead_time_days", 7)

        # Fetch wastage context
        from brain.reorder_optimizer import get_optimized_reorder_quantity
        opt_data = get_optimized_reorder_quantity(sku, daily_sales, lead_time)
        
        wastage_context = (
            f"--- SYSTEM OPTIMIZATION DATA ---\n"
            f"Product: {product_name} ({sku})\n"
            f"Current generic logic suggests: {opt_data['base_quantity']} units\n"
            f"Wastage-adjusted suggestion: {opt_data['optimized_quantity']} units\n"
            f"Reason: {opt_data['wastage_rate']*100:.1f}% wastage rate over last 30 days\n"
            f"Current sales velocity: {opt_data['avg_daily_sales']} units/day\n"
            f"Take this adjusted suggestion strongly into account.\n"
            f"--------------------------------"
        )
        
        # Find suppliers that carry this product/category
        matching_suppliers = self._find_suppliers(product_name, category)

        # Analyze Quotes vs Market Data
        from brain.price_monitor import get_market_reference
        from brain.price_analyzer import format_supplier_verdict
        
        market_ref = get_market_reference(sku)
        market_context_str = ""
        
        if market_ref.get("median_price"):
            market_context_str += (
                f"--- MARKET INTELLIGENCE ---\n"
                f"Median market price:  ₹{market_ref['median_price']}/unit  (confidence: {market_ref['confidence']})\n"
                f"Lowest available:     ₹{market_ref['lowest_price']}/unit  ({market_ref['lowest_source']})\n\n"
            )
            for supplier in matching_suppliers:
                sp = supplier.get("price_per_unit", None)
                if sp:
                    market_context_str += format_supplier_verdict(supplier["supplier_name"], float(sp), market_ref) + "\n"
            market_context_str += "---------------------------\n"

        if not matching_suppliers:
            return {
                "status": "no_suppliers",
                "product": product_name,
                "message": f"No suppliers found for {product_name}",
            }

        # Fetch memory context about past orders
        memory_context = {}
        if self.memory:
            for supplier in matching_suppliers:
                sid = supplier["supplier_id"]
                history = await self.memory.get(f"supplier:{sid}:history")
                
                from brain.context_builder import get_supplier_context
                trust_context = get_supplier_context(sid)
                
                if history:
                    history["trust_data"] = trust_context
                    memory_context[sid] = history
                else:
                    memory_context[sid] = {"trust_data": trust_context}
            # Get daily summary for broader context
            daily = await self.memory.get("orchestrator:daily_summary")
            if daily:
                memory_context["daily_summary"] = daily

        # Call Gemini for ranking
        ranking = await self._rank_with_gemini(product_name, matching_suppliers, memory_context, wastage_context, market_context_str)

        # Store the ranking decision in memory
        if self.memory:
            await self.memory.set(f"product:{sku}:last_procurement", {
                "timestamp": time.time(),
                "product": product_name,
                "ranking": ranking,
            })

        # Prepare approval request
        top_supplier = ranking["ranked_suppliers"][0] if ranking.get("ranked_suppliers") else None

        result = {
            "product_name": product_name,
            "sku": sku,
            "suppliers_evaluated": len(matching_suppliers),
            "ranking": ranking,
            "needs_approval": True,
            "approval_id": f"procurement_{sku}_{int(time.time())}",
            "approval_reason": f"Procurement ranking ready for {product_name}",
            "approval_details": {
                "product": product_name,
                "top_supplier": top_supplier,
                "total_evaluated": len(matching_suppliers),
                "reasoning": ranking.get("overall_reasoning", ""),
            },
            "on_approval_event": {
                "type": "procurement_approved",
                "data": {
                    "product_name": product_name,
                    "sku": sku,
                    "ranked_suppliers": ranking.get("ranked_suppliers", []),
                },
            },
        }

        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="supplier_ranking",
                decision=f"Ranked {len(ranking.get('ranked_suppliers', []))} suppliers for {product_name}",
                reasoning=ranking.get("overall_reasoning", ""),
                outcome=json.dumps(ranking.get("ranked_suppliers", [])[:3], default=str),
                status="success",
            )

        return result

    def _find_suppliers(self, product_name: str, category: str) -> list[dict]:
        matches = []
        product_lower = product_name.lower()
        category_lower = category.lower() if category else ""

        for supplier in self.suppliers_data:
            products = [p.lower() for p in supplier.get("products", [])]
            categories = [c.lower() for c in supplier.get("categories", [])]

            if any(product_lower in p for p in products) or any(category_lower in c for c in categories):
                matches.append(supplier)

        # If no exact matches, return all suppliers (demo fallback)
        return matches if matches else list(self.suppliers_data[:5])

    async def _rank_with_gemini(
        self, product_name: str, suppliers: list[dict], memory_context: dict, wastage_context: str, market_context: str = ""
    ) -> dict[str, Any]:
        if not self.client:
            import os
            api_key = os.environ.get("GEMINI_API_KEY", "")
            if api_key:
                self.client = genai.Client(api_key=api_key)
            else:
                return self._fallback_ranking(suppliers)

        prompt = f"""{RANKING_SYSTEM_PROMPT.replace("{wastage_context}", wastage_context).replace("{market_context}", market_context)}

Product needing procurement: {product_name}

Available suppliers:
{json.dumps(suppliers, indent=2, default=str)}

Past order history and context:
{json.dumps(memory_context, indent=2, default=str) if memory_context else "No past history available."}

Rank the top 2-3 suppliers with detailed reasoning."""

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
            logger.warning("Procurement Gemini ranking failed: %s", e)
            if self.audit:
                await self.audit.log(
                    skill=self.name,
                    event_type="gemini_ranking_error",
                    decision="Falling back to rule-based ranking",
                    reasoning=str(e),
                    outcome="Using price + reliability heuristic",
                    status="error",
                )
            return self._fallback_ranking(suppliers)

    def _fallback_ranking(self, suppliers: list[dict]) -> dict[str, Any]:
        """Simple rule-based ranking when Gemini is unavailable."""
        scored = []
        for s in suppliers:
            score = (s.get("reliability_score", 3) * 20) - (s.get("price_per_unit", 100)) - (s.get("delivery_days", 7) * 2)
            scored.append((score, s))

        scored.sort(key=lambda x: x[0], reverse=True)

        ranked = []
        top_scored = cast(list[Any], scored[:3])
        for i, item in enumerate(top_scored):
            score, s = item
            ranked.append({
                "rank": i + 1,
                "supplier_id": s.get("supplier_id"),
                "supplier_name": s.get("supplier_name"),
                "price_per_unit": s.get("price_per_unit", 0),
                "delivery_days": s.get("delivery_days", 0),
                "min_order_qty": s.get("min_order_qty", 0),
                "reasoning": f"Score: {float(score):.1f} (reliability: {s.get('reliability_score', 0)}, price: ₹{s.get('price_per_unit', 0)}, delivery: {s.get('delivery_days', 0)} days)",
            })

        return {
            "ranked_suppliers": ranked,
            "overall_reasoning": "Fallback ranking based on composite score (reliability × 20 - price - delivery_days × 2)",
        }
