from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from brain.db import get_connection
from brain.expiry_alerter import get_expiry_risks
from brain.reorder_optimizer import get_optimized_reorder_quantity
from brain.wastage_tracker import log_movement
from runtime.orchestrator import Orchestrator
from skills.procurement import ProcurementSkill


def test_high_expiry_products_get_lower_reorder_quantity(isolated_brain_db):
    get_connection().close()

    log_movement("PROD_A", 100, "restock")
    log_movement("PROD_A", -20, "expiry")
    log_movement("PROD_B", 100, "restock")
    log_movement("PROD_B", -5, "expiry")

    opt_a = get_optimized_reorder_quantity("PROD_A", 10, 7)
    opt_b = get_optimized_reorder_quantity("PROD_B", 10, 7)

    assert opt_a["optimized_quantity"] < opt_b["optimized_quantity"]


def test_expiry_risk_respects_sales_velocity(isolated_brain_db):
    yesterday = date.today() - timedelta(days=18)

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO product_metadata (product_id, shelf_life_days, last_restock_date) VALUES (?, ?, ?)",
            ("SLOW_ITEM", 21, yesterday.isoformat()),
        )
        conn.execute(
            "INSERT INTO product_metadata (product_id, shelf_life_days, last_restock_date) VALUES (?, ?, ?)",
            ("FAST_ITEM", 21, yesterday.isoformat()),
        )

    risks = get_expiry_risks(
        [
            {"sku": "SLOW_ITEM", "product_name": "Slow Milk", "current_stock": 30, "daily_sales_rate": 5},
            {"sku": "FAST_ITEM", "product_name": "Fast Milk", "current_stock": 30, "daily_sales_rate": 15},
        ],
        current_date=date.today(),
    )

    risk_skus = [risk["data"]["product_id"] for risk in risks]
    assert "SLOW_ITEM" in risk_skus
    assert "FAST_ITEM" not in risk_skus


@pytest.mark.asyncio
async def test_procurement_prompt_uses_wastage_adjusted_context(isolated_brain_db):
    get_connection().close()
    log_movement("PROD_A", 100, "restock")
    log_movement("PROD_A", -20, "expiry")

    skill = ProcurementSkill()
    skill.suppliers_data = [{"supplier_id": "sup1", "products": ["PROD_A"], "categories": []}]

    captured_context = {}

    async def fake_rank(product, suppliers, mem_ctx, waste_ctx, market_ctx=""):
        captured_context["waste"] = waste_ctx
        return {"ranked_suppliers": [], "overall_reasoning": "mocked"}

    skill._rank_with_gemini = fake_rank

    await skill.run(
        {
            "type": "procurement_request",
            "data": {"product_name": "PROD_A", "sku": "PROD_A", "daily_sales_rate": 10, "lead_time_days": 7},
        }
    )

    assert "20.0% wastage rate" in captured_context["waste"]
    assert "56" in captured_context["waste"]


@pytest.mark.asyncio
async def test_expiry_risk_fallback_routes_inventory_and_customer(audit_mock):
    orchestrator = Orchestrator(memory=MagicMock(), audit=audit_mock, skills={}, api_key="")
    result = orchestrator._fallback_route({"type": "expiry_risk", "data": {"product_id": "EXP1"}})

    skill_targets = [action["skill"] for action in result["actions"]]
    assert "inventory" in skill_targets
    assert "customer" in skill_targets
