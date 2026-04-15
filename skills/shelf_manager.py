import asyncio
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

from runtime.llm_client import get_llm_client
from runtime.utils import extract_json_from_llm

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent

from .base_skill import BaseSkill, SkillState


SHELF_OPTIMIZATION_PROMPT = """You are a retail shelf optimization analyst for an Indian supermart. Given the current shelf layout, sales velocity data, and zone fitness scores, suggest product placement changes to maximize revenue.

Rules:
1. HIGH-VELOCITY products (≥15 units/day) should be in high_traffic zones and at eye_level
2. SLOW-MOVING products (<5 units/day) should NOT occupy high_traffic zones — move them to standard zones
3. NEVER suggest moving refrigerated/dairy products out of refrigerated zones or frozen products out of freezer zones
4. Only suggest moves where the destination zone has available slots
5. Prioritize moves with the biggest fitness improvement
6. Maximum 8 suggestions per run

Respond with valid JSON only:
{
    "suggestions": [
        {
            "type": "move",
            "sku": "SKU-XXX",
            "product_name": "Product Name",
            "from_zone": "Z-XX",
            "to_zone": "Z-XX",
            "suggested_shelf_level": "eye_level|upper|lower|bottom",
            "reason": "1-2 sentence explanation with expected impact",
            "priority": "high|medium|low",
            "expected_velocity_impact": "+15%"
        }
    ],
    "overall_reasoning": "2-3 sentence summary of optimization strategy"
}"""


# Zone types that restrict product movement
COLD_ZONE_TYPES = {"refrigerated", "freezer"}


class ShelfManagerSkill(BaseSkill):
    """Analyzes shelf placements and suggests optimizations based on sales velocity.

    Uses Gemini to generate intelligent placement suggestions. All suggestions
    go through the approvals queue — never auto-applied.
    """

    def __init__(self, memory=None, audit=None):
        super().__init__(name="shelf_manager", memory=memory, audit=audit)
        self.shelf_data: dict = {}
        self.llm = get_llm_client()

    async def init(self) -> None:
        try:
            with open(BASE_DIR / "data" / "mock_shelf_zones.json", "r") as f:
                self.shelf_data = json.load(f)
        except FileNotFoundError:
            self.shelf_data = {"zones": [], "ai_suggestions": []}
        self.state = SkillState.RUNNING

    def _persist_shelf_data(self) -> None:
        with open(BASE_DIR / "data" / "mock_shelf_zones.json", "w") as f:
            json.dump(self.shelf_data, f, indent=2)
            f.write("\n")

    async def clear_suggestions(self) -> None:
        self.shelf_data["ai_suggestions"] = []
        self._persist_shelf_data()

    async def run(self, event: dict[str, Any]) -> dict[str, Any]:
        if not event:
            return {"status": "error", "message": "Event is None"}

        event_type = event.get("type", "")
        data = event.get("data", event.get("params", {}))

        if event_type == "shelf_placement_approved":
            return await self._apply_approved_moves(data)
        else:
            # Default: shelf_optimization
            return await self._run_optimization()

    async def _run_optimization(self) -> dict[str, Any]:
        """Analyze velocity data and generate AI shelf placement suggestions."""
        from brain.velocity_analyzer import get_velocity_report

        report = get_velocity_report()

        # Reload shelf data from disk for current state
        try:
            with open(BASE_DIR / "data" / "mock_shelf_zones.json", "r") as f:
                self.shelf_data = json.load(f)
        except Exception:
            pass

        # Build zone availability map
        zone_availability = {}
        zone_type_map = {}
        for zone in self.shelf_data.get("zones", []):
            zid = zone["zone_id"]
            zone_availability[zid] = zone["total_slots"] - len(zone["products"])
            zone_type_map[zid] = zone["zone_type"]

        # Try Gemini first, fall back to rules
        suggestions = await self._optimize_with_gemini(report, zone_availability)
        if not suggestions:
            suggestions = self._fallback_suggestions(report, zone_availability, zone_type_map)

        # Validate all suggestions
        validated = self._validate_suggestions(suggestions, zone_type_map, zone_availability)

        if not validated:
            await self.clear_suggestions()
            return {
                "status": "no_changes",
                "message": "All products are well-placed. No optimization needed.",
            }

        reasoning = validated[0].get(
            "_overall_reasoning",
            "Optimize product placement for maximum revenue",
        )
        cleaned_suggestions = [
            {k: v for k, v in suggestion.items() if k != "_overall_reasoning"}
            for suggestion in validated
        ]
        self.shelf_data["ai_suggestions"] = cleaned_suggestions
        self._persist_shelf_data()

        result = {
            "status": "suggestions_ready",
            "suggestion_count": len(cleaned_suggestions),
            "suggestions": cleaned_suggestions,
            "velocity_summary": report["summary"],
            "needs_approval": True,
            "approval_id": f"shelf_opt_{int(time.time())}",
            "approval_reason": f"AI suggests {len(cleaned_suggestions)} shelf placement changes based on 30-day sales velocity",
            "approval_details": {
                "type": "shelf_optimization",
                "suggestion_count": len(cleaned_suggestions),
                "suggestions": cleaned_suggestions,
                "velocity_summary": report["summary"],
                "reasoning": reasoning,
            },
            "on_approval_event": {
                "type": "shelf_placement_approved",
                "data": {
                    "moves": cleaned_suggestions,
                },
            },
        }

        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="shelf_optimization",
                decision=f"Generated {len(cleaned_suggestions)} shelf placement suggestions",
                reasoning=f"Avg zone fitness: {report['summary']['avg_zone_fitness']}, "
                          f"Fast movers: {report['summary']['fast_movers']}, "
                          f"Slow movers: {report['summary']['slow_movers']}",
                outcome=json.dumps(cleaned_suggestions[:3], default=str),
                status="success",
            )

        return result

    async def _optimize_with_gemini(self, report: dict, zone_availability: dict) -> list[dict]:
        """Use Gemini to generate intelligent placement suggestions."""
        # Only send misplaced products (fitness < 0.7) to keep prompt focused
        misplaced = [p for p in report["products"] if p.get("zone_fitness") is not None and p["zone_fitness"] < 0.7]
        well_placed_count = len([p for p in report["products"] if p.get("zone_fitness") is not None and p["zone_fitness"] >= 0.7])

        if not misplaced:
            return []

        zones_summary = []
        for zone in self.shelf_data.get("zones", []):
            zid = zone["zone_id"]
            zones_summary.append({
                "zone_id": zid,
                "zone_name": zone["zone_name"],
                "zone_type": zone["zone_type"],
                "total_slots": zone["total_slots"],
                "available_slots": zone_availability.get(zid, 0),
                "current_products": [{"sku": p["sku"], "product_name": p["product_name"], "shelf_level": p.get("shelf_level", "lower")} for p in zone["products"]],
            })

        prompt = f"""{SHELF_OPTIMIZATION_PROMPT}

Current store zones:
{json.dumps(zones_summary, indent=2)}

Products needing repositioning (low zone fitness):
{json.dumps(misplaced, indent=2)}

Summary: {well_placed_count} products are well-placed. Focus on the {len(misplaced)} misplaced products above.

Generate placement suggestions."""

        try:
            text = await self.llm.generate(prompt, timeout=30)
            parsed = extract_json_from_llm(text)
            suggestions = parsed.get("suggestions", [])
            overall = parsed.get("overall_reasoning", "")

            # Attach overall reasoning to first suggestion for passing through
            if suggestions:
                suggestions[0]["_overall_reasoning"] = overall

            return suggestions

        except Exception as e:
            logger.warning("Shelf optimization Gemini call failed: %s", e)
            if self.audit:
                await self.audit.log(
                    skill=self.name,
                    event_type="gemini_shelf_error",
                    decision="Falling back to rule-based suggestions",
                    reasoning=str(e),
                    outcome="Using velocity-based heuristic",
                    status="error",
                )
            return []

    def _fallback_suggestions(self, report: dict, zone_availability: dict, zone_type_map: dict) -> list[dict]:
        """Rule-based suggestions when Gemini is unavailable."""
        available_slots = zone_availability.copy()
        suggestions = []

        # Find high-traffic zones with available slots
        high_traffic_zones = [zid for zid, ztype in zone_type_map.items() if ztype == "high_traffic" and available_slots.get(zid, 0) > 0]
        standard_zones = [zid for zid, ztype in zone_type_map.items() if ztype == "standard" and available_slots.get(zid, 0) > 0]

        for product in report["products"]:
            if len(suggestions) >= 6:
                break

            fitness = product.get("zone_fitness")
            if fitness is None or fitness >= 0.7:
                continue

            current_zone_type = product.get("current_zone_type", "")
            classification = product["classification"]

            # Don't move cold-chain products out of cold zones
            if current_zone_type in COLD_ZONE_TYPES:
                continue

            if classification == "fast_mover" and current_zone_type != "high_traffic" and high_traffic_zones:
                target = high_traffic_zones[0]
                suggestions.append({
                    "type": "move",
                    "sku": product["sku"],
                    "product_name": product["product_name"],
                    "from_zone": product["current_zone_id"],
                    "to_zone": target,
                    "suggested_shelf_level": "eye_level",
                    "reason": f"Fast mover ({product['velocity_score']}/day) in {current_zone_type} zone. Move to high-traffic for better visibility.",
                    "priority": "high",
                    "expected_velocity_impact": "+15%",
                })
                available_slots[target] -= 1
                if available_slots[target] <= 0:
                    high_traffic_zones.remove(target)

            elif classification == "slow_mover" and current_zone_type == "high_traffic" and standard_zones:
                target = standard_zones[0]
                suggestions.append({
                    "type": "move",
                    "sku": product["sku"],
                    "product_name": product["product_name"],
                    "from_zone": product["current_zone_id"],
                    "to_zone": target,
                    "suggested_shelf_level": "lower",
                    "reason": f"Slow mover ({product['velocity_score']}/day) occupying prime high-traffic space. Free slot for faster products.",
                    "priority": "medium",
                    "expected_velocity_impact": "neutral",
                })
                available_slots[target] -= 1
                if available_slots[target] <= 0:
                    standard_zones.remove(target)

        if suggestions:
            suggestions[0]["_overall_reasoning"] = "Rule-based optimization: move fast movers to high-traffic zones, free prime space from slow movers."

        return suggestions

    def _validate_suggestions(self, suggestions: list[dict], zone_type_map: dict, zone_availability: dict) -> list[dict]:
        """Validate suggestions — enforce cold-chain constraints and slot availability."""
        # Build a set of products currently in cold zones
        cold_zone_products = set()
        for zone in self.shelf_data.get("zones", []):
            if zone["zone_type"] in COLD_ZONE_TYPES:
                for p in zone["products"]:
                    cold_zone_products.add(p["sku"])

        validated = []
        used_slots: dict[str, int] = {}

        for s in suggestions:
            to_zone = s.get("to_zone")
            sku = s.get("sku")

            # Skip if moving cold-chain product to non-cold zone
            if sku in cold_zone_products:
                to_type = zone_type_map.get(to_zone, "standard")
                if to_type not in COLD_ZONE_TYPES:
                    continue

            # Check slot availability (accounting for moves already in this batch)
            if to_zone:
                used = used_slots.get(to_zone, 0)
                available = zone_availability.get(to_zone, 0) - used
                if available <= 0:
                    continue
                used_slots[to_zone] = used + 1

            validated.append(s)

        return validated

    async def _apply_approved_moves(self, data: dict) -> dict[str, Any]:
        """Apply approved shelf placement changes to the data file."""
        moves = data.get("moves", [])
        if not moves:
            return {"status": "no_moves", "message": "No moves to apply"}

        # Reload current state
        try:
            with open(BASE_DIR / "data" / "mock_shelf_zones.json", "r") as f:
                self.shelf_data = json.load(f)
        except Exception:
            return {"status": "error", "message": "Failed to read shelf data"}

        zones_by_id = {z["zone_id"]: z for z in self.shelf_data.get("zones", [])}
        applied = []
        skipped = []
        today = date.today().isoformat()

        for move in moves:
            sku = move.get("sku")
            from_zone_id = move.get("from_zone")
            to_zone_id = move.get("to_zone")
            shelf_level = move.get("suggested_shelf_level", "lower")

            if not sku or not from_zone_id:
                continue

            from_zone = zones_by_id.get(from_zone_id)
            if not from_zone:
                continue

            to_zone = None
            if to_zone_id:
                to_zone = zones_by_id.get(to_zone_id)
                if not to_zone:
                    skipped.append({
                        "sku": sku,
                        "product_name": move.get("product_name", ""),
                        "from_zone": from_zone_id,
                        "to_zone": to_zone_id,
                        "reason": "Destination zone not found",
                    })
                    continue
                if len(to_zone["products"]) >= to_zone["total_slots"]:
                    skipped.append({
                        "sku": sku,
                        "product_name": move.get("product_name", ""),
                        "from_zone": from_zone_id,
                        "to_zone": to_zone_id,
                        "reason": "Destination zone is full",
                    })
                    continue

            # Remove from source zone
            product_entry = None
            for i, p in enumerate(from_zone["products"]):
                if p["sku"] == sku:
                    product_entry = from_zone["products"].pop(i)
                    break

            if not product_entry:
                continue

            # If it's a move (not a remove), add to destination
            if to_zone_id:
                product_entry["placed_date"] = today
                product_entry["days_here"] = 0
                product_entry["shelf_level"] = shelf_level
                to_zone["products"].append(product_entry)

            applied.append({
                "sku": sku,
                "product_name": move.get("product_name", product_entry.get("product_name", "")),
                "from_zone": from_zone_id,
                "to_zone": to_zone_id,
            })

        self.shelf_data["ai_suggestions"] = []
        self._persist_shelf_data()

        # Store placement history in memory
        if self.memory:
            for move in applied:
                await self.memory.set(f"shelf:{move['sku']}:placement_history", {
                    "last_move": today,
                    "from_zone": move["from_zone"],
                    "to_zone": move["to_zone"],
                    "timestamp": time.time(),
                })

        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="shelf_placement_applied",
                decision=f"Applied {len(applied)} shelf placement changes",
                reasoning="Owner approved AI shelf optimization suggestions",
                outcome=json.dumps(applied, default=str),
                status="success",
            )

        return {
            "status": "applied",
            "moves_applied": len(applied),
            "details": applied,
            "skipped": skipped,
        }
