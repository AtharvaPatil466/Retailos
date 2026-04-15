from unittest.mock import AsyncMock, MagicMock

import pytest

from runtime.memory import Memory
from runtime.orchestrator import Orchestrator
from skills.base_skill import BaseSkill, SkillState
from skills.negotiation import NegotiationSkill
from skills.procurement import ProcurementSkill


def _mock_llm(text=""):
    """Create a mock LLMClient."""
    mock = MagicMock()
    mock.generate = AsyncMock(return_value=text)
    mock.generate_sync = MagicMock(return_value=text)
    mock.get_raw_client = MagicMock(return_value=None)
    return mock


class DummySkill(BaseSkill):
    def __init__(self, name: str, result: dict):
        super().__init__(name=name)
        self._result = result

    async def init(self) -> None:
        self.state = SkillState.RUNNING

    async def run(self, event: dict):
        return self._result


@pytest.mark.asyncio
async def test_orchestrator_process_event_uses_mocked_gemini_route(audit_mock):
    memory = Memory()
    skill = DummySkill("inventory", {"status": "ok"})
    await skill.init()
    await memory.set("orchestrator:daily_summary", {"summary": "test"})

    orchestrator = Orchestrator(
        memory=memory,
        audit=audit_mock,
        skills={"inventory": skill},
        api_key="",
    )
    orchestrator.llm = _mock_llm(
        text='{"actions":[{"skill":"inventory","params":{"sku":"SKU-1"},"reason":"route test"}],"overall_reasoning":"ok"}'
    )

    result = await orchestrator._process_event({"type": "stock_update", "data": {"sku": "SKU-1"}})

    assert result["routing"]["actions"][0]["skill"] == "inventory"
    assert result["results"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_orchestrator_queues_pending_approval(audit_mock):
    memory = Memory()
    skill = DummySkill(
        "procurement",
        {
            "needs_approval": True,
            "approval_id": "approval-123",
            "approval_reason": "Need owner signoff",
            "approval_details": {"supplier_id": "SUP-1", "amount": 2500},
            "on_approval_event": {"type": "procurement_approved", "data": {"sku": "SKU-1"}},
        },
    )
    await skill.init()

    orchestrator = Orchestrator(
        memory=memory,
        audit=audit_mock,
        skills={"procurement": skill},
        api_key="",
    )

    result = await orchestrator._execute_skill(
        "procurement",
        {"type": "low_stock", "data": {"sku": "SKU-1"}},
        {"sku": "SKU-1"},
        "approval flow",
    )
    pending = await orchestrator.get_pending_approvals()

    assert result["status"] == "success"
    assert pending[0]["id"] == "approval-123"


@pytest.mark.asyncio
async def test_procurement_ranking_parses_fenced_json():
    skill = ProcurementSkill()
    skill.llm = _mock_llm(
        text="""```json
{"ranked_suppliers":[{"rank":1,"supplier_id":"SUP-1","supplier_name":"Fresh","price_per_unit":99.0,"delivery_days":2,"min_order_qty":10,"reasoning":"Best fit"}],"overall_reasoning":"Strong supplier"}
```"""
    )

    result = await skill._rank_with_gemini(
        "Rice",
        [{"supplier_id": "SUP-1", "supplier_name": "Fresh"}],
        {},
        "Waste context",
    )

    assert result["ranked_suppliers"][0]["supplier_id"] == "SUP-1"


@pytest.mark.asyncio
async def test_negotiation_outreach_returns_mocked_gemini_text():
    skill = NegotiationSkill()
    skill.llm = _mock_llm(text="Drafted supplier outreach")

    message = await skill._draft_outreach(
        "Basmati Rice",
        {"supplier_name": "Fresh Supply"},
        {"orders": 3},
        "Reference market price is 95",
    )

    assert message == "Drafted supplier outreach"
