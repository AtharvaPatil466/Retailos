# skills/scheduling.py
import asyncio
import time
import json
from typing import Any
from runtime.llm_client import get_llm_client
from .base_skill import BaseSkill, SkillState

FORMAT_PROMPT = """You are a smart retail store manager formatting a staff scheduling recommendation.
We mapped next day's predicted footfall and calculated the adequacy of the current staff schedule.

Follow this exact format closely:
Tomorrow — {day} {date}
Predicted footfall: {predicted_footfall} customers ({increase_pct}% vs normal {day})
Reason: {reason}

Hour-by-hour adequacy:
  [Insert hour blocks formatted like '10am-12pm  ✓ Adequate   (2 staff, ~30 customers/hr)' or '12pm-2pm   ✗ Understaffed (2 staff, ~55 customers/hr)']

Recommendation:
  [Specific suggestions to add/remove staff during understaffed/overstaffed gaps]

Output ONLY the fully structured markdown report. Do not add any extra prefaces."""

class SchedulingSkill(BaseSkill):
    """Sixth autonomous module targeting physical resourcing management dynamically."""

    def __init__(self, memory=None, audit=None):
        super().__init__(name="scheduling", memory=memory, audit=audit)
        self.llm = get_llm_client()

    async def init(self) -> None:
        self.state = SkillState.RUNNING

    async def run(self, event: dict[str, Any]) -> dict[str, Any]:
        event_type = event.get("type", "")
        data = event.get("data", {})

        if event_type in ["shift_review", "festival_alert"]:
            return await self._review_shifts(data)
        return {"status": "ignored"}

    def _format_am_pm(self, hour: int) -> str:
        if hour == 0:
            return "12am"
        if hour == 12:
            return "12pm"
        if hour > 12:
            return f"{hour-12}pm"
        return f"{hour}am"

    def _build_raw_fallback(self, target_date, adequacy) -> str:
        blocks_text = ""
        for b in adequacy["hourly_blocks"]:
            icon = "✓" if b["status"] == "Adequate" else "✗"
            blocks_text += f"  {self._format_am_pm(b['start'])}-{self._format_am_pm(b['end'])}   {icon} {b['status']}   ({b['staff']} staff, ~{b['avg_footfall']} customers/hr)\n"

        return f"""Tomorrow — {target_date.strftime('%A')} {target_date.strftime('%d %b')}
Predicted footfall: {adequacy['predicted_footfall']} customers ({adequacy['increase_pct']}% vs normal)
Reason: Fallback standard pipeline formatting

Hour-by-hour adequacy:
{blocks_text}
Recommendation:
  Review the blocks flagged as 'Understaffed' and consider extending overlap hour shifts manually."""

    async def _review_shifts(self, data: dict[str, Any]) -> dict[str, Any]:
        from datetime import date
        from brain.shift_optimizer import calculate_adequacy

        target_date_str = data.get("target_date")
        if target_date_str:
            target_date = date.fromisoformat(target_date_str)
        else:
            return {"status": "error", "message": "Missing target_date"}

        adequacy = calculate_adequacy(target_date)

        reason = "Standard baseline prediction"
        if adequacy["festival"]:
            reason = f"Proximity to {adequacy['festival']['festival_name']} surge multiplier"

        blocks_text = ""
        for b in adequacy["hourly_blocks"]:
            blocks_text += f"{self._format_am_pm(b['start'])}-{self._format_am_pm(b['end'])} | {b['status']} | {b['staff']} staff (~{b['avg_footfall']} customers/hr)\n"

        prompt = FORMAT_PROMPT.format(
            day=target_date.strftime("%A"),
            date=target_date.strftime("%d %b"),
            predicted_footfall=adequacy["predicted_footfall"],
            increase_pct=adequacy["increase_pct"],
            reason=reason
        )
        prompt += f"\nRaw Mapped Hourly Data Blocks:\n{blocks_text}"

        try:
            report = await self.llm.generate(prompt, timeout=30)
        except Exception:
            report = self._build_raw_fallback(target_date, adequacy)

        # PUSH TO APPROVAL QUEUE (NEVER AUTO-APPROVE)
        result = {
            "status": "pending_manager_review",
            "report": report,
            "needs_approval": True,
            "approval_id": f"schedule_{target_date_str}_{int(time.time())}",
            "approval_reason": f"Review Staffing Schedule for {target_date_str}",
            "approval_details": {
                "report": report
            },
            "on_approval_event": {
                "type": "schedule_approved",
                "data": {"target_date": target_date_str}
            }
        }

        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="schedule_generated",
                decision=f"Generated shift recommendations for {target_date_str}",
                reasoning=reason,
                outcome=json.dumps({"blocks": len(adequacy["hourly_blocks"])}),
                status="pending_approval"
            )

        return result
