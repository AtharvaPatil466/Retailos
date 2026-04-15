from unittest.mock import AsyncMock

import pytest

from runtime.audit import AuditLogger
from runtime.memory import Memory
from runtime.orchestrator import Orchestrator
from skills.base_skill import BaseSkill, SkillState


class _WorkflowSkill(BaseSkill):
    def __init__(self, name: str, result: dict):
        super().__init__(name=name)
        self._result = result

    async def init(self) -> None:
        self.state = SkillState.RUNNING

    async def run(self, event: dict):
        return self._result


@pytest.mark.asyncio
async def test_orchestrator_day_flow_smoke():
    memory = Memory()
    audit = AuditLogger("postgresql://mock/db")
    audit.log = AsyncMock()

    inventory = _WorkflowSkill(
        "inventory",
        {
            "status": "pending_manager_review",
            "needs_approval": True,
            "approval_id": "inventory_low_stock_1",
            "approval_reason": "Review urgent reorder",
            "approval_details": {"supplier_id": "SUP-1", "amount": 500},
            "on_approval_event": {"type": "procurement_approved", "data": {"sku": "SKU-001"}},
        },
    )
    negotiation = _WorkflowSkill("negotiation", {"status": "drafted", "draft": "Best price?"})

    for skill in (inventory, negotiation):
        await skill.init()

    orchestrator = Orchestrator(
        memory=memory,
        audit=audit,
        skills={"inventory": inventory, "negotiation": negotiation},
        api_key="",
    )

    result = await orchestrator._execute_skill(
        "inventory",
        {"type": "stock_update", "data": {"sku": "SKU-001"}},
        {"sku": "SKU-001"},
        "Simulated day flow",
    )
    pending = await orchestrator.get_pending_approvals()

    assert result["status"] == "success"
    assert pending[0]["id"] == "inventory_low_stock_1"
