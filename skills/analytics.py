import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from runtime.llm_client import get_llm_client
from runtime.utils import extract_json_from_llm

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent

from .base_skill import BaseSkill, SkillState


ANALYTICS_SYSTEM_PROMPT = """You are the analytics engine for RetailOS, an autonomous retail operations system.

Analyze the audit log entries and purchase data to identify patterns. Focus on:
1. Which offers converted to sales
2. Which suppliers are consistently late or unreliable
3. Which SKUs are being reordered too frequently (possible threshold issue)
4. Where margin is leaking (overpaying suppliers, too-frequent discounts)
5. Any anomalies worth flagging

Respond with valid JSON:
{
    "insights": [
        {
            "type": "supplier_reliability|conversion_rate|reorder_frequency|margin_leak|anomaly",
            "title": "Short insight title",
            "detail": "Full explanation",
            "recommendation": "What the system should do about this",
            "severity": "info|warning|critical"
        }
    ],
    "daily_summary": "2-3 sentence executive summary for the store owner",
    "system_recommendations": ["actionable items for the orchestrator to remember"]
}"""


class AnalyticsSkill(BaseSkill):
    """Runs daily analysis on audit logs and purchase data.

    The output becomes memory context for future decisions —
    this is what makes the system smarter over time.
    """

    def __init__(self, memory=None, audit=None):
        super().__init__(name="analytics", memory=memory, audit=audit)
        self.llm = get_llm_client()

    async def init(self) -> None:
        self.state = SkillState.RUNNING

    async def run(self, event: dict[str, Any]) -> dict[str, Any]:
        if not event:
            return {"status": "error", "message": "Event is None"}
        # Gather audit logs from the last 24 hours
        recent_logs = []
        if self.audit:
            recent_logs = await self.audit.get_logs(limit=100)

        # Gather inventory data
        inventory_summary = await self._get_inventory_summary()

        # Run analysis with Gemini
        analysis = await self._analyze(recent_logs, inventory_summary)

        # Store daily summary in memory for future decisions
        if self.memory:
            await self.memory.set("orchestrator:daily_summary", {
                "timestamp": time.time(),
                "summary": analysis.get("daily_summary", ""),
                "insights": analysis.get("insights", []),
                "recommendations": analysis.get("system_recommendations", []),
            })

            from brain.insight_writer import write_daily_insight
            await write_daily_insight(self.memory)

        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="daily_analysis",
                decision="Generated daily analytics report",
                reasoning=f"Analyzed {len(recent_logs)} audit log entries",
                outcome=json.dumps({
                    "insights_count": len(analysis.get("insights", [])),
                    "summary": analysis.get("daily_summary", ""),
                }, default=str),
                status="success",
                metadata={"full_analysis": analysis},
            )

        return {
            "status": "analysis_complete",
            "insights": analysis.get("insights", []),
            "daily_summary": analysis.get("daily_summary", ""),
            "recommendations": analysis.get("system_recommendations", []),
            "logs_analyzed": len(recent_logs),
        }

    async def _get_inventory_summary(self) -> dict:
        try:
            with open(BASE_DIR / "data" / "mock_inventory.json", "r") as f:
                inventory = json.load(f)
            low_stock = [
                item for item in inventory
                if item.get("current_stock", 0) <= item.get("reorder_threshold", 0)
            ]
            return {
                "total_skus": len(inventory),
                "low_stock_count": len(low_stock),
                "low_stock_items": [
                    {"name": str(i.get("product_name", "")), "stock": i.get("current_stock", 0), "threshold": i.get("reorder_threshold", 0)}
                    for i in list(low_stock[:10])
                ],
            }
        except Exception as e:
            logger.warning("Failed to load inventory summary: %s", e)
            return {"total_skus": 0, "low_stock_count": 0, "low_stock_items": []}

    async def _analyze(self, logs: list[dict], inventory: dict) -> dict[str, Any]:
        # Summarize logs for the prompt (keep it focused)
        log_summary = []
        for log in logs[:50]:
            log_summary.append({
                "skill": log.get("skill"),
                "event": log.get("event_type"),
                "decision": log.get("decision"),
                "reasoning": log.get("reasoning", "")[:200],
                "status": log.get("status"),
            })

        prompt = f"""{ANALYTICS_SYSTEM_PROMPT}

Analyze the following RetailOS audit logs and inventory data:

Recent audit log entries (last 24h):
{json.dumps(log_summary, indent=2, default=str)}

Inventory status:
{json.dumps(inventory, indent=2, default=str)}

Identify patterns, issues, and recommendations."""

        try:
            text = await self.llm.generate(prompt, timeout=30)
            return extract_json_from_llm(text)
        except Exception as e:
            logger.warning("Analytics Gemini call failed: %s", e)
            return self._fallback_analysis(logs, inventory)

    def _fallback_analysis(self, logs: list[dict], inventory: dict) -> dict[str, Any]:
        error_count = sum(1 for entry in logs if entry.get("status") == "error")
        success_count = sum(1 for entry in logs if entry.get("status") == "success")

        insights = []
        if error_count > 5:
            insights.append({
                "type": "anomaly",
                "title": "High error rate detected",
                "detail": f"{error_count} errors in last 24h",
                "recommendation": "Review error logs for recurring issues",
                "severity": "warning",
            })

        low_stock = inventory.get("low_stock_count", 0)
        if low_stock > 0:
            insights.append({
                "type": "reorder_frequency",
                "title": f"{low_stock} items below reorder threshold",
                "detail": "Multiple items need restocking",
                "recommendation": "Review reorder thresholds for frequently low items",
                "severity": "info",
            })

        return {
            "insights": insights,
            "daily_summary": f"Processed {len(logs)} events. {success_count} successful, {error_count} errors. {low_stock} items need restocking.",
            "system_recommendations": ["Monitor error rates", "Review low-stock items"],
        }
