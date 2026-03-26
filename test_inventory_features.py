import sqlite3
import time
from datetime import datetime, date, timedelta
from pathlib import Path
import os
import sys

# Add project root to python path to load brain module successfully
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brain.decision_logger import _get_connection
from brain.wastage_tracker import log_movement
from brain.reorder_optimizer import get_optimized_reorder_quantity
from brain.expiry_alerter import get_expiry_risks
from runtime.orchestrator import Orchestrator

DB_PATH = Path("data/brain.db")
if DB_PATH.exists():
    os.remove(DB_PATH)

print("Starting tests...\n")
from brain.decision_logger import _get_connection
# Force create tables
_get_connection().close()
time.sleep(1)

# TEST 1: Reorder Logic
print("TEST 1: High expiry vs Low expiry reorder quantities")
# High Expiry Product: Product A (received 100, 20 expired) -> 20% waste
log_movement("PROD_A", 100, "restock")
log_movement("PROD_A", -20, "expiry")
# Low Expiry Product: Product B (received 100, 5 expired) -> 5% waste
log_movement("PROD_B", 100, "restock")
log_movement("PROD_B", -5, "expiry")

# Both have 10 daily sales, 7 day lead time -> base = 70
opt_a = get_optimized_reorder_quantity("PROD_A", 10, 7)
opt_b = get_optimized_reorder_quantity("PROD_B", 10, 7)

print(f"Product A (High Expiry) Opt Qty: {opt_a['optimized_quantity']} (Rate: {opt_a['wastage_rate']})")
print(f"Product B (Low Expiry) Opt Qty: {opt_b['optimized_quantity']} (Rate: {opt_b['wastage_rate']})")
assert opt_a["optimized_quantity"] < opt_b["optimized_quantity"], "Test 1 Failed"
print("TEST 1 PASSED!\n")


# TEST 2 & 3: Expiry Alerter Velocity Matrix
print("TEST 2 & 3: Sales velocity affects expiry risk triggers")
yesterday = date.today() - timedelta(days=18)
curr_date = date.today()

# Setup metadata mapping in db
with _get_connection() as conn:
    conn.execute("INSERT INTO product_metadata (product_id, shelf_life_days, last_restock_date) VALUES (?, ?, ?)",
                 ("SLOW_ITEM", 21, yesterday.isoformat()))
    conn.execute("INSERT INTO product_metadata (product_id, shelf_life_days, last_restock_date) VALUES (?, ?, ?)",
                 ("FAST_ITEM", 21, yesterday.isoformat()))

inventory = [
    # 3 days left (21-18). 30 in stock. Sells 5/day. Need 6 days to sell out. WILL EXPIRE.
    {"sku": "SLOW_ITEM", "product_name": "Slow Milk", "current_stock": 30, "daily_sales_rate": 5},
    # 3 days left. 30 in stock. Sells 15/day. Need 2 days to sell out. WILL SELL OUT.
    {"sku": "FAST_ITEM", "product_name": "Fast Milk", "current_stock": 30, "daily_sales_rate": 15}
]

risks = get_expiry_risks(inventory, current_date=curr_date)
risk_skus = [r["data"]["product_id"] for r in risks]
print(f"Found Risks for: {risk_skus}")
assert "SLOW_ITEM" in risk_skus, "TEST 2 FAILED (Slow item missing)"
assert "FAST_ITEM" not in risk_skus, "TEST 3 FAILED (Fast item incorrectly flagged)"
print("TEST 2 & 3 PASSED!\n")


# TEST 4: Gemini Prompt Content
print("TEST 4: Gemini prompt shows wastage-adjusted quantity")
from skills.procurement import ProcurementSkill
import asyncio

skill = ProcurementSkill()
skill.suppliers_data = [{"supplier_id": "sup1"}]  # mock required data

captured_context = {}
async def fake_rank(product, suppliers, mem_ctx, waste_ctx):
    captured_context["waste"] = waste_ctx
    return {"ranked_suppliers": [], "overall_reasoning": "mocked"}
# Override the async prompt processor dynamically
skill._rank_with_gemini = fake_rank

event = {
    "type": "procurement_request",
    "data": {"product_name": "PROD_A", "sku": "PROD_A", "daily_sales_rate": 10, "lead_time_days": 7}
}

asyncio.run(skill.run(event))
print("Captured context snippet:")
print(captured_context["waste"])
assert "20.0% wastage rate" in captured_context["waste"], "TEST 4 FAILED"
assert "56" in captured_context["waste"], "TEST 4 FAILED (Expected 56 units)"
print("TEST 4 PASSED!\n")


# TEST 5: Orchestrator Route Chaining
print("TEST 5: expiry_risk event successfully chains customer promotion mapping")
from unittest.mock import MagicMock
orch = Orchestrator(memory=MagicMock(), audit=MagicMock(), skill_loader=MagicMock(), api_key="fake")
mock_event = {"type": "expiry_risk", "data": {"product_id": "EXP1"}}
res = orch._fallback_route(mock_event)
actions = res.get("actions", [])
skill_targets = [a["skill"] for a in actions]
print(f"Chained actions to skills: {skill_targets}")
assert "inventory" in skill_targets, "TEST 5 FAILED (Missing inventory dashboard alert target)"
assert "customer" in skill_targets, "TEST 5 FAILED (Missing customer promotion target)"
print("TEST 5 PASSED!\n")

print("All Verification Tests Passed Successfully!")
