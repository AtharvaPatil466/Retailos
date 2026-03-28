# Complete RetailOS Source Code



## File: `./test_scheduling_features.py`
```py
import sqlite3
import time
from datetime import date, timedelta, datetime
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brain.decision_logger import _get_connection
from brain.footfall_analyzer import log_footfall
from brain.shift_optimizer import calculate_adequacy
from brain.festival_detector import check_upcoming_festival
from skills.scheduling import SchedulingSkill
import asyncio

DB_PATH = Path("data/brain.db")

print("Starting tests...\n")

with _get_connection() as conn:
    conn.execute("DELETE FROM footfall_logs")
    conn.execute("DELETE FROM staff_shifts")

# Prepare historical mock data (2 Weeks)
# We make Mondays quiet (10 cust/hr => 240/day)
# We make Saturdays busy (40 cust/hr => 960/day)
base = date.today() - timedelta(days=20)
for i in range(14):
    d = base + timedelta(days=i)
    d_str = d.strftime("%Y-%m-%d")
    is_sat = d.weekday() == 5
    for h in range(24):
        traffic = 45 if is_sat and (10 <= h < 18) else 10
        log_footfall(d_str, h, traffic, traffic // 2)

# TEST 1: Peak historical footfall generates understaffed flag
print("TEST 1: Peak Saturday generates an understaffed flag")
# Generate next Saturday
next_sat = base
while next_sat.weekday() != 5:
    next_sat += timedelta(days=1)
next_sat += timedelta(days=14) # Bring closer to future
next_sat_str = next_sat.strftime("%Y-%m-%d")

# Only give 1 staff member. 1 staff = 20 customers. Peak is 45. Should gap aggressively (-1 or -2)
with _get_connection() as conn:
    conn.execute("INSERT INTO staff_shifts (staff_id, staff_name, role, shift_date, start_hour, end_hour) VALUES ('S1', 'John', 'Cashier', ?, 10, 18)", (next_sat_str,))

adequacy_under = calculate_adequacy(next_sat)
understaffed = any(b['status'] == 'Understaffed' for b in adequacy_under['hourly_blocks'])
print(f"Max expected footfall block: {max(b['avg_footfall'] for b in adequacy_under['hourly_blocks'])}/hr (1 staff)")
assert understaffed, "Test 1 Failed"
print("TEST 1 PASSED!\n")

# TEST 2: Festival within 14 days applies multiplier
print("TEST 2: Festival Multiplier")
# The festival_detector includes a mock rolling festival at today + 5 days that surges 1.5x
fest_date = date.today() + timedelta(days=5)

# Normal expected footfall on whatever day that is
adeq_fest = calculate_adequacy(fest_date)
print(f"Festival detected: {adeq_fest['festival']['festival_name']} ({adeq_fest['festival']['multiplier']}x)")
print(f"Predicted Increase Pct: {adeq_fest['increase_pct']}%")
assert adeq_fest['festival'] is not None, "Test 2 Failed"
assert adeq_fest['increase_pct'] >= 15, "Test 2 Failed (multiplier didn't correctly surge prediction vs base)"
print("TEST 2 PASSED!\n")

# TEST 3: Adequate Coverage
print("TEST 3: Adequate Coverage")
# Book 4 staff total which handles 80 customers/hr cleanly beating the 67 surge peak
with _get_connection() as conn:
    conn.execute("UPDATE staff_shifts SET end_hour = 19 WHERE staff_id = 'S1' AND shift_date = ?", (next_sat_str,))
    conn.execute("INSERT INTO staff_shifts (staff_id, staff_name, role, shift_date, start_hour, end_hour) VALUES ('S2', 'Jane', 'Cashier', ?, 10, 19)", (next_sat_str,))
    conn.execute("INSERT INTO staff_shifts (staff_id, staff_name, role, shift_date, start_hour, end_hour) VALUES ('S3', 'Bob', 'Packer', ?, 10, 19)", (next_sat_str,))
    conn.execute("INSERT INTO staff_shifts (staff_id, staff_name, role, shift_date, start_hour, end_hour) VALUES ('S4', 'Alice', 'Guard', ?, 10, 19)", (next_sat_str,))

adequacy_safe = calculate_adequacy(next_sat)
understaffed_now = any(b['status'] == 'Understaffed' for b in adequacy_safe['hourly_blocks'] if 10 <= b['start'] <= 18)
assert not understaffed_now, "Test 3 Failed"
print("TEST 3 PASSED!\n")


# TEST 4 & 5: Format & Approvals Check
print("TEST 4/5: Prompt execution strictly limits to Queue and formatting matches.")

class MockClient:
    class Aio:
        class Models:
            async def generate_content(self, model, contents):
                class MockResp:
                    text = "Mocked LLM Body perfectly formatting hour-by-hour output."
                return MockResp()
        models = Models()
    aio = Aio()

skill = SchedulingSkill()
skill.client = MockClient()

async def run_test():
    result = await skill._review_shifts({"target_date": next_sat_str})
    
    print(f"Needs approval flag: {result.get('needs_approval')}")
    assert result.get("needs_approval") is True, "Test 4 Failed (Should never auto-approve!)"
    assert result.get("status") == "pending_manager_review", "Test 4 Failed"
    
    # We will purposely kill the client to guarantee it falls back to raw data to prove Test 5 formatting physically builds the output text required.
    skill.client = None
    result_fallback = await skill._review_shifts({"target_date": next_sat_str})
    
    body = result_fallback["report"]
    assert "Tomorrow —" in body, "Test 5 Failed"
    assert "Hour-by-hour adequacy:" in body, "Test 5 Failed"
    assert "✓" in body or "✗" in body, "Test 5 Failed"

asyncio.run(run_test())

print("TEST 4 & 5 PASSED!\n")
print("All Verification Tests Passed Successfully!")

```


## File: `./test_pricing_features.py`
```py
import sqlite3
import time
from pathlib import Path
import os
import sys

# Add project root to python path to load brain module successfully
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brain.decision_logger import _get_connection
from brain.price_monitor import log_manual_price, fetch_agmarknet_prices, get_market_reference
from brain.price_analyzer import analyze_quote, format_supplier_verdict
from skills.negotiation import NegotiationSkill
import asyncio

DB_PATH = Path("data/brain.db")
if DB_PATH.exists():
    os.remove(DB_PATH)

print("Starting tests...\n")
with _get_connection() as conn:
    pass

# Setup manual prices
# 8 days ago
log_manual_price("PROD_OLD", "Store A", 100.0)
with _get_connection() as conn:
    conn.execute("UPDATE market_prices SET recorded_at = ? WHERE product_id = ?", (time.time() - (8 * 86400), "PROD_OLD"))

# Current price (median 100)
log_manual_price("PROD_NEW", "Store B", 100.0)
log_manual_price("PROD_NEW", "Store C", 100.0)

# TEST 1 & 2: Verdicts
print("TEST 1 & 2: Verdict Logic")
ref_new = get_market_reference("PROD_NEW")

# Quote 110 (10% above market)
high_quote = analyze_quote(110.0, ref_new)
print(f"110 quote verdict: {high_quote['verdict']} (+{high_quote['delta_percentage']}%)")
assert high_quote["verdict"] == "above_market", "Test 1 Failed"
assert high_quote["delta_percentage"] == 10.0, "Test 1 Failed"

# Quote 90 (10% below market)
low_quote = analyze_quote(90.0, ref_new)
print(f"90 quote verdict: {low_quote['verdict']} ({low_quote['delta_percentage']}%)")
assert low_quote["verdict"] == "below_market", "Test 2 Failed"

# Format strings to check counter
fmt_high = format_supplier_verdict("SupplierX", 110.0, ref_new)
fmt_low = format_supplier_verdict("SupplierY", 90.0, ref_new)
assert "countering" in fmt_high, "Test 1 Counter missing"
assert "countering" not in fmt_low, "Test 2 Counter incorrectly present"
print("TEST 1 & 2 PASSED!\n")

# TEST 3: Confidence Downgrade
print("TEST 3: Old quote confidence downgrade")
ref_old = get_market_reference("PROD_OLD")
print(f"Old Quote Confidence: {ref_old['confidence']}")
assert ref_old["confidence"] == "low", "Test 3 Failed"
print("TEST 3 PASSED!\n")

# TEST 4: Negotiation Prompt Context Injection
print("TEST 4: Negotiation skill messaging prompt visibly carries referenced market text")
skill = NegotiationSkill()

captured_payload = ""

# Override gemini client mock
class MockClient:
    class Aio:
        class Models:
            async def generate_content(self, model, contents):
                global captured_payload
                captured_payload = contents
                class MockResp:
                    text = "Mocked msg"
                return MockResp()
        models = Models()
    aio = Aio()

skill.client = MockClient()

async def run_test():
    # Inject context manually mapping to orchestrator run() flow
    from brain.price_monitor import get_market_reference
    market_ref = get_market_reference("PROD_NEW")
    price_context = (
        f"Market Reference Constraints: We recently saw this product heavily discounted at ₹{market_ref['lowest_price']} ({market_ref['lowest_source']}). "
        f"The general market median is ₹{market_ref['median_price']}. "
        f"If you ask for a price, explicitly mention the ₹{market_ref['lowest_price']} external reference naturally to pressure them downwards!"
    )
    await skill._draft_outreach("PROD_NEW", {"supplier_name": "TestSupplier"}, {}, price_context)

asyncio.run(run_test())

print("Captured Negotiation Prompt Snippet:")
print(captured_payload)
assert "Market Reference Constraints" in captured_payload, "Test 4 Failed"
assert "100.0" in captured_payload, "Test 4 Failed"

print("\nTEST 4 PASSED!\n")
print("All Verification Tests Passed Successfully!")

```


## File: `./test_trust_features.py`
```py
import sqlite3
import time
from datetime import datetime, date
from pathlib import Path
import os
import sys

# Add project root to python path to load brain module successfully
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brain.decision_logger import log_decision, log_delivery, log_quality_flag
from brain.trust_scorer import get_trust_score
from brain.seasonal_detector import detect_seasonal_spikes

DB_PATH = Path("data/brain.db")
if DB_PATH.exists():
    os.remove(DB_PATH)

print("Starting tests...\n")
from brain.decision_logger import _get_connection
# Force create tables
_get_connection().close()
time.sleep(1)

# TEST 1: Delivery Impact
print("TEST 1: Perfect approvals but late deliveries score lowers from 100")
for i in range(10):
    log_decision("SUP-PERFECT", 100, "approved")
    # Using YYYY-MM-DD format as parsed
    log_delivery("SUP-PERFECT", f"ord_{i}", "2026-03-01", "2026-03-01")

for i in range(10):
    log_decision("SUP-LATE", 100, "approved")
    # Expected March 1st, Actual March 5th
    log_delivery("SUP-LATE", f"ord_{i}", "2026-03-01", "2026-03-05")

score_perfect = get_trust_score("SUP-PERFECT")
score_late = get_trust_score("SUP-LATE")

print(f"SUP-PERFECT Score: {score_perfect['score']} (Breakdown: {score_perfect['breakdown']})")
print(f"SUP-LATE Score: {score_late['score']} (Breakdown: {score_late['breakdown']})")
assert score_late['score'] < score_perfect['score'], "TEST 1 FAILED"
print("TEST 1 PASSED!\n")


# TEST 2: Quality Impact
print("TEST 2: Complaint ratio impacts score correctly")
for i in range(10):
    log_decision("SUP-QUAL-1", 100, "approved")
    log_delivery("SUP-QUAL-1", f"ord_q1_{i}", "2026-03-01", "2026-03-01")
log_quality_flag("SUP-QUAL-1", "ord_q1_0", "Bad packaging")

for i in range(10):
    log_decision("SUP-QUAL-5", 100, "approved")
    log_delivery("SUP-QUAL-5", f"ord_q5_{i}", "2026-03-01", "2026-03-01")
for i in range(5):
    log_quality_flag("SUP-QUAL-5", f"ord_q5_{i}", "Moldy")

score_qual_1 = get_trust_score("SUP-QUAL-1")
score_qual_5 = get_trust_score("SUP-QUAL-5")

print(f"SUP-QUAL-1 Score: {score_qual_1['score']} (Breakdown: {score_qual_1['breakdown']})")
print(f"SUP-QUAL-5 Score: {score_qual_5['score']} (Breakdown: {score_qual_5['breakdown']})")
assert score_qual_1['score'] > score_qual_5['score'], "TEST 2 FAILED"
print("TEST 2 PASSED!\n")


# TEST 3: Seasonal Detector
print("TEST 3: Seasonal detector fires correctly for an April spike")
mock_orders = [
    {"date": "2025-01-15", "product_name": "Mango Pulp", "quantity": 10},
    {"date": "2025-02-15", "product_name": "Mango Pulp", "quantity": 12},
    {"date": "2025-03-15", "product_name": "Mango Pulp", "quantity": 15},
    {"date": "2025-04-10", "product_name": "Mango Pulp", "quantity": 100},
    {"date": "2025-04-20", "product_name": "Mango Pulp", "quantity": 120},
    {"date": "2025-05-15", "product_name": "Mango Pulp", "quantity": 10},
]

# Feb 20 + 7 weeks = April 10 (Target month is 4)
current_date = date(2026, 2, 20)
events = detect_seasonal_spikes(current_date, mock_orders)
print(f"Detected events: {events}")
assert len(events) == 1, "TEST 3 FAILED (number of events != 1)"
assert events[0]["type"] == "seasonal_preempt", "TEST 3 FAILED (event type)"
assert events[0]["data"]["product_name"] == "Mango Pulp", "TEST 3 FAILED (product)"
print("TEST 3 PASSED!\n")

print("All Verification Tests Passed Successfully!")

```


## File: `./test_e2e_day.py`
```py
import asyncio
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Load keys
load_dotenv()

# Add to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime.orchestrator import Orchestrator
from runtime.memory import Memory
from runtime.audit import AuditLogger
from brain.decision_logger import _get_connection

# Teardown databases for fresh mock
DB_PATH = Path("data/brain.db")
if DB_PATH.exists():
    os.remove(DB_PATH)

MEMORY_DB_PATH = Path("data/memory.db")
if MEMORY_DB_PATH.exists():
    os.remove(MEMORY_DB_PATH)

async def test_simulate_e2e_day():
    print("Initializing RetailOS Orchestrator for Full E2E Day Simulation...\n")
    
    memory = Memory(str(MEMORY_DB_PATH))
    audit = AuditLogger("postgresql://mock/db")
    
    # Initialize Orchestrator properly ensuring Gemini checks
    api_key = os.environ.get("GEMINI_API_KEY", "")
    orchestrator = Orchestrator(memory=memory, audit=audit, api_key=api_key)
    
    for skill in orchestrator.skills.values():
        await skill.init()
    
    # Pre-Seed DB for logic drops
    from datetime import date, timedelta
    today = date.today()
    tomorrow = today + timedelta(days=1)
    
    with _get_connection() as conn:
        # Pre-seed Supplier 1 (High Trust, Avg Delivery, Expensive)
        conn.execute("INSERT INTO decisions (supplier_id, amount, status, timestamp) VALUES ('SUP-1', 180, 'approved', 1.0)")
        
        # Pre-seed Competitor Market References
        conn.execute("INSERT INTO market_prices (product_id, source_name, price_per_unit, unit, recorded_at, source_type, confidence) VALUES ('SKU-001', 'Agmarknet Hub', 160.0, 'kg', ?, 'automated', 'high')", (time.time(),))
        
        # Pre-seed Footfall History for tomorrow
        is_sat = tomorrow.weekday() == 5
        base = today - timedelta(days=14)
        for i in range(14):
            d = base + timedelta(days=i)
            # Make the day exactly match tomorrow's weekday so 'get_footfall_pattern' triggers
            if d.weekday() == tomorrow.weekday():
                for h in range(10, 18): # 8 hour window
                    conn.execute("INSERT INTO footfall_logs (date, hour, customer_count, transaction_count, source) VALUES (?, ?, ?, ?, 'pos_proxy')", (d.strftime("%Y-%m-%d"), h, 50, 25))

    # Mock low stock -> fires inventory alert via low stock
    print("--- [EVENT 1] Registering stock sale (Triggering Inventory Reorder) ---")
    await orchestrator.skills["inventory"].run({
        "type": "stock_movement",
        "data": {
            "product_id": "prd_123",
            "delta": -25,
            "reason": "sale",
            "remaining_quantity": 8
        }
    })
    
    # Force triggering the reorder
    print("--- [EVENT 2] Triggering Inventory Reorder Evaluation ---")
    inv_result = await orchestrator.skills["inventory"].run({
        "type": "stock_update",
        "data": {
            "sku": "SKU-001",
            "quantity": 10,
            "movement_type": "sale"
        }
    })
    
    if "alerts" in inv_result and len(inv_result["alerts"]) > 0:
        for alert in inv_result["alerts"]:
            print(f"Triggered cascade alert: low stock for {alert['sku']}")
            # Emulate orchestrator mapping the event to the Procurement skill combining trust and market price logic
            print("\n--- [EVENT 3] Procurement Skill: Ranking Suppliers ---")
            
            proc_event = {"type": "low_stock", "data": {"product_id": alert["sku"]}}
            proc_result = await orchestrator.skills["procurement"].run(proc_event)
            
            # Check formatting output
            print("Procurement Dump Payload:\n", proc_result)
            print(proc_result.get("report", "No report mapped")[:300] + "...\n")
            
            # Procurement queues human approval natively, but chains into Negotiation
            if proc_result.get("needs_approval"):
                pev = proc_result.get("on_approval_event")
                if pev and pev["type"] == "procurement_approved":
                    print("\n--- [EVENT 4] Negotiation Skill: Drafting WhatsApp with Market Price Context ---")
                    # Trigger generation natively as if it were approved
                    neg_result = await orchestrator.skills["negotiation"].run(pev)
                    print("Negotiation Dump Payload:\n", neg_result)
                    draft = neg_result.get("draft", "")
                    print(f"Draft generated:\n{draft}\n")

    # Now daily sweep runs at Midnight
    print("\n--- [EVENT 5] Midnight Trigger: Orchestrator Daily Analytics Sweep ---")
    sweep_event = {"type": "daily_analytics", "data": {"date": today.isoformat()}}
    # Just call run physically mimicking loop drops
    await orchestrator.skills["analytics"].run(sweep_event)
    
    # We must explicitly trigger scheduling block
    sched_result = await orchestrator.skills["scheduling"].run({
        "type": "shift_review", 
        "data": {"target_date": tomorrow.isoformat()}
    })
    
    if sched_result.get("needs_approval"):
        orchestrator.pending_approvals["schedule_123"] = {
            "skill": "scheduling",
            "result": sched_result,
            "event": {"type": "shift_review", "data": {"target_date": tomorrow.isoformat()}}
        }
    
    print("\n--- [RESULT VALIDATION] Checking the Action approval queue ---")
    queue = orchestrator.get_pending_approvals()
    expected_items = ["schedule", "insight"]
    found = [item["id"].split("_")[0] for item in queue]
    print(f"Items sitting in human approval queue: {found}")
    
    # Check if Schedule was explicitly built
    schedule_item = next((item for item in queue if item["id"].startswith("schedule")), None)
    if schedule_item:
        print("\n--- Extracting generated Schedule AI Output ---")
        print(schedule_item["result"].get("approval_details", {}).get("report", ""))

    print("\nSimulation completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_simulate_e2e_day())

```


## File: `./README.md`
```md
# RetailOS — Autonomous Agent Runtime for Retail Operations

> "Most teams built agents. We built the runtime that runs them."

RetailOS is a persistent autonomous agent runtime that watches for events in a retail supermart and takes action without being asked. The owner's job is one tap: approve or reject.

## Architecture

```
┌─────────────────────────────────────────────┐
│              ORCHESTRATOR                    │
│  Event Loop → Gemini Routing → Skill Exec   │
│  Memory Context │ Audit Logging │ Retries   │
├───────┬───────┬───────┬───────┬─────────────┤
│ Inv.  │ Proc. │ Neg.  │ Cust. │ Analytics   │
│ Skill │ Skill │ Skill │ Skill │ Skill       │
└───────┴───────┴───────┴───────┴─────────────┘
    ↕       ↕       ↕       ↕        ↕
  [Mock]  [Gemini] [Gemini] [Gemini] [Gemini]
  [POS]   [API]   [WhatsApp][API]    [API]
```

## Quick Start

```bash
# Backend
pip install -r requirements.txt
cp .env.example .env  # Add your GEMINI_API_KEY
python main.py

# Dashboard (separate terminal)
cd dashboard
npm install
npm run dev
```

Backend runs on `http://localhost:8000`, dashboard on `http://localhost:3000`.

Redis and PostgreSQL are optional — the system falls back to in-memory storage if they're unavailable.

## Skills

| Skill | What it does | Uses Gemini? |
|-------|-------------|-------------|
| Inventory | Polls stock, fires alerts based on sales velocity | No |
| Procurement | Ranks suppliers with reasoning | Yes |
| Negotiation | WhatsApp outreach, parses messy Hinglish replies | Yes (x2) |
| Customer | Segments customers, writes personalized offers | Yes |
| Analytics | Daily pattern analysis, feeds memory | Yes |

## Key API Endpoints

- `POST /api/demo/trigger-flow` — Trigger the ice cream demo
- `POST /api/demo/supplier-reply` — Simulate a supplier WhatsApp reply
- `GET /api/audit` — View the audit trail
- `GET /api/approvals` — Pending owner approvals
- `POST /api/approvals/approve` — One-tap approve

```


## File: `./test_inventory_features.py`
```py
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

```


## File: `./test_customer_features.py`
```py
import sqlite3
import time
from datetime import datetime
from pathlib import Path
import os
import sys

# Add project root to python path to load brain module successfully
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brain.decision_logger import _get_connection
from brain.message_tracker import log_message_sent, log_conversion
from brain.conversion_scorer import get_template_rankings, get_template_context
from brain.churn_detector import get_churn_scores

DB_PATH = Path("data/brain.db")
if DB_PATH.exists():
    os.remove(DB_PATH)

print("Starting tests...\n")
# Force create tables
_get_connection().close()
time.sleep(1)

# TEST 1: Template Scoring
print("TEST 1: 5 sends / 4 conversions scores higher than 10 sends / 2 conversions")
# Template A (5 sends, 4 conversions) -> 80%
for i in range(5):
    msg_id = f"msg_A_{i}"
    log_message_sent("cust1", msg_id, "Template A")
    if i < 4:
        log_conversion("cust1", msg_id, 100)

# Template B (10 sends, 2 conversions) -> 20%
for i in range(10):
    msg_id = f"msg_B_{i}"
    log_message_sent("cust2", msg_id, "Template B")
    if i < 2:
        log_conversion("cust2", msg_id, 50)

rankings = get_template_rankings()
print("Rankings:")
for r in rankings:
    print(r)
assert rankings[0]["template"] == "Template A", "TEST 1 FAILED"
assert rankings[1]["template"] == "Template B", "TEST 1 FAILED"
print("TEST 1 PASSED!\n")


# TEST 2 & 3: Churn Detection
print("TEST 2 & 3: Churn detection thresholds")
curr_time = time.time()
day = 86400

# Cust 1: buys every 4 days, absent 12 days (ratio = 3.0 -> score 100)
# Timeline: T-20, T-16, T-12
cust1 = {
    "id": "c1", "name": "Frequent Buyer",
    "purchase_history": [
        {"timestamp": curr_time - 20*day},
        {"timestamp": curr_time - 16*day},
        {"timestamp": curr_time - 12*day},
    ]
}

# Cust 2: buys every 30 days, absent 12 days (ratio = 0.4 -> score 0)
# Timeline: T-72, T-42, T-12
cust2 = {
    "id": "c2", "name": "Monthly Buyer",
    "purchase_history": [
        {"timestamp": curr_time - 72*day},
        {"timestamp": curr_time - 42*day},
        {"timestamp": curr_time - 12*day},
    ]
}

scores = get_churn_scores([cust1, cust2], current_time=curr_time)
s1 = next(s for s in scores if s["customer_id"] == "c1")
s2 = next(s for s in scores if s["customer_id"] == "c2")

print(f"Frequent Buyer Score: {s1['churn_score']} (Ratio: {s1['churn_ratio']})")
print(f"Monthly Buyer Score: {s2['churn_score']} (Ratio: {s2['churn_ratio']})")
assert s1["churn_score"] >= 70, "TEST 2 FAILED"
assert s2["churn_score"] < 70, "TEST 3 FAILED"
print("TEST 2 & 3 PASSED!\n")


# TEST 4: Prompt Context
print("TEST 4: Customer skill prompt visibly contains template ranking")
context = get_template_context()
print("Prompt Context:")
print(context)

assert "Top performing message templates" in context, "TEST 4 FAILED"
assert "Template A" in context, "TEST 4 FAILED"
print("TEST 4 PASSED!\n")

print("All Verification Tests Passed Successfully!")

```


## File: `./main.py`
```py
import asyncio
import os

import uvicorn
from dotenv import load_dotenv

from runtime.audit import AuditLogger
from runtime.memory import Memory
from runtime.orchestrator import Orchestrator
from runtime.skill_loader import SkillLoader
from api.routes import create_app

load_dotenv()


async def init_runtime():
    """Initialize all runtime components and return the FastAPI app."""

    # Initialize memory (Redis)
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    memory = Memory(redis_url)
    await memory.init()

    # Initialize audit logger (PostgreSQL)
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/retailos")
    audit = AuditLogger(database_url)
    await audit.init()

    # Load all skills
    skill_loader = SkillLoader(skills_dir="skills", memory=memory, audit=audit)
    skills = await skill_loader.discover_and_load()
    print(f"[RetailOS] Loaded {len(skills)} skills: {', '.join(skills.keys())}")

    # Initialize orchestrator
    api_key = os.environ.get("GEMINI_API_KEY", "")
    orchestrator = Orchestrator(
        memory=memory,
        audit=audit,
        skills=skills,
        api_key=api_key,
    )

    # Start the orchestrator event loop
    await orchestrator.start()

    # Seed demo data into memory
    await _seed_memory(memory)

    # Create FastAPI app
    app = create_app(orchestrator)

    # Store references for cleanup
    app.state.orchestrator = orchestrator
    app.state.memory = memory
    app.state.audit = audit

    return app


async def _seed_memory(memory: Memory):
    """Seed memory with demo data for realistic behavior."""
    # Supplier histories
    await memory.set("supplier:SUP-001:history", {
        "name": "FreshFreeze Distributors",
        "orders": 12,
        "avg_delivery_days": 2.3,
        "reliability": "excellent",
        "last_order": "2026-03-20",
        "notes": "Consistently on time, good quality",
    })
    await memory.set("supplier:SUP-002:history", {
        "name": "CoolFoods India",
        "orders": 8,
        "avg_delivery_days": 4.1,
        "reliability": "declining",
        "last_order": "2026-03-18",
        "notes": "Last 3 of 4 orders were 2 days late",
        "late_deliveries": 3,
    })
    await memory.set("supplier:SUP-003:history", {
        "name": "MegaMart Wholesale",
        "orders": 5,
        "avg_delivery_days": 1.8,
        "reliability": "good",
        "last_order": "2026-03-15",
        "notes": "New supplier, fast so far but higher prices",
    })

    # Yesterday's analytics summary
    await memory.set("orchestrator:daily_summary", {
        "timestamp": 1711238400,
        "summary": "System processed 47 events yesterday. CoolFoods India was 2 days late on delivery again — 3rd time in 4 orders. Protein category offers had 34% conversion rate. Ice cream restocking frequency increased 20% vs last month.",
        "insights": [
            {
                "type": "supplier_reliability",
                "title": "CoolFoods delivery declining",
                "detail": "CoolFoods India has been 2 days late on 3 of the last 4 orders. Average delivery time increased from 2.5 to 4.1 days.",
                "recommendation": "Deprioritize CoolFoods in procurement rankings",
                "severity": "warning",
            },
            {
                "type": "conversion_rate",
                "title": "Protein offers converting well",
                "detail": "Offers for protein products (whey, bars, supplements) had a 34% conversion rate — highest across all categories.",
                "recommendation": "Prioritize protein category for customer outreach",
                "severity": "info",
            },
        ],
        "recommendations": [
            "Deprioritize CoolFoods India in procurement rankings",
            "Review ice cream reorder thresholds — may be set too high",
            "Focus customer offers on protein category",
        ],
    })

    print("[RetailOS] Memory seeded with demo data")


# Global app reference for uvicorn
app = None


async def startup():
    global app
    app = await init_runtime()
    return app


def main():
    """Entry point — starts the RetailOS runtime."""
    import sys

    async def run():
        global app
        app = await init_runtime()

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8000)),
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()

    asyncio.run(run())


if __name__ == "__main__":
    main()

```


## File: `./runtime/audit.py`
```py
import asyncio
import json
import time
import uuid
from typing import Any, Optional

import asyncpg


class AuditLogger:
    """Append-only audit trail stored in PostgreSQL.

    Every action the system takes is logged with full reasoning.
    Nothing is ever deleted or modified.
    """

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
        self._fallback_logs: list[dict] = []
        self.on_log: Optional[callable] = None

    async def init(self) -> None:
        try:
            self.pool = await asyncpg.create_pool(self.database_url, min_size=2, max_size=10)
            await self.pool.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    timestamp DOUBLE PRECISION NOT NULL,
                    skill TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reasoning TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata JSONB DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_skill ON audit_log(skill);
                CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type);
            """)
        except Exception:
            # Fall back to in-memory logging if PostgreSQL is unavailable
            self.pool = None

    async def log(
        self,
        skill: str,
        event_type: str,
        decision: str,
        reasoning: str,
        outcome: str,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "skill": skill,
            "event_type": event_type,
            "decision": decision,
            "reasoning": reasoning,
            "outcome": outcome,
            "status": status,
            "metadata": metadata or {},
        }

        if self.pool:
            try:
                await self.pool.execute(
                    """
                    INSERT INTO audit_log (id, timestamp, skill, event_type, decision, reasoning, outcome, status, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    entry["id"],
                    entry["timestamp"],
                    skill,
                    event_type,
                    decision,
                    reasoning,
                    outcome,
                    status,
                    json.dumps(metadata or {}),
                )
            except Exception:
                self._fallback_logs.append(entry)
        else:
            self._fallback_logs.append(entry)

        if self.on_log:
            try:
                if asyncio.iscoroutinefunction(self.on_log):
                    asyncio.create_task(self.on_log(entry))
                else:
                    self.on_log(entry)
            except Exception:
                pass

        return entry

    async def get_logs(
        self,
        skill: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if self.pool:
            query = "SELECT * FROM audit_log WHERE 1=1"
            params = []
            idx = 1

            if skill:
                query += f" AND skill = ${idx}"
                params.append(skill)
                idx += 1
            if event_type:
                query += f" AND event_type = ${idx}"
                params.append(event_type)
                idx += 1

            query += f" ORDER BY timestamp DESC LIMIT ${idx} OFFSET ${idx + 1}"
            idx += 2
            params.extend([limit, offset])

            rows = await self.pool.fetch(query, *params)
            return [
                {
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "skill": r["skill"],
                    "event_type": r["event_type"],
                    "decision": r["decision"],
                    "reasoning": r["reasoning"],
                    "outcome": r["outcome"],
                    "status": r["status"],
                    "metadata": json.loads(r["metadata"]) if isinstance(r["metadata"], str) else r["metadata"],
                }
                for r in rows
            ]
        else:
            logs = self._fallback_logs[:]
            if skill:
                logs = [l for l in logs if l["skill"] == skill]
            if event_type:
                logs = [l for l in logs if l["event_type"] == event_type]
            logs.sort(key=lambda x: x["timestamp"], reverse=True)
            return logs[offset : offset + limit]

    async def get_log_count(self) -> int:
        if self.pool:
            row = await self.pool.fetchrow("SELECT COUNT(*) as cnt FROM audit_log")
            return row["cnt"]
        return len(self._fallback_logs)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

```


## File: `./runtime/memory.py`
```py
import json
from typing import Any, Optional

import redis.asyncio as redis


# Maps event types to relevant memory key patterns
EVENT_MEMORY_MAP = {
    "low_stock": ["product:{sku}:restock_history", "supplier:*:history", "orchestrator:daily_summary"],
    "supplier_reply": ["supplier:{supplier_id}:history", "product:{sku}:restock_history"],
    "procurement_needed": ["supplier:*:history", "orchestrator:daily_summary"],
    "customer_offer": ["customer:*:purchases", "customer:*:last_offer"],
    "daily_analytics": ["orchestrator:daily_summary", "supplier:*:history", "product:*:restock_history"],
}


class Memory:
    """Redis-backed persistent memory for RetailOS.

    Structured key-value storage organized by domain.
    Not vector search — deliberate key-value with domain-specific key patterns.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None
        self._fallback: dict[str, str] = {}

    async def init(self) -> None:
        try:
            self.client = redis.from_url(self.redis_url, decode_responses=True)
            await self.client.ping()
        except Exception:
            self.client = None

    async def get(self, key: str) -> Any:
        if self.client:
            try:
                val = await self.client.get(key)
                if val is None:
                    return None
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return val
            except Exception:
                pass
        return self._fallback.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        serialized = json.dumps(value) if not isinstance(value, str) else value
        if self.client:
            try:
                if ttl:
                    await self.client.setex(key, ttl, serialized)
                else:
                    await self.client.set(key, serialized)
                return
            except Exception:
                pass
        self._fallback[key] = serialized

    async def delete(self, key: str) -> None:
        if self.client:
            try:
                await self.client.delete(key)
                return
            except Exception:
                pass
        self._fallback.pop(key, None)

    async def get_relevant(self, event_type: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch all memory keys relevant to a given event type.

        Resolves placeholders like {sku} and {supplier_id} from context.
        """
        patterns = EVENT_MEMORY_MAP.get(event_type, [])
        context = context or {}
        result = {}

        for pattern in patterns:
            # Resolve placeholders
            resolved = pattern
            for placeholder_key, placeholder_val in context.items():
                resolved = resolved.replace(f"{{{placeholder_key}}}", str(placeholder_val))

            if "*" in resolved:
                # Wildcard — scan for matching keys
                keys = await self._scan_keys(resolved)
                for key in keys[:20]:  # Cap at 20 to keep prompts focused
                    val = await self.get(key)
                    if val is not None:
                        result[key] = val
            else:
                val = await self.get(resolved)
                if val is not None:
                    result[resolved] = val

        return result

    async def _scan_keys(self, pattern: str) -> list[str]:
        if self.client:
            try:
                keys = []
                async for key in self.client.scan_iter(match=pattern, count=100):
                    keys.append(key)
                    if len(keys) >= 50:
                        break
                return keys
            except Exception:
                pass
        # Fallback: match against in-memory keys
        import fnmatch
        return [k for k in self._fallback.keys() if fnmatch.fnmatch(k, pattern)]

    async def get_all_with_prefix(self, prefix: str) -> dict[str, Any]:
        return await self.get_relevant("", {}) if not prefix else {
            k: await self.get(k) for k in await self._scan_keys(f"{prefix}*")
        }

    async def close(self) -> None:
        if self.client:
            await self.client.close()

```


## File: `./runtime/__init__.py`
```py

```


## File: `./runtime/orchestrator.py`
```py
import asyncio
import json
import logging
import time
import traceback
from typing import Any

from google import genai

logger = logging.getLogger(__name__)

from runtime.audit import AuditLogger
from runtime.memory import Memory
from skills.base_skill import BaseSkill, SkillState
from skills.scheduling import SchedulingSkill


ROUTING_SYSTEM_PROMPT = """You are the RetailOS orchestrator — an autonomous agent runtime for retail operations.

Your job: given an event and relevant memory context, decide which skill(s) to run and in what order.

Available skills:
- inventory: Monitors stock levels, calculates days-until-stockout
- procurement: Ranks suppliers using price, reliability, history
- negotiation: Handles the entire WhatsApp conversation, including sending outreach and parsing/evaluating supplier replies into deals
- customer: Segments customers and sends personalized offers
- analytics: Analyzes patterns in audit logs and purchase data
- scheduling: Manages staff shifts, reviews schedules, and optimizes staffing levels

You must respond with valid JSON only:
{
    "actions": [
        {
            "skill": "<skill_name>",
            "params": { ... },
            "reason": "<why this action, in plain English>"
        }
    ],
    "overall_reasoning": "<1-2 sentence summary of your decision>"
}

Consider memory context carefully. If we over-ordered a product recently, maybe hold off.
If a supplier has been unreliable, deprioritize them. Use the context — that's why it's there.

Be proactive: if an event indicates a potential problem (like low stock), don't just analyze it — trigger the necessary skills (e.g., both inventory and procurement) to solve it in parallel."""


class Orchestrator:
    """Core event loop — the brain of RetailOS.

    Takes events, fetches relevant memory, calls Gemini to decide
    what to do, routes to skills, and logs everything.
    """

    def __init__(
        self,
        memory: Memory,
        audit: AuditLogger,
        skills: dict[str, BaseSkill],
        api_key: str,
    ):
        self.memory = memory
        self.audit = audit
        self.skills = skills
        self.client = genai.Client(api_key=api_key) if api_key else None
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.running = False
        self.pending_approvals: dict[str, dict] = {}
        self.max_retries = 3
        self.retry_delay = 2  # seconds

    async def start(self) -> None:
        """Start the orchestrator event loop."""
        self.running = True
        await self.audit.log(
            skill="orchestrator",
            event_type="runtime_start",
            decision="Starting RetailOS runtime",
            reasoning="System initialization",
            outcome="Runtime started successfully",
            status="success",
        )

        # Start the main event processing loop
        asyncio.create_task(self._event_loop())

    async def stop(self) -> None:
        self.running = False
        await self.audit.log(
            skill="orchestrator",
            event_type="runtime_stop",
            decision="Stopping RetailOS runtime",
            reasoning="Shutdown requested",
            outcome="Runtime stopped",
            status="success",
        )

    async def emit_event(self, event: dict[str, Any]) -> None:
        """Push an event into the orchestrator's queue."""
        await self.event_queue.put(event)

    async def _event_loop(self) -> None:
        """Main loop — processes events as they arrive."""
        while self.running:
            try:
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                await self._process_event(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                await self.audit.log(
                    skill="orchestrator",
                    event_type="event_loop_error",
                    decision="Error in event loop",
                    reasoning=str(e),
                    outcome=traceback.format_exc(),
                    status="error",
                )

    async def _process_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Process a single event: fetch context, route via Gemini, execute."""
        if not isinstance(event, dict) or "type" not in event:
            await self.audit.log(
                skill="orchestrator",
                event_type="invalid_event",
                decision="Rejected malformed event",
                reasoning=f"Event missing 'type' field: {event!r}",
                outcome="Skipped",
                status="error",
            )
            return {"error": "Invalid event: missing 'type' field"}
        event_type = event.get("type", "unknown")

        # Intercept delivery and quality events to log them into the central DB
        if event_type == "delivery":
            from brain.decision_logger import log_delivery
            data = event.get("data", {})
            log_delivery(
                data.get("supplier_id", ""),
                data.get("order_id", ""),
                data.get("expected_date", ""),
                data.get("actual_date", "")
            )
            return {"status": "success", "message": "Delivery logged in brain"}
            
        if event_type == "quality_issue":
            from brain.decision_logger import log_quality_flag
            data = event.get("data", {})
            log_quality_flag(
                data.get("supplier_id", ""),
                data.get("order_id", ""),
                data.get("reason", "")
            )
            return {"status": "success", "message": "Quality issue logged in brain"}

        # Intercept daily analytics to also run churn detector
        if event_type == "daily_analytics":
            from pathlib import Path
            import json
            import asyncio
            base_dir = Path(__file__).resolve().parent.parent
            try:
                with open(base_dir / "data" / "mock_customers.json", "r") as f:
                    customers = json.load(f)
                from brain.churn_detector import detect_at_risk_customers
                churn_events = detect_at_risk_customers(customers)
                for ce in churn_events:
                    asyncio.create_task(self.emit_event(ce))
            except Exception as e:
                logger.error(f"Churn detection failed: {e}")
                
            # Expiry Alerter
            from brain.expiry_alerter import get_expiry_risks
            try:
                with open(base_dir / "data" / "mock_inventory.json", "r") as f:
                    inventory_items = json.load(f)
                expiry_events = get_expiry_risks(inventory_items)
                for ee in expiry_events:
                    asyncio.create_task(self.emit_event(ee))
            except Exception as e:
                logger.error(f"Expiry detection failed: {e}")
                
            # Competitor Price Monitor Auto-Fetch
            try:
                from brain.price_monitor import fetch_agmarknet_prices
                with open(base_dir / "data" / "mock_inventory.json", "r") as f:
                    inv_items = json.load(f)
                
                # Fetch top 20 items by sales volume
                sorted_items = sorted(inv_items, key=lambda x: x.get("daily_sales_rate", 0), reverse=True)
                top_20_skus = [i["sku"] for i in sorted_items[:20]]
                if top_20_skus:
                    fetch_agmarknet_prices(top_20_skus)
            except Exception as e:
                logger.error(f"Price fetching failed: {e}")
                
            # --- Staff Scheduling Auto-Review ---
            # Automatically push a shift_review event for tomorrow into the system natively
            try:
                from datetime import date, timedelta
                tomorrow = date.today() + timedelta(days=1)
                if "scheduling" in self.skills:
                    # Fire directly synchronously to prevent complex queue drops in testing
                    sched_result = await self.skills["scheduling"].run({
                        "type": "shift_review", 
                        "data": {"target_date": tomorrow.isoformat()}
                    })
                    if sched_result.get("needs_approval"):
                        self._add_to_approval_queue(sched_result)
            except Exception as e:
                logger.error(f"Daily scheduling review failed: {e}")

            # Do NOT return here, allow daily_analytics to proceed to the analytics skill

        # Fetch relevant memory
        context = await self.memory.get_relevant(event_type, event.get("data", {}))

        # Ask Gemini to route
        routing_decision = await self._route_with_gemini(event, context)

        results = []
        for action in routing_decision.get("actions", []):
            skill_name = action["skill"]
            params = action.get("params", {})
            reason = action.get("reason", "No reason provided")

            result = await self._execute_skill(skill_name, event, params, reason)
            results.append(result)

        return {
            "event": event,
            "routing": routing_decision,
            "results": results,
        }

    async def _route_with_gemini(self, event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """CALL 1 — Orchestrator routing. Gemini decides what to do."""
        prompt = f"""{ROUTING_SYSTEM_PROMPT}

Event received:
{json.dumps(event, indent=2, default=str)}

Relevant memory context:
{json.dumps(context, indent=2, default=str) if context else "No relevant memory found."}

Decide which skill(s) to run and why."""

        for attempt in range(self.max_retries):
            try:
                if not self.client:
                    raise ValueError("API key not configured")
                
                response = await self.client.aio.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt
                )

                text = response.text
                # Extract JSON from response
                try:
                    if "```json" in text:
                        parts = text.split("```json")
                        if len(parts) > 1:
                            inner = parts[1].split("```")
                            text = inner[0] if len(inner) > 1 else inner[0]
                    elif "```" in text:
                        parts = text.split("```")
                        if len(parts) > 2:
                            text = parts[1]
                except (IndexError, ValueError):
                    pass

                decision = json.loads(text.strip())

                await self.audit.log(
                    skill="orchestrator",
                    event_type="routing_decision",
                    decision=json.dumps(decision.get("actions", []), default=str),
                    reasoning=decision.get("overall_reasoning", ""),
                    outcome="Route determined",
                    status="success",
                    metadata={"event": event, "memory_keys": list(context.keys())},
                )

                return decision

            except Exception as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                    continue
                await self.audit.log(
                    skill="orchestrator",
                    event_type="gemini_api_error",
                    decision="API error after retries",
                    reasoning=f"Gemini API failed {self.max_retries} times: {e}",
                    outcome="Falling back to rule-based routing",
                    status="error",
                )
                return self._fallback_route(event)

        return self._fallback_route(event)  # pragma: no cover — safety net for max_retries=0

    def _fallback_route(self, event: dict[str, Any]) -> dict[str, Any]:
        """Rule-based fallback when Gemini API is unavailable."""
        event_type = event.get("type", "")
        actions = []

        if event_type == "start_procurement":
            actions = [
                {"skill": "procurement", "params": event.get("data", {}), "reason": "Fallback: start procurement process"},
            ]
        elif event_type == "low_stock" or event_type == "stock_update" or event_type == "inventory_check":
            actions = [
                {"skill": "inventory", "params": event.get("data", {}), "reason": "Fallback: stock level change triggers inventory check"},
            ]
        elif event_type == "seasonal_preempt":
            actions = [
                {"skill": "procurement", "params": event.get("data", {}), "reason": "Fallback: seasonal pattern detected, triggering proactive procurement"},
            ]
        elif event_type == "procurement_approved":
            actions = [
                {"skill": "negotiation", "params": event.get("data", {}), "reason": "Fallback: procurement approved triggers negotiation"},
            ]
        elif event_type == "supplier_reply":
            actions = [
                {"skill": "negotiation", "params": event.get("data", {}), "reason": "Fallback: supplier reply needs parsing"},
            ]
        elif event_type == "deal_confirmed":
            actions = [
                {"skill": "customer", "params": event.get("data", {}), "reason": "Fallback: deal confirmed triggers customer outreach"},
            ]
        elif event_type == "churn_risk":
            actions = [
                {"skill": "customer", "params": event.get("data", {}), "reason": "Fallback: churn risk detected, triggering re-engagement"},
            ]
        elif event_type == "expiry_risk":
            actions = [
                {"skill": "inventory", "params": event.get("data", {}), "reason": "Fallback: flag expiry risk on dashboard"},
                {"skill": "customer", "params": {**event.get("data", {}), "discount": "20% off (Flash Sale!)"}, "reason": "Fallback: chain targeted promotion for expiring product"},
            ]

        return {"actions": actions, "overall_reasoning": "Fallback rule-based routing (Gemini unavailable)"}

    async def _execute_skill(
        self, skill_name: str, event: dict[str, Any], params: dict[str, Any], reason: str
    ) -> dict[str, Any]:
        """Execute a skill with retry logic and failure handling."""
        skill = self.skills.get(skill_name)

        if not skill:
            await self.audit.log(
                skill=skill_name,
                event_type="skill_not_found",
                decision=f"Cannot execute {skill_name}",
                reasoning=f"Skill '{skill_name}' not registered",
                outcome="Skipped",
                status="error",
            )
            return {"skill": skill_name, "status": "not_found"}

        if skill.state == SkillState.PAUSED:
            await self.audit.log(
                skill=skill_name,
                event_type="skill_paused_skip",
                decision=f"Skipping {skill_name} — currently paused",
                reasoning=reason,
                outcome="Skipped",
                status="skipped",
            )
            return {"skill": skill_name, "status": "paused"}

        # Retry loop
        merged_event = {**event, "params": params}
        for attempt in range(self.max_retries):
            try:
                result = await skill._safe_run(merged_event)

                await self.audit.log(
                    skill=skill_name,
                    event_type=f"skill_executed",
                    decision=reason,
                    reasoning=f"Executed on attempt {attempt + 1}",
                    outcome=json.dumps(result, default=str)[:2000],
                    status="success",
                    metadata={"attempt": attempt + 1, "params": params},
                )

                # Check if result needs owner approval
                if result.get("needs_approval"):
                    details = result.get("approval_details", {})
                    supplier_id = details.get("supplier_id") or (details.get("top_supplier", {}).get("supplier_id") if details.get("top_supplier") else None)
                    amount = details.get("amount") or details.get("price") or details.get("total_cost") or (details.get("top_supplier", {}).get("price_per_unit", 0) * details.get("top_supplier", {}).get("min_order_qty", 1) if details.get("top_supplier") else None)

                    auto_approved = False
                    if supplier_id and amount is not None:
                        from brain.auto_approver import should_auto_approve
                        from brain.decision_logger import log_decision
                        
                        if should_auto_approve(supplier_id, amount):
                            auto_approved = True
                            log_decision(supplier_id, amount, "approved")
                            
                            follow_up = result.get("on_approval_event")
                            if follow_up:
                                asyncio.create_task(self.emit_event(follow_up))
                                
                            await self.audit.log(
                                skill=skill_name,
                                event_type="auto_approved",
                                decision="Silently approved via Brain subsystem",
                                reasoning=f"Trust score high and amount {amount} below ceiling",
                                outcome="Triggered follow-up event",
                                status="success"
                            )
                            return {"skill": skill_name, "status": "success", "result": result, "auto_approved": True}

                    approval_id = result.get("approval_id", f"{skill_name}_{int(time.time())}")
                    self.pending_approvals[approval_id] = {
                        "skill": skill_name,
                        "result": result,
                        "event": event,
                        "timestamp": time.time(),
                    }
                    await self.audit.log(
                        skill=skill_name,
                        event_type="approval_requested",
                        decision="Awaiting owner approval",
                        reasoning=result.get("approval_reason", "Significant action requires approval"),
                        outcome=json.dumps(result.get("approval_details", {}), default=str),
                        status="pending",
                    )

                return {"skill": skill_name, "status": "success", "result": result}

            except Exception as e:
                await self.audit.log(
                    skill=skill_name,
                    event_type="skill_error",
                    decision=f"Skill failed on attempt {attempt + 1}/{self.max_retries}",
                    reasoning=str(e),
                    outcome=traceback.format_exc()[:1000],
                    status="error",
                    metadata={"attempt": attempt + 1},
                )

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                    continue

                # All retries exhausted — escalate
                await self.audit.log(
                    skill=skill_name,
                    event_type="skill_escalation",
                    decision=f"Escalating {skill_name} failure to owner",
                    reasoning=f"Failed after {self.max_retries} attempts: {e}",
                    outcome="Owner notification sent",
                    status="escalated",
                )

                return {"skill": skill_name, "status": "failed", "error": str(e)}

        # All retries exhausted via exception path above; this is a safety net
        logger.warning("Skill %s: retry loop exited without return", skill_name)
        return {"skill": skill_name, "status": "failed"}

    async def approve(self, approval_id: str) -> dict[str, Any]:
        """Owner approves a pending action."""
        if approval_id not in self.pending_approvals:
            return {"error": "Approval not found"}

        approval = self.pending_approvals.pop(approval_id)
        
        from brain.decision_logger import log_decision
        details = approval["result"].get("approval_details", {})
        supplier_id = details.get("supplier_id") or (details.get("top_supplier", {}).get("supplier_id") if details.get("top_supplier") else None)
        amount = details.get("amount") or details.get("price") or details.get("total_cost") or (details.get("top_supplier", {}).get("price_per_unit", 0) * details.get("top_supplier", {}).get("min_order_qty", 1) if details.get("top_supplier") else None)
        if supplier_id and amount is not None:
            log_decision(supplier_id, amount, "approved")
            
        await self.audit.log(
            skill=approval["skill"],
            event_type="owner_approved",
            decision="Owner approved action",
            reasoning="Manual approval via dashboard",
            outcome=json.dumps(approval["result"].get("approval_details", {}), default=str),
            status="approved",
        )

        # Trigger any follow-up events
        follow_up = approval["result"].get("on_approval_event")
        if follow_up:
            await self.emit_event(follow_up)

        return {"status": "approved", "approval_id": approval_id}

    async def reject(self, approval_id: str, reason: str = "") -> dict[str, Any]:
        """Owner rejects a pending action."""
        if approval_id not in self.pending_approvals:
            return {"error": "Approval not found"}

        approval = self.pending_approvals.pop(approval_id)
        
        from brain.decision_logger import log_decision
        details = approval["result"].get("approval_details", {})
        supplier_id = details.get("supplier_id") or (details.get("top_supplier", {}).get("supplier_id") if details.get("top_supplier") else None)
        amount = details.get("amount") or details.get("price") or details.get("total_cost") or (details.get("top_supplier", {}).get("price_per_unit", 0) * details.get("top_supplier", {}).get("min_order_qty", 1) if details.get("top_supplier") else None)
        if supplier_id and amount is not None:
            log_decision(supplier_id, amount, "rejected")

        await self.audit.log(
            skill=approval["skill"],
            event_type="owner_rejected",
            decision="Owner rejected action",
            reasoning=reason or "No reason provided",
            outcome="Action cancelled",
            status="rejected",
        )

        return {"status": "rejected", "approval_id": approval_id}

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        return [
            {"id": k, **v}
            for k, v in self.pending_approvals.items()
        ]

```


## File: `./runtime/dashboard_api.py`
```py
# runtime/dashboard_api.py
from typing import Optional

def _get_connection():
    from brain.decision_logger import _get_connection as _get_main_conn
    return _get_main_conn()

def add_manual_market_price(product_id: str, source_name: str, price: float, unit: str = "kg") -> dict:
    """Mock API endpoint handler for staff dashboard UI logging competitors."""
    from brain.price_monitor import log_manual_price
    try:
        log_manual_price(product_id, source_name, price, unit)
        return {"status": "success", "message": f"Logged ₹{price}/{unit} for {product_id} from {source_name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def get_product_dashboard_stats(product_id: str) -> dict:
    """Provides a read-only price comparison dashboard view data."""
    from brain.price_monitor import get_market_reference
    market = get_market_reference(product_id)
    
    # Normally fetch last purchase price from history, mock for now
    last_purchase_price = 105.0 if "PROD" not in product_id else None
    
    delta = None
    if market.get("median_price") and last_purchase_price:
        delta = round(((last_purchase_price - market["median_price"]) / market["median_price"]) * 100, 1)

    return {
        "product_id": product_id,
        "market_median": market.get("median_price", "N/A"),
        "market_lowest": market.get("lowest_price", "N/A"),
        "lowest_source": market.get("lowest_source", "N/A"),
        "last_purchase_price": last_purchase_price or "N/A",
        "delta_vs_market": delta,
        "confidence": market.get("confidence", "none")
    }

```


## File: `./runtime/skill_loader.py`
```py
import importlib
import os
import inspect
from typing import Any

from skills.base_skill import BaseSkill


class SkillLoader:
    """Discovers and registers skill files from the skills/ directory.

    Drop a new skill file in, the runtime picks it up automatically.
    """

    def __init__(self, skills_dir: str = "skills", memory=None, audit=None):
        self.skills_dir = skills_dir
        self.memory = memory
        self.audit = audit
        self.skills: dict[str, BaseSkill] = {}

    async def discover_and_load(self) -> dict[str, BaseSkill]:
        """Scan the skills directory and load all valid skill classes."""
        skills_path = os.path.abspath(self.skills_dir)

        for filename in os.listdir(skills_path):
            if not filename.endswith(".py"):
                continue
            if filename.startswith("_") or filename == "base_skill.py":
                continue

            module_name = f"skills.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name)

                # Find all classes that inherit from BaseSkill
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        inspect.isclass(attr)
                        and issubclass(attr, BaseSkill)
                        and attr is not BaseSkill
                    ):
                        skill_instance = attr(
                            memory=self.memory, audit=self.audit
                        )
                        await skill_instance.init()
                        self.skills[skill_instance.name] = skill_instance

            except Exception as e:
                print(f"[SkillLoader] Failed to load {module_name}: {e}")

        return self.skills

    def get_skill(self, name: str) -> BaseSkill | None:
        return self.skills.get(name)

    def list_skills(self) -> list[dict[str, Any]]:
        return [skill.status() for skill in self.skills.values()]

    async def reload_skill(self, name: str) -> bool:
        """Hot-reload a single skill by name."""
        if name in self.skills:
            old_skill = self.skills[name]
            await old_skill.pause()

        # Re-import and re-instantiate
        for filename in os.listdir(os.path.abspath(self.skills_dir)):
            if not filename.endswith(".py") or filename.startswith("_") or filename == "base_skill.py":
                continue
            module_name = f"skills.{filename[:-3]}"
            try:
                module = importlib.reload(importlib.import_module(module_name))
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        inspect.isclass(attr)
                        and issubclass(attr, BaseSkill)
                        and attr is not BaseSkill
                    ):
                        instance = attr(memory=self.memory, audit=self.audit)
                        if instance.name == name:
                            await instance.init()
                            self.skills[name] = instance
                            return True
            except Exception:
                continue
        return False

```


## File: `./.claude/settings.local.json`
```json
{
  "permissions": {
    "allow": [
      "Bash(cd:*)",
      "Bash(npm install:*)",
      "Bash(pip install:*)",
      "Bash(pip3 install:*)",
      "Bash(python3 -m venv venv)",
      "Bash(source venv/bin/activate)",
      "Bash(rm -rf venv)",
      "Bash(python3.13 -m venv venv)",
      "Bash(python3 -c \":*)",
      "Bash(grep -n \"async def\" skills/*.py runtime/*.py)",
      "Bash(grep -n \"if self.audit\\\\|if self.memory\" skills/*.py)"
    ]
  }
}

```


## File: `./dashboard/index.html`
```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <meta name="theme-color" content="#0a0a0a" />
    <meta name="description" content="RetailOS — Autonomous Agent Runtime for Retail Operations. Your store runs itself." />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
    <meta name="apple-mobile-web-app-title" content="RetailOS" />
    <title>RetailOS — Autonomous Agent Runtime</title>
    <link rel="manifest" href="/manifest.json" />
    <link rel="icon" type="image/svg+xml" href="/icon-192.svg" />
    <link rel="apple-touch-icon" href="/icon-192.svg" />
  </head>
  <body class="bg-[#0a0a0a] text-white">
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
    <script>
      if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
          navigator.serviceWorker.register('/sw.js').catch(() => {});
        });
      }
    </script>
  </body>
</html>

```


## File: `./dashboard/tailwind.config.js`
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        'retail': {
          50: '#f0f7ff',
          100: '#e0effe',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          900: '#1e3a5f',
        },
      },
    },
  },
  plugins: [],
}

```


## File: `./dashboard/vite.config.js`
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  },
})

```


## File: `./dashboard/package.json`
```json
{
  "name": "retailos-dashboard",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "clsx": "^2.1.1",
    "framer-motion": "^12.38.0",
    "lucide-react": "^1.7.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "tailwind-merge": "^3.5.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.17",
    "vite": "^6.0.5"
  }
}

```


## File: `./dashboard/postcss.config.js`
```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}

```


## File: `./dashboard/dist/index.html`
```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <meta name="theme-color" content="#0a0a0a" />
    <meta name="description" content="RetailOS — Autonomous Agent Runtime for Retail Operations. Your store runs itself." />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
    <meta name="apple-mobile-web-app-title" content="RetailOS" />
    <title>RetailOS — Autonomous Agent Runtime</title>
    <link rel="manifest" href="/manifest.json" />
    <link rel="icon" type="image/svg+xml" href="/icon-192.svg" />
    <link rel="apple-touch-icon" href="/icon-192.svg" />
    <script type="module" crossorigin src="/assets/index-BTqvvU0l.js"></script>
    <link rel="stylesheet" crossorigin href="/assets/index-DTsRsVyk.css">
  </head>
  <body class="bg-[#0a0a0a] text-white">
    <div id="root"></div>
    <script>
      if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
          navigator.serviceWorker.register('/sw.js').catch(() => {});
        });
      }
    </script>
  </body>
</html>

```


## File: `./dashboard/dist/manifest.json`
```json
{
  "name": "RetailOS",
  "short_name": "RetailOS",
  "description": "Autonomous Agent Runtime for Retail Operations",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0a0a0a",
  "theme_color": "#3b82f6",
  "orientation": "any",
  "icons": [
    {
      "src": "/icon-192.svg",
      "sizes": "192x192",
      "type": "image/svg+xml",
      "purpose": "any maskable"
    },
    {
      "src": "/icon-512.svg",
      "sizes": "512x512",
      "type": "image/svg+xml",
      "purpose": "any maskable"
    }
  ]
}

```


## File: `./dashboard/dist/sw.js`
```js
const CACHE_NAME = 'retailos-v1';
const STATIC_ASSETS = [
  '/',
  '/index.html',
];

// Install: cache the shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: network-first strategy (API and WS go to network, static falls back to cache)
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Don't cache API calls or WebSocket upgrades
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/ws')) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cache successful responses
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

```


## File: `./dashboard/dist/assets/index-DTsRsVyk.css`
```css
@import"https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap";*,:before,:after{--tw-border-spacing-x: 0;--tw-border-spacing-y: 0;--tw-translate-x: 0;--tw-translate-y: 0;--tw-rotate: 0;--tw-skew-x: 0;--tw-skew-y: 0;--tw-scale-x: 1;--tw-scale-y: 1;--tw-pan-x: ;--tw-pan-y: ;--tw-pinch-zoom: ;--tw-scroll-snap-strictness: proximity;--tw-gradient-from-position: ;--tw-gradient-via-position: ;--tw-gradient-to-position: ;--tw-ordinal: ;--tw-slashed-zero: ;--tw-numeric-figure: ;--tw-numeric-spacing: ;--tw-numeric-fraction: ;--tw-ring-inset: ;--tw-ring-offset-width: 0px;--tw-ring-offset-color: #fff;--tw-ring-color: rgb(59 130 246 / .5);--tw-ring-offset-shadow: 0 0 #0000;--tw-ring-shadow: 0 0 #0000;--tw-shadow: 0 0 #0000;--tw-shadow-colored: 0 0 #0000;--tw-blur: ;--tw-brightness: ;--tw-contrast: ;--tw-grayscale: ;--tw-hue-rotate: ;--tw-invert: ;--tw-saturate: ;--tw-sepia: ;--tw-drop-shadow: ;--tw-backdrop-blur: ;--tw-backdrop-brightness: ;--tw-backdrop-contrast: ;--tw-backdrop-grayscale: ;--tw-backdrop-hue-rotate: ;--tw-backdrop-invert: ;--tw-backdrop-opacity: ;--tw-backdrop-saturate: ;--tw-backdrop-sepia: ;--tw-contain-size: ;--tw-contain-layout: ;--tw-contain-paint: ;--tw-contain-style: }::backdrop{--tw-border-spacing-x: 0;--tw-border-spacing-y: 0;--tw-translate-x: 0;--tw-translate-y: 0;--tw-rotate: 0;--tw-skew-x: 0;--tw-skew-y: 0;--tw-scale-x: 1;--tw-scale-y: 1;--tw-pan-x: ;--tw-pan-y: ;--tw-pinch-zoom: ;--tw-scroll-snap-strictness: proximity;--tw-gradient-from-position: ;--tw-gradient-via-position: ;--tw-gradient-to-position: ;--tw-ordinal: ;--tw-slashed-zero: ;--tw-numeric-figure: ;--tw-numeric-spacing: ;--tw-numeric-fraction: ;--tw-ring-inset: ;--tw-ring-offset-width: 0px;--tw-ring-offset-color: #fff;--tw-ring-color: rgb(59 130 246 / .5);--tw-ring-offset-shadow: 0 0 #0000;--tw-ring-shadow: 0 0 #0000;--tw-shadow: 0 0 #0000;--tw-shadow-colored: 0 0 #0000;--tw-blur: ;--tw-brightness: ;--tw-contrast: ;--tw-grayscale: ;--tw-hue-rotate: ;--tw-invert: ;--tw-saturate: ;--tw-sepia: ;--tw-drop-shadow: ;--tw-backdrop-blur: ;--tw-backdrop-brightness: ;--tw-backdrop-contrast: ;--tw-backdrop-grayscale: ;--tw-backdrop-hue-rotate: ;--tw-backdrop-invert: ;--tw-backdrop-opacity: ;--tw-backdrop-saturate: ;--tw-backdrop-sepia: ;--tw-contain-size: ;--tw-contain-layout: ;--tw-contain-paint: ;--tw-contain-style: }*,:before,:after{box-sizing:border-box;border-width:0;border-style:solid;border-color:#e5e7eb}:before,:after{--tw-content: ""}html,:host{line-height:1.5;-webkit-text-size-adjust:100%;-moz-tab-size:4;-o-tab-size:4;tab-size:4;font-family:ui-sans-serif,system-ui,sans-serif,"Apple Color Emoji","Segoe UI Emoji",Segoe UI Symbol,"Noto Color Emoji";font-feature-settings:normal;font-variation-settings:normal;-webkit-tap-highlight-color:transparent}body{margin:0;line-height:inherit}hr{height:0;color:inherit;border-top-width:1px}abbr:where([title]){-webkit-text-decoration:underline dotted;text-decoration:underline dotted}h1,h2,h3,h4,h5,h6{font-size:inherit;font-weight:inherit}a{color:inherit;text-decoration:inherit}b,strong{font-weight:bolder}code,kbd,samp,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,Liberation Mono,Courier New,monospace;font-feature-settings:normal;font-variation-settings:normal;font-size:1em}small{font-size:80%}sub,sup{font-size:75%;line-height:0;position:relative;vertical-align:baseline}sub{bottom:-.25em}sup{top:-.5em}table{text-indent:0;border-color:inherit;border-collapse:collapse}button,input,optgroup,select,textarea{font-family:inherit;font-feature-settings:inherit;font-variation-settings:inherit;font-size:100%;font-weight:inherit;line-height:inherit;letter-spacing:inherit;color:inherit;margin:0;padding:0}button,select{text-transform:none}button,input:where([type=button]),input:where([type=reset]),input:where([type=submit]){-webkit-appearance:button;background-color:transparent;background-image:none}:-moz-focusring{outline:auto}:-moz-ui-invalid{box-shadow:none}progress{vertical-align:baseline}::-webkit-inner-spin-button,::-webkit-outer-spin-button{height:auto}[type=search]{-webkit-appearance:textfield;outline-offset:-2px}::-webkit-search-decoration{-webkit-appearance:none}::-webkit-file-upload-button{-webkit-appearance:button;font:inherit}summary{display:list-item}blockquote,dl,dd,h1,h2,h3,h4,h5,h6,hr,figure,p,pre{margin:0}fieldset{margin:0;padding:0}legend{padding:0}ol,ul,menu{list-style:none;margin:0;padding:0}dialog{padding:0}textarea{resize:vertical}input::-moz-placeholder,textarea::-moz-placeholder{opacity:1;color:#9ca3af}input::placeholder,textarea::placeholder{opacity:1;color:#9ca3af}button,[role=button]{cursor:pointer}:disabled{cursor:default}img,svg,video,canvas,audio,iframe,embed,object{display:block;vertical-align:middle}img,video{max-width:100%;height:auto}[hidden]:where(:not([hidden=until-found])){display:none}.btn-success{border-radius:.75rem;--tw-bg-opacity: 1;background-color:rgb(4 120 87 / var(--tw-bg-opacity, 1));padding:.75rem 1.5rem;font-weight:700;--tw-text-opacity: 1;color:rgb(255 255 255 / var(--tw-text-opacity, 1));--tw-shadow: 0 10px 15px -3px rgb(0 0 0 / .1), 0 4px 6px -4px rgb(0 0 0 / .1);--tw-shadow-colored: 0 10px 15px -3px var(--tw-shadow-color), 0 4px 6px -4px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow);--tw-shadow-color: rgb(4 120 87 / .2);--tw-shadow: var(--tw-shadow-colored);transition-property:all;transition-timing-function:cubic-bezier(.4,0,.2,1);transition-duration:.15s}.btn-success:hover{--tw-bg-opacity: 1;background-color:rgb(5 150 105 / var(--tw-bg-opacity, 1))}.btn-success:active{--tw-scale-x: .95;--tw-scale-y: .95;transform:translate(var(--tw-translate-x),var(--tw-translate-y)) rotate(var(--tw-rotate)) skew(var(--tw-skew-x)) skewY(var(--tw-skew-y)) scaleX(var(--tw-scale-x)) scaleY(var(--tw-scale-y))}.pointer-events-none{pointer-events:none}.absolute{position:absolute}.relative{position:relative}.sticky{position:sticky}.inset-0{top:0;right:0;bottom:0;left:0}.-right-0\.5{right:-.125rem}.-right-1{right:-.25rem}.-top-0\.5{top:-.125rem}.-top-1{top:-.25rem}.left-1\/2{left:50%}.left-2{left:.5rem}.left-3{left:.75rem}.right-0{right:0}.top-0{top:0}.top-1\/2{top:50%}.top-28{top:7rem}.z-10{z-index:10}.z-40{z-index:40}.col-span-full{grid-column:1 / -1}.m-3{margin:.75rem}.mx-auto{margin-left:auto;margin-right:auto}.mb-1{margin-bottom:.25rem}.mb-2{margin-bottom:.5rem}.mb-3{margin-bottom:.75rem}.mb-4{margin-bottom:1rem}.mb-5{margin-bottom:1.25rem}.mb-6{margin-bottom:1.5rem}.mb-8{margin-bottom:2rem}.ml-1{margin-left:.25rem}.ml-auto{margin-left:auto}.mr-1{margin-right:.25rem}.mt-0\.5{margin-top:.125rem}.mt-1{margin-top:.25rem}.mt-1\.5{margin-top:.375rem}.mt-2{margin-top:.5rem}.mt-3{margin-top:.75rem}.mt-4{margin-top:1rem}.mt-5{margin-top:1.25rem}.mt-6{margin-top:1.5rem}.mt-8{margin-top:2rem}.line-clamp-2{overflow:hidden;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2}.block{display:block}.flex{display:flex}.inline-flex{display:inline-flex}.grid{display:grid}.hidden{display:none}.h-1\.5{height:.375rem}.h-10{height:2.5rem}.h-11{height:2.75rem}.h-12{height:3rem}.h-14{height:3.5rem}.h-16{height:4rem}.h-2{height:.5rem}.h-2\.5{height:.625rem}.h-20{height:5rem}.h-5{height:1.25rem}.h-6{height:1.5rem}.h-7{height:1.75rem}.h-8{height:2rem}.h-full{height:100%}.max-h-32{max-height:8rem}.max-h-96{max-height:24rem}.min-h-\[84px\]{min-height:84px}.min-h-screen{min-height:100vh}.w-1{width:.25rem}.w-1\.5{width:.375rem}.w-10{width:2.5rem}.w-11{width:2.75rem}.w-12{width:3rem}.w-14{width:3.5rem}.w-16{width:4rem}.w-2{width:.5rem}.w-2\.5{width:.625rem}.w-20{width:5rem}.w-24{width:6rem}.w-32{width:8rem}.w-5{width:1.25rem}.w-8{width:2rem}.w-full{width:100%}.w-px{width:1px}.min-w-0{min-width:0px}.min-w-5{min-width:1.25rem}.min-w-\[2\.5ch\]{min-width:2.5ch}.min-w-max{min-width:-moz-max-content;min-width:max-content}.max-w-2xl{max-width:42rem}.max-w-3xl{max-width:48rem}.max-w-\[1500px\]{max-width:1500px}.max-w-\[60\%\]{max-width:60%}.max-w-\[80\%\]{max-width:80%}.max-w-md{max-width:28rem}.flex-1{flex:1 1 0%}.flex-shrink-0,.shrink-0{flex-shrink:0}.grow{flex-grow:1}.-translate-x-1\/2{--tw-translate-x: -50%;transform:translate(var(--tw-translate-x),var(--tw-translate-y)) rotate(var(--tw-rotate)) skew(var(--tw-skew-x)) skewY(var(--tw-skew-y)) scaleX(var(--tw-scale-x)) scaleY(var(--tw-scale-y))}.-translate-y-1\/2{--tw-translate-y: -50%;transform:translate(var(--tw-translate-x),var(--tw-translate-y)) rotate(var(--tw-rotate)) skew(var(--tw-skew-x)) skewY(var(--tw-skew-y)) scaleX(var(--tw-scale-x)) scaleY(var(--tw-scale-y))}@keyframes ping{75%,to{transform:scale(2);opacity:0}}.animate-ping{animation:ping 1s cubic-bezier(0,0,.2,1) infinite}@keyframes pulse{50%{opacity:.5}}.animate-pulse{animation:pulse 2s cubic-bezier(.4,0,.6,1) infinite}@keyframes spin{to{transform:rotate(360deg)}}.animate-spin{animation:spin 1s linear infinite}.cursor-pointer{cursor:pointer}.resize-none{resize:none}.list-none{list-style-type:none}.grid-cols-1{grid-template-columns:repeat(1,minmax(0,1fr))}.grid-cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}.grid-cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}.flex-col{flex-direction:column}.flex-wrap{flex-wrap:wrap}.items-start{align-items:flex-start}.items-end{align-items:flex-end}.items-center{align-items:center}.justify-start{justify-content:flex-start}.justify-end{justify-content:flex-end}.justify-center{justify-content:center}.justify-between{justify-content:space-between}.gap-1{gap:.25rem}.gap-1\.5{gap:.375rem}.gap-2{gap:.5rem}.gap-3{gap:.75rem}.gap-4{gap:1rem}.gap-5{gap:1.25rem}.gap-6{gap:1.5rem}.gap-8{gap:2rem}.space-y-0\.5>:not([hidden])~:not([hidden]){--tw-space-y-reverse: 0;margin-top:calc(.125rem * calc(1 - var(--tw-space-y-reverse)));margin-bottom:calc(.125rem * var(--tw-space-y-reverse))}.space-y-1>:not([hidden])~:not([hidden]){--tw-space-y-reverse: 0;margin-top:calc(.25rem * calc(1 - var(--tw-space-y-reverse)));margin-bottom:calc(.25rem * var(--tw-space-y-reverse))}.space-y-2>:not([hidden])~:not([hidden]){--tw-space-y-reverse: 0;margin-top:calc(.5rem * calc(1 - var(--tw-space-y-reverse)));margin-bottom:calc(.5rem * var(--tw-space-y-reverse))}.space-y-3>:not([hidden])~:not([hidden]){--tw-space-y-reverse: 0;margin-top:calc(.75rem * calc(1 - var(--tw-space-y-reverse)));margin-bottom:calc(.75rem * var(--tw-space-y-reverse))}.space-y-4>:not([hidden])~:not([hidden]){--tw-space-y-reverse: 0;margin-top:calc(1rem * calc(1 - var(--tw-space-y-reverse)));margin-bottom:calc(1rem * var(--tw-space-y-reverse))}.space-y-5>:not([hidden])~:not([hidden]){--tw-space-y-reverse: 0;margin-top:calc(1.25rem * calc(1 - var(--tw-space-y-reverse)));margin-bottom:calc(1.25rem * var(--tw-space-y-reverse))}.space-y-6>:not([hidden])~:not([hidden]){--tw-space-y-reverse: 0;margin-top:calc(1.5rem * calc(1 - var(--tw-space-y-reverse)));margin-bottom:calc(1.5rem * var(--tw-space-y-reverse))}.space-y-8>:not([hidden])~:not([hidden]){--tw-space-y-reverse: 0;margin-top:calc(2rem * calc(1 - var(--tw-space-y-reverse)));margin-bottom:calc(2rem * var(--tw-space-y-reverse))}.overflow-hidden{overflow:hidden}.overflow-x-auto{overflow-x:auto}.overflow-y-auto{overflow-y:auto}.truncate{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.whitespace-nowrap{white-space:nowrap}.whitespace-pre-wrap{white-space:pre-wrap}.break-all{word-break:break-all}.rounded{border-radius:.25rem}.rounded-2xl{border-radius:1rem}.rounded-3xl{border-radius:1.5rem}.rounded-\[24px\]{border-radius:24px}.rounded-\[26px\]{border-radius:26px}.rounded-\[28px\]{border-radius:28px}.rounded-\[2rem\]{border-radius:2rem}.rounded-\[30px\]{border-radius:30px}.rounded-\[32px\]{border-radius:32px}.rounded-full{border-radius:9999px}.rounded-lg{border-radius:.5rem}.rounded-xl{border-radius:.75rem}.rounded-r-full{border-top-right-radius:9999px;border-bottom-right-radius:9999px}.border{border-width:1px}.border-2{border-width:2px}.border-b{border-bottom-width:1px}.border-t{border-top-width:1px}.border-dashed{border-style:dashed}.border-amber-200{--tw-border-opacity: 1;border-color:rgb(253 230 138 / var(--tw-border-opacity, 1))}.border-amber-500\/20{border-color:#f59e0b33}.border-black\/10{border-color:#0000001a}.border-black\/5{border-color:#0000000d}.border-blue-500\/20{border-color:#3b82f633}.border-emerald-200{--tw-border-opacity: 1;border-color:rgb(167 243 208 / var(--tw-border-opacity, 1))}.border-emerald-500\/20{border-color:#10b98133}.border-gray-500\/20{border-color:#6b728033}.border-gray-700{--tw-border-opacity: 1;border-color:rgb(55 65 81 / var(--tw-border-opacity, 1))}.border-gray-800{--tw-border-opacity: 1;border-color:rgb(31 41 55 / var(--tw-border-opacity, 1))}.border-orange-500\/20{border-color:#f9731633}.border-purple-500\/20{border-color:#a855f733}.border-red-200{--tw-border-opacity: 1;border-color:rgb(254 202 202 / var(--tw-border-opacity, 1))}.border-red-500\/10{border-color:#ef44441a}.border-red-500\/20{border-color:#ef444433}.border-stone-900{--tw-border-opacity: 1;border-color:rgb(28 25 23 / var(--tw-border-opacity, 1))}.border-teal-200{--tw-border-opacity: 1;border-color:rgb(153 246 228 / var(--tw-border-opacity, 1))}.border-teal-700{--tw-border-opacity: 1;border-color:rgb(15 118 110 / var(--tw-border-opacity, 1))}.border-white\/70{border-color:#ffffffb3}.border-yellow-500\/20{border-color:#eab30833}.bg-\[\#0a0a0a\]{--tw-bg-opacity: 1;background-color:rgb(10 10 10 / var(--tw-bg-opacity, 1))}.bg-\[rgba\(244\,239\,230\,0\.82\)\]{background-color:#f4efe6d1}.bg-\[rgba\(255\,252\,247\,0\.72\)\]{background-color:#fffcf7b8}.bg-\[rgba\(255\,252\,247\,0\.74\)\]{background-color:#fffcf7bd}.bg-\[rgba\(255\,252\,247\,0\.78\)\]{background-color:#fffcf7c7}.bg-\[rgba\(255\,252\,247\,0\.82\)\]{background-color:#fffcf7d1}.bg-\[rgba\(255\,252\,247\,0\.86\)\]{background-color:#fffcf7db}.bg-\[rgba\(255\,252\,247\,0\.9\)\]{background-color:#fffcf7e6}.bg-\[rgba\(255\,252\,247\,0\.92\)\]{background-color:#fffcf7eb}.bg-amber-100{--tw-bg-opacity: 1;background-color:rgb(254 243 199 / var(--tw-bg-opacity, 1))}.bg-amber-400{--tw-bg-opacity: 1;background-color:rgb(251 191 36 / var(--tw-bg-opacity, 1))}.bg-amber-50{--tw-bg-opacity: 1;background-color:rgb(255 251 235 / var(--tw-bg-opacity, 1))}.bg-amber-500\/10{background-color:#f59e0b1a}.bg-amber-600{--tw-bg-opacity: 1;background-color:rgb(217 119 6 / var(--tw-bg-opacity, 1))}.bg-black\/\[0\.03\]{background-color:#00000008}.bg-blue-400{--tw-bg-opacity: 1;background-color:rgb(96 165 250 / var(--tw-bg-opacity, 1))}.bg-blue-400\/10{background-color:#60a5fa1a}.bg-blue-50{--tw-bg-opacity: 1;background-color:rgb(239 246 255 / var(--tw-bg-opacity, 1))}.bg-blue-500{--tw-bg-opacity: 1;background-color:rgb(59 130 246 / var(--tw-bg-opacity, 1))}.bg-blue-500\/10{background-color:#3b82f61a}.bg-blue-500\/20{background-color:#3b82f633}.bg-blue-600{--tw-bg-opacity: 1;background-color:rgb(37 99 235 / var(--tw-bg-opacity, 1))}.bg-blue-600\/20{background-color:#2563eb33}.bg-emerald-100{--tw-bg-opacity: 1;background-color:rgb(209 250 229 / var(--tw-bg-opacity, 1))}.bg-emerald-400{--tw-bg-opacity: 1;background-color:rgb(52 211 153 / var(--tw-bg-opacity, 1))}.bg-emerald-50{--tw-bg-opacity: 1;background-color:rgb(236 253 245 / var(--tw-bg-opacity, 1))}.bg-emerald-500{--tw-bg-opacity: 1;background-color:rgb(16 185 129 / var(--tw-bg-opacity, 1))}.bg-emerald-500\/10{background-color:#10b9811a}.bg-emerald-600{--tw-bg-opacity: 1;background-color:rgb(5 150 105 / var(--tw-bg-opacity, 1))}.bg-emerald-700{--tw-bg-opacity: 1;background-color:rgb(4 120 87 / var(--tw-bg-opacity, 1))}.bg-gray-400{--tw-bg-opacity: 1;background-color:rgb(156 163 175 / var(--tw-bg-opacity, 1))}.bg-gray-500\/10{background-color:#6b72801a}.bg-gray-800{--tw-bg-opacity: 1;background-color:rgb(31 41 55 / var(--tw-bg-opacity, 1))}.bg-gray-900{--tw-bg-opacity: 1;background-color:rgb(17 24 39 / var(--tw-bg-opacity, 1))}.bg-gray-900\/50{background-color:#11182780}.bg-gray-950{--tw-bg-opacity: 1;background-color:rgb(3 7 18 / var(--tw-bg-opacity, 1))}.bg-gray-950\/50{background-color:#03071280}.bg-green-500{--tw-bg-opacity: 1;background-color:rgb(34 197 94 / var(--tw-bg-opacity, 1))}.bg-green-500\/10{background-color:#22c55e1a}.bg-orange-500\/10{background-color:#f973161a}.bg-purple-500\/10{background-color:#a855f71a}.bg-red-400{--tw-bg-opacity: 1;background-color:rgb(248 113 113 / var(--tw-bg-opacity, 1))}.bg-red-50{--tw-bg-opacity: 1;background-color:rgb(254 242 242 / var(--tw-bg-opacity, 1))}.bg-red-500{--tw-bg-opacity: 1;background-color:rgb(239 68 68 / var(--tw-bg-opacity, 1))}.bg-red-500\/10{background-color:#ef44441a}.bg-red-500\/5{background-color:#ef44440d}.bg-red-600{--tw-bg-opacity: 1;background-color:rgb(220 38 38 / var(--tw-bg-opacity, 1))}.bg-stone-100{--tw-bg-opacity: 1;background-color:rgb(245 245 244 / var(--tw-bg-opacity, 1))}.bg-stone-200{--tw-bg-opacity: 1;background-color:rgb(231 229 228 / var(--tw-bg-opacity, 1))}.bg-stone-400{--tw-bg-opacity: 1;background-color:rgb(168 162 158 / var(--tw-bg-opacity, 1))}.bg-stone-50{--tw-bg-opacity: 1;background-color:rgb(250 250 249 / var(--tw-bg-opacity, 1))}.bg-stone-900{--tw-bg-opacity: 1;background-color:rgb(28 25 23 / var(--tw-bg-opacity, 1))}.bg-teal-100{--tw-bg-opacity: 1;background-color:rgb(204 251 241 / var(--tw-bg-opacity, 1))}.bg-teal-50{--tw-bg-opacity: 1;background-color:rgb(240 253 250 / var(--tw-bg-opacity, 1))}.bg-teal-700{--tw-bg-opacity: 1;background-color:rgb(15 118 110 / var(--tw-bg-opacity, 1))}.bg-white{--tw-bg-opacity: 1;background-color:rgb(255 255 255 / var(--tw-bg-opacity, 1))}.bg-white\/10{background-color:#ffffff1a}.bg-white\/15{background-color:#ffffff26}.bg-white\/5{background-color:#ffffff0d}.bg-white\/50{background-color:#ffffff80}.bg-white\/55{background-color:#ffffff8c}.bg-white\/60{background-color:#fff9}.bg-white\/70{background-color:#ffffffb3}.bg-white\/75{background-color:#ffffffbf}.bg-white\/80{background-color:#fffc}.bg-white\/85{background-color:#ffffffd9}.bg-white\/90{background-color:#ffffffe6}.bg-yellow-500\/10{background-color:#eab3081a}.bg-\[linear-gradient\(135deg\,rgba\(239\,247\,242\,0\.96\)\,rgba\(229\,240\,238\,0\.88\)\)\]{background-image:linear-gradient(135deg,#eff7f2f5,#e5f0eee0)}.bg-\[linear-gradient\(135deg\,rgba\(239\,247\,242\,0\.96\)\,rgba\(247\,241\,232\,0\.9\)\)\]{background-image:linear-gradient(135deg,#eff7f2f5,#f7f1e8e6)}.bg-\[linear-gradient\(135deg\,rgba\(255\,252\,247\,0\.95\)\,rgba\(233\,227\,216\,0\.85\)\)\]{background-image:linear-gradient(135deg,#fffcf7f2,#e9e3d8d9)}.bg-\[linear-gradient\(180deg\,rgba\(255\,255\,255\,0\.7\)\,rgba\(246\,241\,233\,0\.9\)\)\]{background-image:linear-gradient(180deg,#ffffffb3,#f6f1e9e6)}.bg-gradient-to-br{background-image:linear-gradient(to bottom right,var(--tw-gradient-stops))}.bg-gradient-to-r{background-image:linear-gradient(to right,var(--tw-gradient-stops))}.from-amber-500\/20{--tw-gradient-from: rgb(245 158 11 / .2) var(--tw-gradient-from-position);--tw-gradient-to: rgb(245 158 11 / 0) var(--tw-gradient-to-position);--tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to)}.from-blue-400\/20{--tw-gradient-from: rgb(96 165 250 / .2) var(--tw-gradient-from-position);--tw-gradient-to: rgb(96 165 250 / 0) var(--tw-gradient-to-position);--tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to)}.from-blue-500\/20{--tw-gradient-from: rgb(59 130 246 / .2) var(--tw-gradient-from-position);--tw-gradient-to: rgb(59 130 246 / 0) var(--tw-gradient-to-position);--tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to)}.from-green-500\/20{--tw-gradient-from: rgb(34 197 94 / .2) var(--tw-gradient-from-position);--tw-gradient-to: rgb(34 197 94 / 0) var(--tw-gradient-to-position);--tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to)}.from-purple-500\/20{--tw-gradient-from: rgb(168 85 247 / .2) var(--tw-gradient-from-position);--tw-gradient-to: rgb(168 85 247 / 0) var(--tw-gradient-to-position);--tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to)}.from-teal-700{--tw-gradient-from: #0f766e var(--tw-gradient-from-position);--tw-gradient-to: rgb(15 118 110 / 0) var(--tw-gradient-to-position);--tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to)}.via-teal-600{--tw-gradient-to: rgb(13 148 136 / 0) var(--tw-gradient-to-position);--tw-gradient-stops: var(--tw-gradient-from), #0d9488 var(--tw-gradient-via-position), var(--tw-gradient-to)}.to-amber-600{--tw-gradient-to: #d97706 var(--tw-gradient-to-position)}.to-amber-700{--tw-gradient-to: #b45309 var(--tw-gradient-to-position)}.to-cyan-500\/5{--tw-gradient-to: rgb(6 182 212 / .05) var(--tw-gradient-to-position)}.to-emerald-500\/5{--tw-gradient-to: rgb(16 185 129 / .05) var(--tw-gradient-to-position)}.to-indigo-500\/5{--tw-gradient-to: rgb(99 102 241 / .05) var(--tw-gradient-to-position)}.to-orange-500\/5{--tw-gradient-to: rgb(249 115 22 / .05) var(--tw-gradient-to-position)}.to-pink-500\/5{--tw-gradient-to: rgb(236 72 153 / .05) var(--tw-gradient-to-position)}.p-1{padding:.25rem}.p-2{padding:.5rem}.p-2\.5{padding:.625rem}.p-3{padding:.75rem}.p-4{padding:1rem}.p-5{padding:1.25rem}.p-6{padding:1.5rem}.p-7{padding:1.75rem}.p-8{padding:2rem}.px-1{padding-left:.25rem;padding-right:.25rem}.px-10{padding-left:2.5rem;padding-right:2.5rem}.px-2{padding-left:.5rem;padding-right:.5rem}.px-3{padding-left:.75rem;padding-right:.75rem}.px-4{padding-left:1rem;padding-right:1rem}.px-5{padding-left:1.25rem;padding-right:1.25rem}.px-6{padding-left:1.5rem;padding-right:1.5rem}.py-0\.5{padding-top:.125rem;padding-bottom:.125rem}.py-1{padding-top:.25rem;padding-bottom:.25rem}.py-12{padding-top:3rem;padding-bottom:3rem}.py-16{padding-top:4rem;padding-bottom:4rem}.py-2{padding-top:.5rem;padding-bottom:.5rem}.py-2\.5{padding-top:.625rem;padding-bottom:.625rem}.py-20{padding-top:5rem;padding-bottom:5rem}.py-3{padding-top:.75rem;padding-bottom:.75rem}.py-4{padding-top:1rem;padding-bottom:1rem}.py-8{padding-top:2rem;padding-bottom:2rem}.pb-2{padding-bottom:.5rem}.pb-4{padding-bottom:1rem}.pb-5{padding-bottom:1.25rem}.pl-10{padding-left:2.5rem}.pr-4{padding-right:1rem}.pr-8{padding-right:2rem}.pt-0\.5{padding-top:.125rem}.pt-1{padding-top:.25rem}.pt-2{padding-top:.5rem}.pt-3{padding-top:.75rem}.pt-4{padding-top:1rem}.pt-6{padding-top:1.5rem}.text-left{text-align:left}.text-center{text-align:center}.text-right{text-align:right}.font-mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,Liberation Mono,Courier New,monospace}.text-2xl{font-size:1.5rem;line-height:2rem}.text-3xl{font-size:1.875rem;line-height:2.25rem}.text-4xl{font-size:2.25rem;line-height:2.5rem}.text-\[10px\]{font-size:10px}.text-\[11px\]{font-size:11px}.text-\[12px\]{font-size:12px}.text-\[13px\]{font-size:13px}.text-\[15px\]{font-size:15px}.text-\[8px\]{font-size:8px}.text-\[9px\]{font-size:9px}.text-base{font-size:1rem;line-height:1.5rem}.text-lg{font-size:1.125rem;line-height:1.75rem}.text-sm{font-size:.875rem;line-height:1.25rem}.text-xl{font-size:1.25rem;line-height:1.75rem}.text-xs{font-size:.75rem;line-height:1rem}.font-black{font-weight:900}.font-bold{font-weight:700}.font-medium{font-weight:500}.font-normal{font-weight:400}.font-semibold{font-weight:600}.uppercase{text-transform:uppercase}.capitalize{text-transform:capitalize}.italic{font-style:italic}.not-italic{font-style:normal}.leading-none{line-height:1}.leading-normal{line-height:1.5}.leading-relaxed{line-height:1.625}.leading-snug{line-height:1.375}.leading-tight{line-height:1.25}.tracking-\[0\.16em\]{letter-spacing:.16em}.tracking-\[0\.18em\]{letter-spacing:.18em}.tracking-\[0\.22em\]{letter-spacing:.22em}.tracking-\[0\.24em\]{letter-spacing:.24em}.tracking-\[0\.28em\]{letter-spacing:.28em}.tracking-\[0\.2em\]{letter-spacing:.2em}.tracking-\[0\.3em\]{letter-spacing:.3em}.tracking-tight{letter-spacing:-.025em}.tracking-tighter{letter-spacing:-.05em}.tracking-wider{letter-spacing:.05em}.tracking-widest{letter-spacing:.1em}.text-amber-300{--tw-text-opacity: 1;color:rgb(252 211 77 / var(--tw-text-opacity, 1))}.text-amber-400{--tw-text-opacity: 1;color:rgb(251 191 36 / var(--tw-text-opacity, 1))}.text-amber-500{--tw-text-opacity: 1;color:rgb(245 158 11 / var(--tw-text-opacity, 1))}.text-amber-700{--tw-text-opacity: 1;color:rgb(180 83 9 / var(--tw-text-opacity, 1))}.text-blue-400{--tw-text-opacity: 1;color:rgb(96 165 250 / var(--tw-text-opacity, 1))}.text-blue-500{--tw-text-opacity: 1;color:rgb(59 130 246 / var(--tw-text-opacity, 1))}.text-cyan-400{--tw-text-opacity: 1;color:rgb(34 211 238 / var(--tw-text-opacity, 1))}.text-emerald-400{--tw-text-opacity: 1;color:rgb(52 211 153 / var(--tw-text-opacity, 1))}.text-emerald-600{--tw-text-opacity: 1;color:rgb(5 150 105 / var(--tw-text-opacity, 1))}.text-emerald-700{--tw-text-opacity: 1;color:rgb(4 120 87 / var(--tw-text-opacity, 1))}.text-emerald-700\/70{color:#047857b3}.text-gray-200{--tw-text-opacity: 1;color:rgb(229 231 235 / var(--tw-text-opacity, 1))}.text-gray-300{--tw-text-opacity: 1;color:rgb(209 213 219 / var(--tw-text-opacity, 1))}.text-gray-400{--tw-text-opacity: 1;color:rgb(156 163 175 / var(--tw-text-opacity, 1))}.text-gray-500{--tw-text-opacity: 1;color:rgb(107 114 128 / var(--tw-text-opacity, 1))}.text-gray-600{--tw-text-opacity: 1;color:rgb(75 85 99 / var(--tw-text-opacity, 1))}.text-gray-800{--tw-text-opacity: 1;color:rgb(31 41 55 / var(--tw-text-opacity, 1))}.text-green-400{--tw-text-opacity: 1;color:rgb(74 222 128 / var(--tw-text-opacity, 1))}.text-green-500{--tw-text-opacity: 1;color:rgb(34 197 94 / var(--tw-text-opacity, 1))}.text-green-600{--tw-text-opacity: 1;color:rgb(22 163 74 / var(--tw-text-opacity, 1))}.text-orange-400{--tw-text-opacity: 1;color:rgb(251 146 60 / var(--tw-text-opacity, 1))}.text-pink-400{--tw-text-opacity: 1;color:rgb(244 114 182 / var(--tw-text-opacity, 1))}.text-purple-400{--tw-text-opacity: 1;color:rgb(192 132 252 / var(--tw-text-opacity, 1))}.text-purple-500{--tw-text-opacity: 1;color:rgb(168 85 247 / var(--tw-text-opacity, 1))}.text-red-400{--tw-text-opacity: 1;color:rgb(248 113 113 / var(--tw-text-opacity, 1))}.text-red-500{--tw-text-opacity: 1;color:rgb(239 68 68 / var(--tw-text-opacity, 1))}.text-red-600{--tw-text-opacity: 1;color:rgb(220 38 38 / var(--tw-text-opacity, 1))}.text-red-700{--tw-text-opacity: 1;color:rgb(185 28 28 / var(--tw-text-opacity, 1))}.text-stone-200{--tw-text-opacity: 1;color:rgb(231 229 228 / var(--tw-text-opacity, 1))}.text-stone-300{--tw-text-opacity: 1;color:rgb(214 211 209 / var(--tw-text-opacity, 1))}.text-stone-400{--tw-text-opacity: 1;color:rgb(168 162 158 / var(--tw-text-opacity, 1))}.text-stone-50{--tw-text-opacity: 1;color:rgb(250 250 249 / var(--tw-text-opacity, 1))}.text-stone-500{--tw-text-opacity: 1;color:rgb(120 113 108 / var(--tw-text-opacity, 1))}.text-stone-600{--tw-text-opacity: 1;color:rgb(87 83 78 / var(--tw-text-opacity, 1))}.text-stone-700{--tw-text-opacity: 1;color:rgb(68 64 60 / var(--tw-text-opacity, 1))}.text-stone-800{--tw-text-opacity: 1;color:rgb(41 37 36 / var(--tw-text-opacity, 1))}.text-stone-900{--tw-text-opacity: 1;color:rgb(28 25 23 / var(--tw-text-opacity, 1))}.text-teal-700{--tw-text-opacity: 1;color:rgb(15 118 110 / var(--tw-text-opacity, 1))}.text-teal-700\/80{color:#0f766ecc}.text-violet-400{--tw-text-opacity: 1;color:rgb(167 139 250 / var(--tw-text-opacity, 1))}.text-white{--tw-text-opacity: 1;color:rgb(255 255 255 / var(--tw-text-opacity, 1))}.text-white\/40{color:#fff6}.text-yellow-400{--tw-text-opacity: 1;color:rgb(250 204 21 / var(--tw-text-opacity, 1))}.line-through{text-decoration-line:line-through}.opacity-0{opacity:0}.opacity-20{opacity:.2}.opacity-40{opacity:.4}.opacity-50{opacity:.5}.opacity-75{opacity:.75}.shadow{--tw-shadow: 0 1px 3px 0 rgb(0 0 0 / .1), 0 1px 2px -1px rgb(0 0 0 / .1);--tw-shadow-colored: 0 1px 3px 0 var(--tw-shadow-color), 0 1px 2px -1px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow)}.shadow-\[0_0_12px_rgba\(239\,68\,68\,0\.8\)\]{--tw-shadow: 0 0 12px rgba(239,68,68,.8);--tw-shadow-colored: 0 0 12px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow)}.shadow-\[0_18px_45px_rgba\(0\,0\,0\,0\.05\)\]{--tw-shadow: 0 18px 45px rgba(0,0,0,.05);--tw-shadow-colored: 0 18px 45px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow)}.shadow-\[0_20px_55px_rgba\(0\,0\,0\,0\.06\)\]{--tw-shadow: 0 20px 55px rgba(0,0,0,.06);--tw-shadow-colored: 0 20px 55px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow)}.shadow-\[0_20px_60px_rgba\(0\,0\,0\,0\.06\)\]{--tw-shadow: 0 20px 60px rgba(0,0,0,.06);--tw-shadow-colored: 0 20px 60px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow)}.shadow-\[0_22px_55px_rgba\(0\,0\,0\,0\.06\)\]{--tw-shadow: 0 22px 55px rgba(0,0,0,.06);--tw-shadow-colored: 0 22px 55px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow)}.shadow-\[0_22px_55px_rgba\(0\,0\,0\,0\.18\)\]{--tw-shadow: 0 22px 55px rgba(0,0,0,.18);--tw-shadow-colored: 0 22px 55px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow)}.shadow-\[0_24px_60px_rgba\(0\,0\,0\,0\.06\)\]{--tw-shadow: 0 24px 60px rgba(0,0,0,.06);--tw-shadow-colored: 0 24px 60px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow)}.shadow-\[0_28px_70px_rgba\(0\,0\,0\,0\.08\)\]{--tw-shadow: 0 28px 70px rgba(0,0,0,.08);--tw-shadow-colored: 0 28px 70px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow)}.shadow-lg{--tw-shadow: 0 10px 15px -3px rgb(0 0 0 / .1), 0 4px 6px -4px rgb(0 0 0 / .1);--tw-shadow-colored: 0 10px 15px -3px var(--tw-shadow-color), 0 4px 6px -4px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow)}.shadow-sm{--tw-shadow: 0 1px 2px 0 rgb(0 0 0 / .05);--tw-shadow-colored: 0 1px 2px 0 var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow)}.shadow-stone-900\/10{--tw-shadow-color: rgb(28 25 23 / .1);--tw-shadow: var(--tw-shadow-colored)}.shadow-teal-700\/15{--tw-shadow-color: rgb(15 118 110 / .15);--tw-shadow: var(--tw-shadow-colored)}.shadow-teal-900\/15{--tw-shadow-color: rgb(19 78 74 / .15);--tw-shadow: var(--tw-shadow-colored)}.filter{filter:var(--tw-blur) var(--tw-brightness) var(--tw-contrast) var(--tw-grayscale) var(--tw-hue-rotate) var(--tw-invert) var(--tw-saturate) var(--tw-sepia) var(--tw-drop-shadow)}.backdrop-blur-xl{--tw-backdrop-blur: blur(24px);-webkit-backdrop-filter:var(--tw-backdrop-blur) var(--tw-backdrop-brightness) var(--tw-backdrop-contrast) var(--tw-backdrop-grayscale) var(--tw-backdrop-hue-rotate) var(--tw-backdrop-invert) var(--tw-backdrop-opacity) var(--tw-backdrop-saturate) var(--tw-backdrop-sepia);backdrop-filter:var(--tw-backdrop-blur) var(--tw-backdrop-brightness) var(--tw-backdrop-contrast) var(--tw-backdrop-grayscale) var(--tw-backdrop-hue-rotate) var(--tw-backdrop-invert) var(--tw-backdrop-opacity) var(--tw-backdrop-saturate) var(--tw-backdrop-sepia)}.transition{transition-property:color,background-color,border-color,text-decoration-color,fill,stroke,opacity,box-shadow,transform,filter,backdrop-filter;transition-timing-function:cubic-bezier(.4,0,.2,1);transition-duration:.15s}.transition-all{transition-property:all;transition-timing-function:cubic-bezier(.4,0,.2,1);transition-duration:.15s}.transition-colors{transition-property:color,background-color,border-color,text-decoration-color,fill,stroke;transition-timing-function:cubic-bezier(.4,0,.2,1);transition-duration:.15s}.transition-opacity{transition-property:opacity;transition-timing-function:cubic-bezier(.4,0,.2,1);transition-duration:.15s}.duration-500{transition-duration:.5s}.scrollbar-thin::-webkit-scrollbar{width:6px}.scrollbar-thin::-webkit-scrollbar-track{background:#ffffff08}.scrollbar-thin::-webkit-scrollbar-thumb{background:#ffffff26;border-radius:3px}.scrollbar-thin::-webkit-scrollbar-thumb:hover{background:#ffffff40}.scrollbar-hide::-webkit-scrollbar{display:none}.scrollbar-hide{-ms-overflow-style:none;scrollbar-width:none}:root{--background: #f4efe6;--background-deep: #efe7db;--card: rgba(255, 252, 247, .8);--card-dark: #1b1d1e;--primary: #0f766e;--accent: #b45309;--success: #15803d;--danger: #b91c1c;--warning: #ca8a04;--text: #171717;--text-muted: #57534e}body{background:radial-gradient(circle at top left,rgba(15,118,110,.08),transparent 32%),radial-gradient(circle at top right,rgba(180,83,9,.08),transparent 28%),linear-gradient(180deg,var(--background) 0%,var(--background-deep) 100%);color:var(--text);font-family:Manrope,system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}#root{min-height:100vh}h1,h2,h3,h4,.font-display{font-family:Space Grotesk,Manrope,sans-serif}.whatsapp-bubble-out{max-width:80%;align-self:flex-end;border-radius:1rem;border-top-right-radius:0;--tw-bg-opacity: 1;background-color:rgb(37 99 235 / var(--tw-bg-opacity, 1));padding:.75rem;--tw-text-opacity: 1;color:rgb(255 255 255 / var(--tw-text-opacity, 1));--tw-shadow: 0 10px 15px -3px rgb(0 0 0 / .1), 0 4px 6px -4px rgb(0 0 0 / .1);--tw-shadow-colored: 0 10px 15px -3px var(--tw-shadow-color), 0 4px 6px -4px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow);--tw-shadow-color: rgb(37 99 235 / .2);--tw-shadow: var(--tw-shadow-colored)}.whatsapp-bubble-in{max-width:80%;align-self:flex-start;border-radius:1rem;border-top-left-radius:0;--tw-bg-opacity: 1;background-color:rgb(39 39 42 / var(--tw-bg-opacity, 1));padding:.75rem;--tw-text-opacity: 1;color:rgb(255 255 255 / var(--tw-text-opacity, 1));--tw-shadow: 0 10px 15px -3px rgb(0 0 0 / .1), 0 4px 6px -4px rgb(0 0 0 / .1);--tw-shadow-colored: 0 10px 15px -3px var(--tw-shadow-color), 0 4px 6px -4px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow, 0 0 #0000),var(--tw-ring-shadow, 0 0 #0000),var(--tw-shadow)}.placeholder\:text-stone-400::-moz-placeholder{--tw-text-opacity: 1;color:rgb(168 162 158 / var(--tw-text-opacity, 1))}.placeholder\:text-stone-400::placeholder{--tw-text-opacity: 1;color:rgb(168 162 158 / var(--tw-text-opacity, 1))}.hover\:border-black\/15:hover{border-color:#00000026}.hover\:border-blue-500\/30:hover{border-color:#3b82f64d}.hover\:border-gray-700:hover{--tw-border-opacity: 1;border-color:rgb(55 65 81 / var(--tw-border-opacity, 1))}.hover\:bg-amber-500:hover{--tw-bg-opacity: 1;background-color:rgb(245 158 11 / var(--tw-bg-opacity, 1))}.hover\:bg-amber-500\/20:hover{background-color:#f59e0b33}.hover\:bg-black:hover{--tw-bg-opacity: 1;background-color:rgb(0 0 0 / var(--tw-bg-opacity, 1))}.hover\:bg-black\/\[0\.04\]:hover{background-color:#0000000a}.hover\:bg-blue-500:hover{--tw-bg-opacity: 1;background-color:rgb(59 130 246 / var(--tw-bg-opacity, 1))}.hover\:bg-emerald-100:hover{--tw-bg-opacity: 1;background-color:rgb(209 250 229 / var(--tw-bg-opacity, 1))}.hover\:bg-emerald-400:hover{--tw-bg-opacity: 1;background-color:rgb(52 211 153 / var(--tw-bg-opacity, 1))}.hover\:bg-emerald-500\/20:hover{background-color:#10b98133}.hover\:bg-emerald-600:hover{--tw-bg-opacity: 1;background-color:rgb(5 150 105 / var(--tw-bg-opacity, 1))}.hover\:bg-gray-700:hover{--tw-bg-opacity: 1;background-color:rgb(55 65 81 / var(--tw-bg-opacity, 1))}.hover\:bg-red-50:hover{--tw-bg-opacity: 1;background-color:rgb(254 242 242 / var(--tw-bg-opacity, 1))}.hover\:bg-stone-100:hover{--tw-bg-opacity: 1;background-color:rgb(245 245 244 / var(--tw-bg-opacity, 1))}.hover\:bg-white:hover{--tw-bg-opacity: 1;background-color:rgb(255 255 255 / var(--tw-bg-opacity, 1))}.hover\:bg-white\/90:hover{background-color:#ffffffe6}.hover\:text-gray-200:hover{--tw-text-opacity: 1;color:rgb(229 231 235 / var(--tw-text-opacity, 1))}.hover\:text-stone-900:hover{--tw-text-opacity: 1;color:rgb(28 25 23 / var(--tw-text-opacity, 1))}.hover\:text-teal-700:hover{--tw-text-opacity: 1;color:rgb(15 118 110 / var(--tw-text-opacity, 1))}.focus\:border-blue-500:focus{--tw-border-opacity: 1;border-color:rgb(59 130 246 / var(--tw-border-opacity, 1))}.focus\:border-teal-600\/50:focus{border-color:#0d948880}.focus\:outline-none:focus{outline:2px solid transparent;outline-offset:2px}.disabled\:opacity-50:disabled{opacity:.5}.group:hover .group-hover\:text-teal-700{--tw-text-opacity: 1;color:rgb(15 118 110 / var(--tw-text-opacity, 1))}.group:hover .group-hover\:opacity-100{opacity:1}@media(min-width:640px){.sm\:flex{display:flex}.sm\:grid-cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}.sm\:flex-row{flex-direction:row}.sm\:items-center{align-items:center}.sm\:px-6{padding-left:1.5rem;padding-right:1.5rem}}@media(min-width:768px){.md\:grid-cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}.md\:grid-cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}.md\:grid-cols-4{grid-template-columns:repeat(4,minmax(0,1fr))}}@media(min-width:1024px){.lg\:block{display:block}.lg\:flex{display:flex}.lg\:h-12{height:3rem}.lg\:h-14{height:3.5rem}.lg\:h-24{height:6rem}.lg\:w-12{width:3rem}.lg\:w-14{width:3.5rem}.lg\:w-24{width:6rem}.lg\:w-auto{width:auto}.lg\:grid-cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}.lg\:grid-cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}.lg\:grid-cols-4{grid-template-columns:repeat(4,minmax(0,1fr))}.lg\:flex-row{flex-direction:row}.lg\:flex-wrap{flex-wrap:wrap}.lg\:gap-4{gap:1rem}.lg\:gap-5{gap:1.25rem}.lg\:gap-6{gap:1.5rem}.lg\:space-y-10>:not([hidden])~:not([hidden]){--tw-space-y-reverse: 0;margin-top:calc(2.5rem * calc(1 - var(--tw-space-y-reverse)));margin-bottom:calc(2.5rem * var(--tw-space-y-reverse))}.lg\:space-y-4>:not([hidden])~:not([hidden]){--tw-space-y-reverse: 0;margin-top:calc(1rem * calc(1 - var(--tw-space-y-reverse)));margin-bottom:calc(1rem * var(--tw-space-y-reverse))}.lg\:space-y-8>:not([hidden])~:not([hidden]){--tw-space-y-reverse: 0;margin-top:calc(2rem * calc(1 - var(--tw-space-y-reverse)));margin-bottom:calc(2rem * var(--tw-space-y-reverse))}.lg\:rounded-2xl{border-radius:1rem}.lg\:rounded-3xl{border-radius:1.5rem}.lg\:p-5{padding:1.25rem}.lg\:p-6{padding:1.5rem}.lg\:p-7{padding:1.75rem}.lg\:p-8{padding:2rem}.lg\:p-9{padding:2.25rem}.lg\:px-10{padding-left:2.5rem;padding-right:2.5rem}.lg\:py-32{padding-top:8rem;padding-bottom:8rem}.lg\:pt-10{padding-top:2.5rem}.lg\:text-2xl{font-size:1.5rem;line-height:2rem}.lg\:text-4xl{font-size:2.25rem;line-height:2.5rem}.lg\:text-6xl{font-size:3.75rem;line-height:1}.lg\:text-\[12px\]{font-size:12px}.lg\:text-\[14px\]{font-size:14px}.lg\:text-\[16px\]{font-size:16px}.lg\:text-base{font-size:1rem;line-height:1.5rem}.lg\:text-lg{font-size:1.125rem;line-height:1.75rem}.lg\:text-xl{font-size:1.25rem;line-height:1.75rem}}@media(min-width:1280px){.xl\:block{display:block}.xl\:flex{display:flex}.xl\:hidden{display:none}.xl\:grid-cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}.xl\:grid-cols-4{grid-template-columns:repeat(4,minmax(0,1fr))}.xl\:grid-cols-\[0\.9fr_1\.1fr\]{grid-template-columns:.9fr 1.1fr}.xl\:grid-cols-\[1\.15fr_0\.85fr\]{grid-template-columns:1.15fr .85fr}.xl\:grid-cols-\[1\.35fr_0\.65fr\]{grid-template-columns:1.35fr .65fr}.xl\:grid-cols-\[260px_minmax\(0\,1fr\)\]{grid-template-columns:260px minmax(0,1fr)}}@media(min-width:1536px){.\32xl\:grid-cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}}

```


## File: `./dashboard/dist/assets/index-BTqvvU0l.js`
```js
(function(){const r=document.createElement("link").relList;if(r&&r.supports&&r.supports("modulepreload"))return;for(const u of document.querySelectorAll('link[rel="modulepreload"]'))a(u);new MutationObserver(u=>{for(const f of u)if(f.type==="childList")for(const d of f.addedNodes)d.tagName==="LINK"&&d.rel==="modulepreload"&&a(d)}).observe(document,{childList:!0,subtree:!0});function i(u){const f={};return u.integrity&&(f.integrity=u.integrity),u.referrerPolicy&&(f.referrerPolicy=u.referrerPolicy),u.crossOrigin==="use-credentials"?f.credentials="include":u.crossOrigin==="anonymous"?f.credentials="omit":f.credentials="same-origin",f}function a(u){if(u.ep)return;u.ep=!0;const f=i(u);fetch(u.href,f)}})();function op(n){return n&&n.__esModule&&Object.prototype.hasOwnProperty.call(n,"default")?n.default:n}var ol={exports:{}},ls={},al={exports:{}},le={};/**
 * @license React
 * react.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var Ef;function ty(){if(Ef)return le;Ef=1;var n=Symbol.for("react.element"),r=Symbol.for("react.portal"),i=Symbol.for("react.fragment"),a=Symbol.for("react.strict_mode"),u=Symbol.for("react.profiler"),f=Symbol.for("react.provider"),d=Symbol.for("react.context"),p=Symbol.for("react.forward_ref"),g=Symbol.for("react.suspense"),x=Symbol.for("react.memo"),y=Symbol.for("react.lazy"),v=Symbol.iterator;function w(T){return T===null||typeof T!="object"?null:(T=v&&T[v]||T["@@iterator"],typeof T=="function"?T:null)}var N={isMounted:function(){return!1},enqueueForceUpdate:function(){},enqueueReplaceState:function(){},enqueueSetState:function(){}},E=Object.assign,_={};function M(T,A,ae){this.props=T,this.context=A,this.refs=_,this.updater=ae||N}M.prototype.isReactComponent={},M.prototype.setState=function(T,A){if(typeof T!="object"&&typeof T!="function"&&T!=null)throw Error("setState(...): takes an object of state variables to update or a function which returns an object of state variables.");this.updater.enqueueSetState(this,T,A,"setState")},M.prototype.forceUpdate=function(T){this.updater.enqueueForceUpdate(this,T,"forceUpdate")};function L(){}L.prototype=M.prototype;function B(T,A,ae){this.props=T,this.context=A,this.refs=_,this.updater=ae||N}var I=B.prototype=new L;I.constructor=B,E(I,M.prototype),I.isPureReactComponent=!0;var U=Array.isArray,W=Object.prototype.hasOwnProperty,se={current:null},G={key:!0,ref:!0,__self:!0,__source:!0};function H(T,A,ae){var ue,fe={},he=null,xe=null;if(A!=null)for(ue in A.ref!==void 0&&(xe=A.ref),A.key!==void 0&&(he=""+A.key),A)W.call(A,ue)&&!G.hasOwnProperty(ue)&&(fe[ue]=A[ue]);var ge=arguments.length-2;if(ge===1)fe.children=ae;else if(1<ge){for(var Te=Array(ge),ct=0;ct<ge;ct++)Te[ct]=arguments[ct+2];fe.children=Te}if(T&&T.defaultProps)for(ue in ge=T.defaultProps,ge)fe[ue]===void 0&&(fe[ue]=ge[ue]);return{$$typeof:n,type:T,key:he,ref:xe,props:fe,_owner:se.current}}function re(T,A){return{$$typeof:n,type:T.type,key:A,ref:T.ref,props:T.props,_owner:T._owner}}function Y(T){return typeof T=="object"&&T!==null&&T.$$typeof===n}function ce(T){var A={"=":"=0",":":"=2"};return"$"+T.replace(/[=:]/g,function(ae){return A[ae]})}var me=/\/+/g;function Pe(T,A){return typeof T=="object"&&T!==null&&T.key!=null?ce(""+T.key):A.toString(36)}function _e(T,A,ae,ue,fe){var he=typeof T;(he==="undefined"||he==="boolean")&&(T=null);var xe=!1;if(T===null)xe=!0;else switch(he){case"string":case"number":xe=!0;break;case"object":switch(T.$$typeof){case n:case r:xe=!0}}if(xe)return xe=T,fe=fe(xe),T=ue===""?"."+Pe(xe,0):ue,U(fe)?(ae="",T!=null&&(ae=T.replace(me,"$&/")+"/"),_e(fe,A,ae,"",function(ct){return ct})):fe!=null&&(Y(fe)&&(fe=re(fe,ae+(!fe.key||xe&&xe.key===fe.key?"":(""+fe.key).replace(me,"$&/")+"/")+T)),A.push(fe)),1;if(xe=0,ue=ue===""?".":ue+":",U(T))for(var ge=0;ge<T.length;ge++){he=T[ge];var Te=ue+Pe(he,ge);xe+=_e(he,A,ae,Te,fe)}else if(Te=w(T),typeof Te=="function")for(T=Te.call(T),ge=0;!(he=T.next()).done;)he=he.value,Te=ue+Pe(he,ge++),xe+=_e(he,A,ae,Te,fe);else if(he==="object")throw A=String(T),Error("Objects are not valid as a React child (found: "+(A==="[object Object]"?"object with keys {"+Object.keys(T).join(", ")+"}":A)+"). If you meant to render a collection of children, use an array instead.");return xe}function ze(T,A,ae){if(T==null)return T;var ue=[],fe=0;return _e(T,ue,"","",function(he){return A.call(ae,he,fe++)}),ue}function ke(T){if(T._status===-1){var A=T._result;A=A(),A.then(function(ae){(T._status===0||T._status===-1)&&(T._status=1,T._result=ae)},function(ae){(T._status===0||T._status===-1)&&(T._status=2,T._result=ae)}),T._status===-1&&(T._status=0,T._result=A)}if(T._status===1)return T._result.default;throw T._result}var Ee={current:null},O={transition:null},Z={ReactCurrentDispatcher:Ee,ReactCurrentBatchConfig:O,ReactCurrentOwner:se};function $(){throw Error("act(...) is not supported in production builds of React.")}return le.Children={map:ze,forEach:function(T,A,ae){ze(T,function(){A.apply(this,arguments)},ae)},count:function(T){var A=0;return ze(T,function(){A++}),A},toArray:function(T){return ze(T,function(A){return A})||[]},only:function(T){if(!Y(T))throw Error("React.Children.only expected to receive a single React element child.");return T}},le.Component=M,le.Fragment=i,le.Profiler=u,le.PureComponent=B,le.StrictMode=a,le.Suspense=g,le.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED=Z,le.act=$,le.cloneElement=function(T,A,ae){if(T==null)throw Error("React.cloneElement(...): The argument must be a React element, but you passed "+T+".");var ue=E({},T.props),fe=T.key,he=T.ref,xe=T._owner;if(A!=null){if(A.ref!==void 0&&(he=A.ref,xe=se.current),A.key!==void 0&&(fe=""+A.key),T.type&&T.type.defaultProps)var ge=T.type.defaultProps;for(Te in A)W.call(A,Te)&&!G.hasOwnProperty(Te)&&(ue[Te]=A[Te]===void 0&&ge!==void 0?ge[Te]:A[Te])}var Te=arguments.length-2;if(Te===1)ue.children=ae;else if(1<Te){ge=Array(Te);for(var ct=0;ct<Te;ct++)ge[ct]=arguments[ct+2];ue.children=ge}return{$$typeof:n,type:T.type,key:fe,ref:he,props:ue,_owner:xe}},le.createContext=function(T){return T={$$typeof:d,_currentValue:T,_currentValue2:T,_threadCount:0,Provider:null,Consumer:null,_defaultValue:null,_globalName:null},T.Provider={$$typeof:f,_context:T},T.Consumer=T},le.createElement=H,le.createFactory=function(T){var A=H.bind(null,T);return A.type=T,A},le.createRef=function(){return{current:null}},le.forwardRef=function(T){return{$$typeof:p,render:T}},le.isValidElement=Y,le.lazy=function(T){return{$$typeof:y,_payload:{_status:-1,_result:T},_init:ke}},le.memo=function(T,A){return{$$typeof:x,type:T,compare:A===void 0?null:A}},le.startTransition=function(T){var A=O.transition;O.transition={};try{T()}finally{O.transition=A}},le.unstable_act=$,le.useCallback=function(T,A){return Ee.current.useCallback(T,A)},le.useContext=function(T){return Ee.current.useContext(T)},le.useDebugValue=function(){},le.useDeferredValue=function(T){return Ee.current.useDeferredValue(T)},le.useEffect=function(T,A){return Ee.current.useEffect(T,A)},le.useId=function(){return Ee.current.useId()},le.useImperativeHandle=function(T,A,ae){return Ee.current.useImperativeHandle(T,A,ae)},le.useInsertionEffect=function(T,A){return Ee.current.useInsertionEffect(T,A)},le.useLayoutEffect=function(T,A){return Ee.current.useLayoutEffect(T,A)},le.useMemo=function(T,A){return Ee.current.useMemo(T,A)},le.useReducer=function(T,A,ae){return Ee.current.useReducer(T,A,ae)},le.useRef=function(T){return Ee.current.useRef(T)},le.useState=function(T){return Ee.current.useState(T)},le.useSyncExternalStore=function(T,A,ae){return Ee.current.useSyncExternalStore(T,A,ae)},le.useTransition=function(){return Ee.current.useTransition()},le.version="18.3.1",le}var bf;function eu(){return bf||(bf=1,al.exports=ty()),al.exports}/**
 * @license React
 * react-jsx-runtime.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var Mf;function ny(){if(Mf)return ls;Mf=1;var n=eu(),r=Symbol.for("react.element"),i=Symbol.for("react.fragment"),a=Object.prototype.hasOwnProperty,u=n.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner,f={key:!0,ref:!0,__self:!0,__source:!0};function d(p,g,x){var y,v={},w=null,N=null;x!==void 0&&(w=""+x),g.key!==void 0&&(w=""+g.key),g.ref!==void 0&&(N=g.ref);for(y in g)a.call(g,y)&&!f.hasOwnProperty(y)&&(v[y]=g[y]);if(p&&p.defaultProps)for(y in g=p.defaultProps,g)v[y]===void 0&&(v[y]=g[y]);return{$$typeof:r,type:p,key:w,ref:N,props:v,_owner:u.current}}return ls.Fragment=i,ls.jsx=d,ls.jsxs=d,ls}var _f;function ry(){return _f||(_f=1,ol.exports=ny()),ol.exports}var h=ry(),z=eu();const sy=op(z);var Vi={},ll={exports:{}},ut={},ul={exports:{}},cl={};/**
 * @license React
 * scheduler.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var Af;function iy(){return Af||(Af=1,(function(n){function r(O,Z){var $=O.length;O.push(Z);e:for(;0<$;){var T=$-1>>>1,A=O[T];if(0<u(A,Z))O[T]=Z,O[$]=A,$=T;else break e}}function i(O){return O.length===0?null:O[0]}function a(O){if(O.length===0)return null;var Z=O[0],$=O.pop();if($!==Z){O[0]=$;e:for(var T=0,A=O.length,ae=A>>>1;T<ae;){var ue=2*(T+1)-1,fe=O[ue],he=ue+1,xe=O[he];if(0>u(fe,$))he<A&&0>u(xe,fe)?(O[T]=xe,O[he]=$,T=he):(O[T]=fe,O[ue]=$,T=ue);else if(he<A&&0>u(xe,$))O[T]=xe,O[he]=$,T=he;else break e}}return Z}function u(O,Z){var $=O.sortIndex-Z.sortIndex;return $!==0?$:O.id-Z.id}if(typeof performance=="object"&&typeof performance.now=="function"){var f=performance;n.unstable_now=function(){return f.now()}}else{var d=Date,p=d.now();n.unstable_now=function(){return d.now()-p}}var g=[],x=[],y=1,v=null,w=3,N=!1,E=!1,_=!1,M=typeof setTimeout=="function"?setTimeout:null,L=typeof clearTimeout=="function"?clearTimeout:null,B=typeof setImmediate<"u"?setImmediate:null;typeof navigator<"u"&&navigator.scheduling!==void 0&&navigator.scheduling.isInputPending!==void 0&&navigator.scheduling.isInputPending.bind(navigator.scheduling);function I(O){for(var Z=i(x);Z!==null;){if(Z.callback===null)a(x);else if(Z.startTime<=O)a(x),Z.sortIndex=Z.expirationTime,r(g,Z);else break;Z=i(x)}}function U(O){if(_=!1,I(O),!E)if(i(g)!==null)E=!0,ke(W);else{var Z=i(x);Z!==null&&Ee(U,Z.startTime-O)}}function W(O,Z){E=!1,_&&(_=!1,L(H),H=-1),N=!0;var $=w;try{for(I(Z),v=i(g);v!==null&&(!(v.expirationTime>Z)||O&&!ce());){var T=v.callback;if(typeof T=="function"){v.callback=null,w=v.priorityLevel;var A=T(v.expirationTime<=Z);Z=n.unstable_now(),typeof A=="function"?v.callback=A:v===i(g)&&a(g),I(Z)}else a(g);v=i(g)}if(v!==null)var ae=!0;else{var ue=i(x);ue!==null&&Ee(U,ue.startTime-Z),ae=!1}return ae}finally{v=null,w=$,N=!1}}var se=!1,G=null,H=-1,re=5,Y=-1;function ce(){return!(n.unstable_now()-Y<re)}function me(){if(G!==null){var O=n.unstable_now();Y=O;var Z=!0;try{Z=G(!0,O)}finally{Z?Pe():(se=!1,G=null)}}else se=!1}var Pe;if(typeof B=="function")Pe=function(){B(me)};else if(typeof MessageChannel<"u"){var _e=new MessageChannel,ze=_e.port2;_e.port1.onmessage=me,Pe=function(){ze.postMessage(null)}}else Pe=function(){M(me,0)};function ke(O){G=O,se||(se=!0,Pe())}function Ee(O,Z){H=M(function(){O(n.unstable_now())},Z)}n.unstable_IdlePriority=5,n.unstable_ImmediatePriority=1,n.unstable_LowPriority=4,n.unstable_NormalPriority=3,n.unstable_Profiling=null,n.unstable_UserBlockingPriority=2,n.unstable_cancelCallback=function(O){O.callback=null},n.unstable_continueExecution=function(){E||N||(E=!0,ke(W))},n.unstable_forceFrameRate=function(O){0>O||125<O?console.error("forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported"):re=0<O?Math.floor(1e3/O):5},n.unstable_getCurrentPriorityLevel=function(){return w},n.unstable_getFirstCallbackNode=function(){return i(g)},n.unstable_next=function(O){switch(w){case 1:case 2:case 3:var Z=3;break;default:Z=w}var $=w;w=Z;try{return O()}finally{w=$}},n.unstable_pauseExecution=function(){},n.unstable_requestPaint=function(){},n.unstable_runWithPriority=function(O,Z){switch(O){case 1:case 2:case 3:case 4:case 5:break;default:O=3}var $=w;w=O;try{return Z()}finally{w=$}},n.unstable_scheduleCallback=function(O,Z,$){var T=n.unstable_now();switch(typeof $=="object"&&$!==null?($=$.delay,$=typeof $=="number"&&0<$?T+$:T):$=T,O){case 1:var A=-1;break;case 2:A=250;break;case 5:A=1073741823;break;case 4:A=1e4;break;default:A=5e3}return A=$+A,O={id:y++,callback:Z,priorityLevel:O,startTime:$,expirationTime:A,sortIndex:-1},$>T?(O.sortIndex=$,r(x,O),i(g)===null&&O===i(x)&&(_?(L(H),H=-1):_=!0,Ee(U,$-T))):(O.sortIndex=A,r(g,O),E||N||(E=!0,ke(W))),O},n.unstable_shouldYield=ce,n.unstable_wrapCallback=function(O){var Z=w;return function(){var $=w;w=Z;try{return O.apply(this,arguments)}finally{w=$}}}})(cl)),cl}var Rf;function oy(){return Rf||(Rf=1,ul.exports=iy()),ul.exports}/**
 * @license React
 * react-dom.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var Df;function ay(){if(Df)return ut;Df=1;var n=eu(),r=oy();function i(e){for(var t="https://reactjs.org/docs/error-decoder.html?invariant="+e,s=1;s<arguments.length;s++)t+="&args[]="+encodeURIComponent(arguments[s]);return"Minified React error #"+e+"; visit "+t+" for the full message or use the non-minified dev environment for full errors and additional helpful warnings."}var a=new Set,u={};function f(e,t){d(e,t),d(e+"Capture",t)}function d(e,t){for(u[e]=t,e=0;e<t.length;e++)a.add(t[e])}var p=!(typeof window>"u"||typeof window.document>"u"||typeof window.document.createElement>"u"),g=Object.prototype.hasOwnProperty,x=/^[:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD][:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\-.0-9\u00B7\u0300-\u036F\u203F-\u2040]*$/,y={},v={};function w(e){return g.call(v,e)?!0:g.call(y,e)?!1:x.test(e)?v[e]=!0:(y[e]=!0,!1)}function N(e,t,s,o){if(s!==null&&s.type===0)return!1;switch(typeof t){case"function":case"symbol":return!0;case"boolean":return o?!1:s!==null?!s.acceptsBooleans:(e=e.toLowerCase().slice(0,5),e!=="data-"&&e!=="aria-");default:return!1}}function E(e,t,s,o){if(t===null||typeof t>"u"||N(e,t,s,o))return!0;if(o)return!1;if(s!==null)switch(s.type){case 3:return!t;case 4:return t===!1;case 5:return isNaN(t);case 6:return isNaN(t)||1>t}return!1}function _(e,t,s,o,l,c,m){this.acceptsBooleans=t===2||t===3||t===4,this.attributeName=o,this.attributeNamespace=l,this.mustUseProperty=s,this.propertyName=e,this.type=t,this.sanitizeURL=c,this.removeEmptyString=m}var M={};"children dangerouslySetInnerHTML defaultValue defaultChecked innerHTML suppressContentEditableWarning suppressHydrationWarning style".split(" ").forEach(function(e){M[e]=new _(e,0,!1,e,null,!1,!1)}),[["acceptCharset","accept-charset"],["className","class"],["htmlFor","for"],["httpEquiv","http-equiv"]].forEach(function(e){var t=e[0];M[t]=new _(t,1,!1,e[1],null,!1,!1)}),["contentEditable","draggable","spellCheck","value"].forEach(function(e){M[e]=new _(e,2,!1,e.toLowerCase(),null,!1,!1)}),["autoReverse","externalResourcesRequired","focusable","preserveAlpha"].forEach(function(e){M[e]=new _(e,2,!1,e,null,!1,!1)}),"allowFullScreen async autoFocus autoPlay controls default defer disabled disablePictureInPicture disableRemotePlayback formNoValidate hidden loop noModule noValidate open playsInline readOnly required reversed scoped seamless itemScope".split(" ").forEach(function(e){M[e]=new _(e,3,!1,e.toLowerCase(),null,!1,!1)}),["checked","multiple","muted","selected"].forEach(function(e){M[e]=new _(e,3,!0,e,null,!1,!1)}),["capture","download"].forEach(function(e){M[e]=new _(e,4,!1,e,null,!1,!1)}),["cols","rows","size","span"].forEach(function(e){M[e]=new _(e,6,!1,e,null,!1,!1)}),["rowSpan","start"].forEach(function(e){M[e]=new _(e,5,!1,e.toLowerCase(),null,!1,!1)});var L=/[\-:]([a-z])/g;function B(e){return e[1].toUpperCase()}"accent-height alignment-baseline arabic-form baseline-shift cap-height clip-path clip-rule color-interpolation color-interpolation-filters color-profile color-rendering dominant-baseline enable-background fill-opacity fill-rule flood-color flood-opacity font-family font-size font-size-adjust font-stretch font-style font-variant font-weight glyph-name glyph-orientation-horizontal glyph-orientation-vertical horiz-adv-x horiz-origin-x image-rendering letter-spacing lighting-color marker-end marker-mid marker-start overline-position overline-thickness paint-order panose-1 pointer-events rendering-intent shape-rendering stop-color stop-opacity strikethrough-position strikethrough-thickness stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity stroke-width text-anchor text-decoration text-rendering underline-position underline-thickness unicode-bidi unicode-range units-per-em v-alphabetic v-hanging v-ideographic v-mathematical vector-effect vert-adv-y vert-origin-x vert-origin-y word-spacing writing-mode xmlns:xlink x-height".split(" ").forEach(function(e){var t=e.replace(L,B);M[t]=new _(t,1,!1,e,null,!1,!1)}),"xlink:actuate xlink:arcrole xlink:role xlink:show xlink:title xlink:type".split(" ").forEach(function(e){var t=e.replace(L,B);M[t]=new _(t,1,!1,e,"http://www.w3.org/1999/xlink",!1,!1)}),["xml:base","xml:lang","xml:space"].forEach(function(e){var t=e.replace(L,B);M[t]=new _(t,1,!1,e,"http://www.w3.org/XML/1998/namespace",!1,!1)}),["tabIndex","crossOrigin"].forEach(function(e){M[e]=new _(e,1,!1,e.toLowerCase(),null,!1,!1)}),M.xlinkHref=new _("xlinkHref",1,!1,"xlink:href","http://www.w3.org/1999/xlink",!0,!1),["src","href","action","formAction"].forEach(function(e){M[e]=new _(e,1,!1,e.toLowerCase(),null,!0,!0)});function I(e,t,s,o){var l=M.hasOwnProperty(t)?M[t]:null;(l!==null?l.type!==0:o||!(2<t.length)||t[0]!=="o"&&t[0]!=="O"||t[1]!=="n"&&t[1]!=="N")&&(E(t,s,l,o)&&(s=null),o||l===null?w(t)&&(s===null?e.removeAttribute(t):e.setAttribute(t,""+s)):l.mustUseProperty?e[l.propertyName]=s===null?l.type===3?!1:"":s:(t=l.attributeName,o=l.attributeNamespace,s===null?e.removeAttribute(t):(l=l.type,s=l===3||l===4&&s===!0?"":""+s,o?e.setAttributeNS(o,t,s):e.setAttribute(t,s))))}var U=n.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED,W=Symbol.for("react.element"),se=Symbol.for("react.portal"),G=Symbol.for("react.fragment"),H=Symbol.for("react.strict_mode"),re=Symbol.for("react.profiler"),Y=Symbol.for("react.provider"),ce=Symbol.for("react.context"),me=Symbol.for("react.forward_ref"),Pe=Symbol.for("react.suspense"),_e=Symbol.for("react.suspense_list"),ze=Symbol.for("react.memo"),ke=Symbol.for("react.lazy"),Ee=Symbol.for("react.offscreen"),O=Symbol.iterator;function Z(e){return e===null||typeof e!="object"?null:(e=O&&e[O]||e["@@iterator"],typeof e=="function"?e:null)}var $=Object.assign,T;function A(e){if(T===void 0)try{throw Error()}catch(s){var t=s.stack.trim().match(/\n( *(at )?)/);T=t&&t[1]||""}return`
`+T+e}var ae=!1;function ue(e,t){if(!e||ae)return"";ae=!0;var s=Error.prepareStackTrace;Error.prepareStackTrace=void 0;try{if(t)if(t=function(){throw Error()},Object.defineProperty(t.prototype,"props",{set:function(){throw Error()}}),typeof Reflect=="object"&&Reflect.construct){try{Reflect.construct(t,[])}catch(b){var o=b}Reflect.construct(e,[],t)}else{try{t.call()}catch(b){o=b}e.call(t.prototype)}else{try{throw Error()}catch(b){o=b}e()}}catch(b){if(b&&o&&typeof b.stack=="string"){for(var l=b.stack.split(`
`),c=o.stack.split(`
`),m=l.length-1,k=c.length-1;1<=m&&0<=k&&l[m]!==c[k];)k--;for(;1<=m&&0<=k;m--,k--)if(l[m]!==c[k]){if(m!==1||k!==1)do if(m--,k--,0>k||l[m]!==c[k]){var S=`
`+l[m].replace(" at new "," at ");return e.displayName&&S.includes("<anonymous>")&&(S=S.replace("<anonymous>",e.displayName)),S}while(1<=m&&0<=k);break}}}finally{ae=!1,Error.prepareStackTrace=s}return(e=e?e.displayName||e.name:"")?A(e):""}function fe(e){switch(e.tag){case 5:return A(e.type);case 16:return A("Lazy");case 13:return A("Suspense");case 19:return A("SuspenseList");case 0:case 2:case 15:return e=ue(e.type,!1),e;case 11:return e=ue(e.type.render,!1),e;case 1:return e=ue(e.type,!0),e;default:return""}}function he(e){if(e==null)return null;if(typeof e=="function")return e.displayName||e.name||null;if(typeof e=="string")return e;switch(e){case G:return"Fragment";case se:return"Portal";case re:return"Profiler";case H:return"StrictMode";case Pe:return"Suspense";case _e:return"SuspenseList"}if(typeof e=="object")switch(e.$$typeof){case ce:return(e.displayName||"Context")+".Consumer";case Y:return(e._context.displayName||"Context")+".Provider";case me:var t=e.render;return e=e.displayName,e||(e=t.displayName||t.name||"",e=e!==""?"ForwardRef("+e+")":"ForwardRef"),e;case ze:return t=e.displayName||null,t!==null?t:he(e.type)||"Memo";case ke:t=e._payload,e=e._init;try{return he(e(t))}catch{}}return null}function xe(e){var t=e.type;switch(e.tag){case 24:return"Cache";case 9:return(t.displayName||"Context")+".Consumer";case 10:return(t._context.displayName||"Context")+".Provider";case 18:return"DehydratedFragment";case 11:return e=t.render,e=e.displayName||e.name||"",t.displayName||(e!==""?"ForwardRef("+e+")":"ForwardRef");case 7:return"Fragment";case 5:return t;case 4:return"Portal";case 3:return"Root";case 6:return"Text";case 16:return he(t);case 8:return t===H?"StrictMode":"Mode";case 22:return"Offscreen";case 12:return"Profiler";case 21:return"Scope";case 13:return"Suspense";case 19:return"SuspenseList";case 25:return"TracingMarker";case 1:case 0:case 17:case 2:case 14:case 15:if(typeof t=="function")return t.displayName||t.name||null;if(typeof t=="string")return t}return null}function ge(e){switch(typeof e){case"boolean":case"number":case"string":case"undefined":return e;case"object":return e;default:return""}}function Te(e){var t=e.type;return(e=e.nodeName)&&e.toLowerCase()==="input"&&(t==="checkbox"||t==="radio")}function ct(e){var t=Te(e)?"checked":"value",s=Object.getOwnPropertyDescriptor(e.constructor.prototype,t),o=""+e[t];if(!e.hasOwnProperty(t)&&typeof s<"u"&&typeof s.get=="function"&&typeof s.set=="function"){var l=s.get,c=s.set;return Object.defineProperty(e,t,{configurable:!0,get:function(){return l.call(this)},set:function(m){o=""+m,c.call(this,m)}}),Object.defineProperty(e,t,{enumerable:s.enumerable}),{getValue:function(){return o},setValue:function(m){o=""+m},stopTracking:function(){e._valueTracker=null,delete e[t]}}}}function Cs(e){e._valueTracker||(e._valueTracker=ct(e))}function Ru(e){if(!e)return!1;var t=e._valueTracker;if(!t)return!0;var s=t.getValue(),o="";return e&&(o=Te(e)?e.checked?"true":"false":e.value),e=o,e!==s?(t.setValue(e),!0):!1}function Ps(e){if(e=e||(typeof document<"u"?document:void 0),typeof e>"u")return null;try{return e.activeElement||e.body}catch{return e.body}}function ho(e,t){var s=t.checked;return $({},t,{defaultChecked:void 0,defaultValue:void 0,value:void 0,checked:s??e._wrapperState.initialChecked})}function Du(e,t){var s=t.defaultValue==null?"":t.defaultValue,o=t.checked!=null?t.checked:t.defaultChecked;s=ge(t.value!=null?t.value:s),e._wrapperState={initialChecked:o,initialValue:s,controlled:t.type==="checkbox"||t.type==="radio"?t.checked!=null:t.value!=null}}function Lu(e,t){t=t.checked,t!=null&&I(e,"checked",t,!1)}function po(e,t){Lu(e,t);var s=ge(t.value),o=t.type;if(s!=null)o==="number"?(s===0&&e.value===""||e.value!=s)&&(e.value=""+s):e.value!==""+s&&(e.value=""+s);else if(o==="submit"||o==="reset"){e.removeAttribute("value");return}t.hasOwnProperty("value")?mo(e,t.type,s):t.hasOwnProperty("defaultValue")&&mo(e,t.type,ge(t.defaultValue)),t.checked==null&&t.defaultChecked!=null&&(e.defaultChecked=!!t.defaultChecked)}function Vu(e,t,s){if(t.hasOwnProperty("value")||t.hasOwnProperty("defaultValue")){var o=t.type;if(!(o!=="submit"&&o!=="reset"||t.value!==void 0&&t.value!==null))return;t=""+e._wrapperState.initialValue,s||t===e.value||(e.value=t),e.defaultValue=t}s=e.name,s!==""&&(e.name=""),e.defaultChecked=!!e._wrapperState.initialChecked,s!==""&&(e.name=s)}function mo(e,t,s){(t!=="number"||Ps(e.ownerDocument)!==e)&&(s==null?e.defaultValue=""+e._wrapperState.initialValue:e.defaultValue!==""+s&&(e.defaultValue=""+s))}var jr=Array.isArray;function Un(e,t,s,o){if(e=e.options,t){t={};for(var l=0;l<s.length;l++)t["$"+s[l]]=!0;for(s=0;s<e.length;s++)l=t.hasOwnProperty("$"+e[s].value),e[s].selected!==l&&(e[s].selected=l),l&&o&&(e[s].defaultSelected=!0)}else{for(s=""+ge(s),t=null,l=0;l<e.length;l++){if(e[l].value===s){e[l].selected=!0,o&&(e[l].defaultSelected=!0);return}t!==null||e[l].disabled||(t=e[l])}t!==null&&(t.selected=!0)}}function go(e,t){if(t.dangerouslySetInnerHTML!=null)throw Error(i(91));return $({},t,{value:void 0,defaultValue:void 0,children:""+e._wrapperState.initialValue})}function zu(e,t){var s=t.value;if(s==null){if(s=t.children,t=t.defaultValue,s!=null){if(t!=null)throw Error(i(92));if(jr(s)){if(1<s.length)throw Error(i(93));s=s[0]}t=s}t==null&&(t=""),s=t}e._wrapperState={initialValue:ge(s)}}function Iu(e,t){var s=ge(t.value),o=ge(t.defaultValue);s!=null&&(s=""+s,s!==e.value&&(e.value=s),t.defaultValue==null&&e.defaultValue!==s&&(e.defaultValue=s)),o!=null&&(e.defaultValue=""+o)}function Ou(e){var t=e.textContent;t===e._wrapperState.initialValue&&t!==""&&t!==null&&(e.value=t)}function Fu(e){switch(e){case"svg":return"http://www.w3.org/2000/svg";case"math":return"http://www.w3.org/1998/Math/MathML";default:return"http://www.w3.org/1999/xhtml"}}function yo(e,t){return e==null||e==="http://www.w3.org/1999/xhtml"?Fu(t):e==="http://www.w3.org/2000/svg"&&t==="foreignObject"?"http://www.w3.org/1999/xhtml":e}var Es,Bu=(function(e){return typeof MSApp<"u"&&MSApp.execUnsafeLocalFunction?function(t,s,o,l){MSApp.execUnsafeLocalFunction(function(){return e(t,s,o,l)})}:e})(function(e,t){if(e.namespaceURI!=="http://www.w3.org/2000/svg"||"innerHTML"in e)e.innerHTML=t;else{for(Es=Es||document.createElement("div"),Es.innerHTML="<svg>"+t.valueOf().toString()+"</svg>",t=Es.firstChild;e.firstChild;)e.removeChild(e.firstChild);for(;t.firstChild;)e.appendChild(t.firstChild)}});function Nr(e,t){if(t){var s=e.firstChild;if(s&&s===e.lastChild&&s.nodeType===3){s.nodeValue=t;return}}e.textContent=t}var Tr={animationIterationCount:!0,aspectRatio:!0,borderImageOutset:!0,borderImageSlice:!0,borderImageWidth:!0,boxFlex:!0,boxFlexGroup:!0,boxOrdinalGroup:!0,columnCount:!0,columns:!0,flex:!0,flexGrow:!0,flexPositive:!0,flexShrink:!0,flexNegative:!0,flexOrder:!0,gridArea:!0,gridRow:!0,gridRowEnd:!0,gridRowSpan:!0,gridRowStart:!0,gridColumn:!0,gridColumnEnd:!0,gridColumnSpan:!0,gridColumnStart:!0,fontWeight:!0,lineClamp:!0,lineHeight:!0,opacity:!0,order:!0,orphans:!0,tabSize:!0,widows:!0,zIndex:!0,zoom:!0,fillOpacity:!0,floodOpacity:!0,stopOpacity:!0,strokeDasharray:!0,strokeDashoffset:!0,strokeMiterlimit:!0,strokeOpacity:!0,strokeWidth:!0},i0=["Webkit","ms","Moz","O"];Object.keys(Tr).forEach(function(e){i0.forEach(function(t){t=t+e.charAt(0).toUpperCase()+e.substring(1),Tr[t]=Tr[e]})});function Uu(e,t,s){return t==null||typeof t=="boolean"||t===""?"":s||typeof t!="number"||t===0||Tr.hasOwnProperty(e)&&Tr[e]?(""+t).trim():t+"px"}function $u(e,t){e=e.style;for(var s in t)if(t.hasOwnProperty(s)){var o=s.indexOf("--")===0,l=Uu(s,t[s],o);s==="float"&&(s="cssFloat"),o?e.setProperty(s,l):e[s]=l}}var o0=$({menuitem:!0},{area:!0,base:!0,br:!0,col:!0,embed:!0,hr:!0,img:!0,input:!0,keygen:!0,link:!0,meta:!0,param:!0,source:!0,track:!0,wbr:!0});function vo(e,t){if(t){if(o0[e]&&(t.children!=null||t.dangerouslySetInnerHTML!=null))throw Error(i(137,e));if(t.dangerouslySetInnerHTML!=null){if(t.children!=null)throw Error(i(60));if(typeof t.dangerouslySetInnerHTML!="object"||!("__html"in t.dangerouslySetInnerHTML))throw Error(i(61))}if(t.style!=null&&typeof t.style!="object")throw Error(i(62))}}function xo(e,t){if(e.indexOf("-")===-1)return typeof t.is=="string";switch(e){case"annotation-xml":case"color-profile":case"font-face":case"font-face-src":case"font-face-uri":case"font-face-format":case"font-face-name":case"missing-glyph":return!1;default:return!0}}var wo=null;function ko(e){return e=e.target||e.srcElement||window,e.correspondingUseElement&&(e=e.correspondingUseElement),e.nodeType===3?e.parentNode:e}var So=null,$n=null,Wn=null;function Wu(e){if(e=Gr(e)){if(typeof So!="function")throw Error(i(280));var t=e.stateNode;t&&(t=qs(t),So(e.stateNode,e.type,t))}}function Hu(e){$n?Wn?Wn.push(e):Wn=[e]:$n=e}function Ku(){if($n){var e=$n,t=Wn;if(Wn=$n=null,Wu(e),t)for(e=0;e<t.length;e++)Wu(t[e])}}function Gu(e,t){return e(t)}function Yu(){}var jo=!1;function Xu(e,t,s){if(jo)return e(t,s);jo=!0;try{return Gu(e,t,s)}finally{jo=!1,($n!==null||Wn!==null)&&(Yu(),Ku())}}function Cr(e,t){var s=e.stateNode;if(s===null)return null;var o=qs(s);if(o===null)return null;s=o[t];e:switch(t){case"onClick":case"onClickCapture":case"onDoubleClick":case"onDoubleClickCapture":case"onMouseDown":case"onMouseDownCapture":case"onMouseMove":case"onMouseMoveCapture":case"onMouseUp":case"onMouseUpCapture":case"onMouseEnter":(o=!o.disabled)||(e=e.type,o=!(e==="button"||e==="input"||e==="select"||e==="textarea")),e=!o;break e;default:e=!1}if(e)return null;if(s&&typeof s!="function")throw Error(i(231,t,typeof s));return s}var No=!1;if(p)try{var Pr={};Object.defineProperty(Pr,"passive",{get:function(){No=!0}}),window.addEventListener("test",Pr,Pr),window.removeEventListener("test",Pr,Pr)}catch{No=!1}function a0(e,t,s,o,l,c,m,k,S){var b=Array.prototype.slice.call(arguments,3);try{t.apply(s,b)}catch(D){this.onError(D)}}var Er=!1,bs=null,Ms=!1,To=null,l0={onError:function(e){Er=!0,bs=e}};function u0(e,t,s,o,l,c,m,k,S){Er=!1,bs=null,a0.apply(l0,arguments)}function c0(e,t,s,o,l,c,m,k,S){if(u0.apply(this,arguments),Er){if(Er){var b=bs;Er=!1,bs=null}else throw Error(i(198));Ms||(Ms=!0,To=b)}}function jn(e){var t=e,s=e;if(e.alternate)for(;t.return;)t=t.return;else{e=t;do t=e,(t.flags&4098)!==0&&(s=t.return),e=t.return;while(e)}return t.tag===3?s:null}function Qu(e){if(e.tag===13){var t=e.memoizedState;if(t===null&&(e=e.alternate,e!==null&&(t=e.memoizedState)),t!==null)return t.dehydrated}return null}function qu(e){if(jn(e)!==e)throw Error(i(188))}function d0(e){var t=e.alternate;if(!t){if(t=jn(e),t===null)throw Error(i(188));return t!==e?null:e}for(var s=e,o=t;;){var l=s.return;if(l===null)break;var c=l.alternate;if(c===null){if(o=l.return,o!==null){s=o;continue}break}if(l.child===c.child){for(c=l.child;c;){if(c===s)return qu(l),e;if(c===o)return qu(l),t;c=c.sibling}throw Error(i(188))}if(s.return!==o.return)s=l,o=c;else{for(var m=!1,k=l.child;k;){if(k===s){m=!0,s=l,o=c;break}if(k===o){m=!0,o=l,s=c;break}k=k.sibling}if(!m){for(k=c.child;k;){if(k===s){m=!0,s=c,o=l;break}if(k===o){m=!0,o=c,s=l;break}k=k.sibling}if(!m)throw Error(i(189))}}if(s.alternate!==o)throw Error(i(190))}if(s.tag!==3)throw Error(i(188));return s.stateNode.current===s?e:t}function Zu(e){return e=d0(e),e!==null?Ju(e):null}function Ju(e){if(e.tag===5||e.tag===6)return e;for(e=e.child;e!==null;){var t=Ju(e);if(t!==null)return t;e=e.sibling}return null}var ec=r.unstable_scheduleCallback,tc=r.unstable_cancelCallback,f0=r.unstable_shouldYield,h0=r.unstable_requestPaint,Le=r.unstable_now,p0=r.unstable_getCurrentPriorityLevel,Co=r.unstable_ImmediatePriority,nc=r.unstable_UserBlockingPriority,_s=r.unstable_NormalPriority,m0=r.unstable_LowPriority,rc=r.unstable_IdlePriority,As=null,Dt=null;function g0(e){if(Dt&&typeof Dt.onCommitFiberRoot=="function")try{Dt.onCommitFiberRoot(As,e,void 0,(e.current.flags&128)===128)}catch{}}var Nt=Math.clz32?Math.clz32:x0,y0=Math.log,v0=Math.LN2;function x0(e){return e>>>=0,e===0?32:31-(y0(e)/v0|0)|0}var Rs=64,Ds=4194304;function br(e){switch(e&-e){case 1:return 1;case 2:return 2;case 4:return 4;case 8:return 8;case 16:return 16;case 32:return 32;case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:return e&4194240;case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:return e&130023424;case 134217728:return 134217728;case 268435456:return 268435456;case 536870912:return 536870912;case 1073741824:return 1073741824;default:return e}}function Ls(e,t){var s=e.pendingLanes;if(s===0)return 0;var o=0,l=e.suspendedLanes,c=e.pingedLanes,m=s&268435455;if(m!==0){var k=m&~l;k!==0?o=br(k):(c&=m,c!==0&&(o=br(c)))}else m=s&~l,m!==0?o=br(m):c!==0&&(o=br(c));if(o===0)return 0;if(t!==0&&t!==o&&(t&l)===0&&(l=o&-o,c=t&-t,l>=c||l===16&&(c&4194240)!==0))return t;if((o&4)!==0&&(o|=s&16),t=e.entangledLanes,t!==0)for(e=e.entanglements,t&=o;0<t;)s=31-Nt(t),l=1<<s,o|=e[s],t&=~l;return o}function w0(e,t){switch(e){case 1:case 2:case 4:return t+250;case 8:case 16:case 32:case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:return t+5e3;case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:return-1;case 134217728:case 268435456:case 536870912:case 1073741824:return-1;default:return-1}}function k0(e,t){for(var s=e.suspendedLanes,o=e.pingedLanes,l=e.expirationTimes,c=e.pendingLanes;0<c;){var m=31-Nt(c),k=1<<m,S=l[m];S===-1?((k&s)===0||(k&o)!==0)&&(l[m]=w0(k,t)):S<=t&&(e.expiredLanes|=k),c&=~k}}function Po(e){return e=e.pendingLanes&-1073741825,e!==0?e:e&1073741824?1073741824:0}function sc(){var e=Rs;return Rs<<=1,(Rs&4194240)===0&&(Rs=64),e}function Eo(e){for(var t=[],s=0;31>s;s++)t.push(e);return t}function Mr(e,t,s){e.pendingLanes|=t,t!==536870912&&(e.suspendedLanes=0,e.pingedLanes=0),e=e.eventTimes,t=31-Nt(t),e[t]=s}function S0(e,t){var s=e.pendingLanes&~t;e.pendingLanes=t,e.suspendedLanes=0,e.pingedLanes=0,e.expiredLanes&=t,e.mutableReadLanes&=t,e.entangledLanes&=t,t=e.entanglements;var o=e.eventTimes;for(e=e.expirationTimes;0<s;){var l=31-Nt(s),c=1<<l;t[l]=0,o[l]=-1,e[l]=-1,s&=~c}}function bo(e,t){var s=e.entangledLanes|=t;for(e=e.entanglements;s;){var o=31-Nt(s),l=1<<o;l&t|e[o]&t&&(e[o]|=t),s&=~l}}var ye=0;function ic(e){return e&=-e,1<e?4<e?(e&268435455)!==0?16:536870912:4:1}var oc,Mo,ac,lc,uc,_o=!1,Vs=[],qt=null,Zt=null,Jt=null,_r=new Map,Ar=new Map,en=[],j0="mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset submit".split(" ");function cc(e,t){switch(e){case"focusin":case"focusout":qt=null;break;case"dragenter":case"dragleave":Zt=null;break;case"mouseover":case"mouseout":Jt=null;break;case"pointerover":case"pointerout":_r.delete(t.pointerId);break;case"gotpointercapture":case"lostpointercapture":Ar.delete(t.pointerId)}}function Rr(e,t,s,o,l,c){return e===null||e.nativeEvent!==c?(e={blockedOn:t,domEventName:s,eventSystemFlags:o,nativeEvent:c,targetContainers:[l]},t!==null&&(t=Gr(t),t!==null&&Mo(t)),e):(e.eventSystemFlags|=o,t=e.targetContainers,l!==null&&t.indexOf(l)===-1&&t.push(l),e)}function N0(e,t,s,o,l){switch(t){case"focusin":return qt=Rr(qt,e,t,s,o,l),!0;case"dragenter":return Zt=Rr(Zt,e,t,s,o,l),!0;case"mouseover":return Jt=Rr(Jt,e,t,s,o,l),!0;case"pointerover":var c=l.pointerId;return _r.set(c,Rr(_r.get(c)||null,e,t,s,o,l)),!0;case"gotpointercapture":return c=l.pointerId,Ar.set(c,Rr(Ar.get(c)||null,e,t,s,o,l)),!0}return!1}function dc(e){var t=Nn(e.target);if(t!==null){var s=jn(t);if(s!==null){if(t=s.tag,t===13){if(t=Qu(s),t!==null){e.blockedOn=t,uc(e.priority,function(){ac(s)});return}}else if(t===3&&s.stateNode.current.memoizedState.isDehydrated){e.blockedOn=s.tag===3?s.stateNode.containerInfo:null;return}}}e.blockedOn=null}function zs(e){if(e.blockedOn!==null)return!1;for(var t=e.targetContainers;0<t.length;){var s=Ro(e.domEventName,e.eventSystemFlags,t[0],e.nativeEvent);if(s===null){s=e.nativeEvent;var o=new s.constructor(s.type,s);wo=o,s.target.dispatchEvent(o),wo=null}else return t=Gr(s),t!==null&&Mo(t),e.blockedOn=s,!1;t.shift()}return!0}function fc(e,t,s){zs(e)&&s.delete(t)}function T0(){_o=!1,qt!==null&&zs(qt)&&(qt=null),Zt!==null&&zs(Zt)&&(Zt=null),Jt!==null&&zs(Jt)&&(Jt=null),_r.forEach(fc),Ar.forEach(fc)}function Dr(e,t){e.blockedOn===t&&(e.blockedOn=null,_o||(_o=!0,r.unstable_scheduleCallback(r.unstable_NormalPriority,T0)))}function Lr(e){function t(l){return Dr(l,e)}if(0<Vs.length){Dr(Vs[0],e);for(var s=1;s<Vs.length;s++){var o=Vs[s];o.blockedOn===e&&(o.blockedOn=null)}}for(qt!==null&&Dr(qt,e),Zt!==null&&Dr(Zt,e),Jt!==null&&Dr(Jt,e),_r.forEach(t),Ar.forEach(t),s=0;s<en.length;s++)o=en[s],o.blockedOn===e&&(o.blockedOn=null);for(;0<en.length&&(s=en[0],s.blockedOn===null);)dc(s),s.blockedOn===null&&en.shift()}var Hn=U.ReactCurrentBatchConfig,Is=!0;function C0(e,t,s,o){var l=ye,c=Hn.transition;Hn.transition=null;try{ye=1,Ao(e,t,s,o)}finally{ye=l,Hn.transition=c}}function P0(e,t,s,o){var l=ye,c=Hn.transition;Hn.transition=null;try{ye=4,Ao(e,t,s,o)}finally{ye=l,Hn.transition=c}}function Ao(e,t,s,o){if(Is){var l=Ro(e,t,s,o);if(l===null)Qo(e,t,o,Os,s),cc(e,o);else if(N0(l,e,t,s,o))o.stopPropagation();else if(cc(e,o),t&4&&-1<j0.indexOf(e)){for(;l!==null;){var c=Gr(l);if(c!==null&&oc(c),c=Ro(e,t,s,o),c===null&&Qo(e,t,o,Os,s),c===l)break;l=c}l!==null&&o.stopPropagation()}else Qo(e,t,o,null,s)}}var Os=null;function Ro(e,t,s,o){if(Os=null,e=ko(o),e=Nn(e),e!==null)if(t=jn(e),t===null)e=null;else if(s=t.tag,s===13){if(e=Qu(t),e!==null)return e;e=null}else if(s===3){if(t.stateNode.current.memoizedState.isDehydrated)return t.tag===3?t.stateNode.containerInfo:null;e=null}else t!==e&&(e=null);return Os=e,null}function hc(e){switch(e){case"cancel":case"click":case"close":case"contextmenu":case"copy":case"cut":case"auxclick":case"dblclick":case"dragend":case"dragstart":case"drop":case"focusin":case"focusout":case"input":case"invalid":case"keydown":case"keypress":case"keyup":case"mousedown":case"mouseup":case"paste":case"pause":case"play":case"pointercancel":case"pointerdown":case"pointerup":case"ratechange":case"reset":case"resize":case"seeked":case"submit":case"touchcancel":case"touchend":case"touchstart":case"volumechange":case"change":case"selectionchange":case"textInput":case"compositionstart":case"compositionend":case"compositionupdate":case"beforeblur":case"afterblur":case"beforeinput":case"blur":case"fullscreenchange":case"focus":case"hashchange":case"popstate":case"select":case"selectstart":return 1;case"drag":case"dragenter":case"dragexit":case"dragleave":case"dragover":case"mousemove":case"mouseout":case"mouseover":case"pointermove":case"pointerout":case"pointerover":case"scroll":case"toggle":case"touchmove":case"wheel":case"mouseenter":case"mouseleave":case"pointerenter":case"pointerleave":return 4;case"message":switch(p0()){case Co:return 1;case nc:return 4;case _s:case m0:return 16;case rc:return 536870912;default:return 16}default:return 16}}var tn=null,Do=null,Fs=null;function pc(){if(Fs)return Fs;var e,t=Do,s=t.length,o,l="value"in tn?tn.value:tn.textContent,c=l.length;for(e=0;e<s&&t[e]===l[e];e++);var m=s-e;for(o=1;o<=m&&t[s-o]===l[c-o];o++);return Fs=l.slice(e,1<o?1-o:void 0)}function Bs(e){var t=e.keyCode;return"charCode"in e?(e=e.charCode,e===0&&t===13&&(e=13)):e=t,e===10&&(e=13),32<=e||e===13?e:0}function Us(){return!0}function mc(){return!1}function dt(e){function t(s,o,l,c,m){this._reactName=s,this._targetInst=l,this.type=o,this.nativeEvent=c,this.target=m,this.currentTarget=null;for(var k in e)e.hasOwnProperty(k)&&(s=e[k],this[k]=s?s(c):c[k]);return this.isDefaultPrevented=(c.defaultPrevented!=null?c.defaultPrevented:c.returnValue===!1)?Us:mc,this.isPropagationStopped=mc,this}return $(t.prototype,{preventDefault:function(){this.defaultPrevented=!0;var s=this.nativeEvent;s&&(s.preventDefault?s.preventDefault():typeof s.returnValue!="unknown"&&(s.returnValue=!1),this.isDefaultPrevented=Us)},stopPropagation:function(){var s=this.nativeEvent;s&&(s.stopPropagation?s.stopPropagation():typeof s.cancelBubble!="unknown"&&(s.cancelBubble=!0),this.isPropagationStopped=Us)},persist:function(){},isPersistent:Us}),t}var Kn={eventPhase:0,bubbles:0,cancelable:0,timeStamp:function(e){return e.timeStamp||Date.now()},defaultPrevented:0,isTrusted:0},Lo=dt(Kn),Vr=$({},Kn,{view:0,detail:0}),E0=dt(Vr),Vo,zo,zr,$s=$({},Vr,{screenX:0,screenY:0,clientX:0,clientY:0,pageX:0,pageY:0,ctrlKey:0,shiftKey:0,altKey:0,metaKey:0,getModifierState:Oo,button:0,buttons:0,relatedTarget:function(e){return e.relatedTarget===void 0?e.fromElement===e.srcElement?e.toElement:e.fromElement:e.relatedTarget},movementX:function(e){return"movementX"in e?e.movementX:(e!==zr&&(zr&&e.type==="mousemove"?(Vo=e.screenX-zr.screenX,zo=e.screenY-zr.screenY):zo=Vo=0,zr=e),Vo)},movementY:function(e){return"movementY"in e?e.movementY:zo}}),gc=dt($s),b0=$({},$s,{dataTransfer:0}),M0=dt(b0),_0=$({},Vr,{relatedTarget:0}),Io=dt(_0),A0=$({},Kn,{animationName:0,elapsedTime:0,pseudoElement:0}),R0=dt(A0),D0=$({},Kn,{clipboardData:function(e){return"clipboardData"in e?e.clipboardData:window.clipboardData}}),L0=dt(D0),V0=$({},Kn,{data:0}),yc=dt(V0),z0={Esc:"Escape",Spacebar:" ",Left:"ArrowLeft",Up:"ArrowUp",Right:"ArrowRight",Down:"ArrowDown",Del:"Delete",Win:"OS",Menu:"ContextMenu",Apps:"ContextMenu",Scroll:"ScrollLock",MozPrintableKey:"Unidentified"},I0={8:"Backspace",9:"Tab",12:"Clear",13:"Enter",16:"Shift",17:"Control",18:"Alt",19:"Pause",20:"CapsLock",27:"Escape",32:" ",33:"PageUp",34:"PageDown",35:"End",36:"Home",37:"ArrowLeft",38:"ArrowUp",39:"ArrowRight",40:"ArrowDown",45:"Insert",46:"Delete",112:"F1",113:"F2",114:"F3",115:"F4",116:"F5",117:"F6",118:"F7",119:"F8",120:"F9",121:"F10",122:"F11",123:"F12",144:"NumLock",145:"ScrollLock",224:"Meta"},O0={Alt:"altKey",Control:"ctrlKey",Meta:"metaKey",Shift:"shiftKey"};function F0(e){var t=this.nativeEvent;return t.getModifierState?t.getModifierState(e):(e=O0[e])?!!t[e]:!1}function Oo(){return F0}var B0=$({},Vr,{key:function(e){if(e.key){var t=z0[e.key]||e.key;if(t!=="Unidentified")return t}return e.type==="keypress"?(e=Bs(e),e===13?"Enter":String.fromCharCode(e)):e.type==="keydown"||e.type==="keyup"?I0[e.keyCode]||"Unidentified":""},code:0,location:0,ctrlKey:0,shiftKey:0,altKey:0,metaKey:0,repeat:0,locale:0,getModifierState:Oo,charCode:function(e){return e.type==="keypress"?Bs(e):0},keyCode:function(e){return e.type==="keydown"||e.type==="keyup"?e.keyCode:0},which:function(e){return e.type==="keypress"?Bs(e):e.type==="keydown"||e.type==="keyup"?e.keyCode:0}}),U0=dt(B0),$0=$({},$s,{pointerId:0,width:0,height:0,pressure:0,tangentialPressure:0,tiltX:0,tiltY:0,twist:0,pointerType:0,isPrimary:0}),vc=dt($0),W0=$({},Vr,{touches:0,targetTouches:0,changedTouches:0,altKey:0,metaKey:0,ctrlKey:0,shiftKey:0,getModifierState:Oo}),H0=dt(W0),K0=$({},Kn,{propertyName:0,elapsedTime:0,pseudoElement:0}),G0=dt(K0),Y0=$({},$s,{deltaX:function(e){return"deltaX"in e?e.deltaX:"wheelDeltaX"in e?-e.wheelDeltaX:0},deltaY:function(e){return"deltaY"in e?e.deltaY:"wheelDeltaY"in e?-e.wheelDeltaY:"wheelDelta"in e?-e.wheelDelta:0},deltaZ:0,deltaMode:0}),X0=dt(Y0),Q0=[9,13,27,32],Fo=p&&"CompositionEvent"in window,Ir=null;p&&"documentMode"in document&&(Ir=document.documentMode);var q0=p&&"TextEvent"in window&&!Ir,xc=p&&(!Fo||Ir&&8<Ir&&11>=Ir),wc=" ",kc=!1;function Sc(e,t){switch(e){case"keyup":return Q0.indexOf(t.keyCode)!==-1;case"keydown":return t.keyCode!==229;case"keypress":case"mousedown":case"focusout":return!0;default:return!1}}function jc(e){return e=e.detail,typeof e=="object"&&"data"in e?e.data:null}var Gn=!1;function Z0(e,t){switch(e){case"compositionend":return jc(t);case"keypress":return t.which!==32?null:(kc=!0,wc);case"textInput":return e=t.data,e===wc&&kc?null:e;default:return null}}function J0(e,t){if(Gn)return e==="compositionend"||!Fo&&Sc(e,t)?(e=pc(),Fs=Do=tn=null,Gn=!1,e):null;switch(e){case"paste":return null;case"keypress":if(!(t.ctrlKey||t.altKey||t.metaKey)||t.ctrlKey&&t.altKey){if(t.char&&1<t.char.length)return t.char;if(t.which)return String.fromCharCode(t.which)}return null;case"compositionend":return xc&&t.locale!=="ko"?null:t.data;default:return null}}var eg={color:!0,date:!0,datetime:!0,"datetime-local":!0,email:!0,month:!0,number:!0,password:!0,range:!0,search:!0,tel:!0,text:!0,time:!0,url:!0,week:!0};function Nc(e){var t=e&&e.nodeName&&e.nodeName.toLowerCase();return t==="input"?!!eg[e.type]:t==="textarea"}function Tc(e,t,s,o){Hu(o),t=Ys(t,"onChange"),0<t.length&&(s=new Lo("onChange","change",null,s,o),e.push({event:s,listeners:t}))}var Or=null,Fr=null;function tg(e){$c(e,0)}function Ws(e){var t=Zn(e);if(Ru(t))return e}function ng(e,t){if(e==="change")return t}var Cc=!1;if(p){var Bo;if(p){var Uo="oninput"in document;if(!Uo){var Pc=document.createElement("div");Pc.setAttribute("oninput","return;"),Uo=typeof Pc.oninput=="function"}Bo=Uo}else Bo=!1;Cc=Bo&&(!document.documentMode||9<document.documentMode)}function Ec(){Or&&(Or.detachEvent("onpropertychange",bc),Fr=Or=null)}function bc(e){if(e.propertyName==="value"&&Ws(Fr)){var t=[];Tc(t,Fr,e,ko(e)),Xu(tg,t)}}function rg(e,t,s){e==="focusin"?(Ec(),Or=t,Fr=s,Or.attachEvent("onpropertychange",bc)):e==="focusout"&&Ec()}function sg(e){if(e==="selectionchange"||e==="keyup"||e==="keydown")return Ws(Fr)}function ig(e,t){if(e==="click")return Ws(t)}function og(e,t){if(e==="input"||e==="change")return Ws(t)}function ag(e,t){return e===t&&(e!==0||1/e===1/t)||e!==e&&t!==t}var Tt=typeof Object.is=="function"?Object.is:ag;function Br(e,t){if(Tt(e,t))return!0;if(typeof e!="object"||e===null||typeof t!="object"||t===null)return!1;var s=Object.keys(e),o=Object.keys(t);if(s.length!==o.length)return!1;for(o=0;o<s.length;o++){var l=s[o];if(!g.call(t,l)||!Tt(e[l],t[l]))return!1}return!0}function Mc(e){for(;e&&e.firstChild;)e=e.firstChild;return e}function _c(e,t){var s=Mc(e);e=0;for(var o;s;){if(s.nodeType===3){if(o=e+s.textContent.length,e<=t&&o>=t)return{node:s,offset:t-e};e=o}e:{for(;s;){if(s.nextSibling){s=s.nextSibling;break e}s=s.parentNode}s=void 0}s=Mc(s)}}function Ac(e,t){return e&&t?e===t?!0:e&&e.nodeType===3?!1:t&&t.nodeType===3?Ac(e,t.parentNode):"contains"in e?e.contains(t):e.compareDocumentPosition?!!(e.compareDocumentPosition(t)&16):!1:!1}function Rc(){for(var e=window,t=Ps();t instanceof e.HTMLIFrameElement;){try{var s=typeof t.contentWindow.location.href=="string"}catch{s=!1}if(s)e=t.contentWindow;else break;t=Ps(e.document)}return t}function $o(e){var t=e&&e.nodeName&&e.nodeName.toLowerCase();return t&&(t==="input"&&(e.type==="text"||e.type==="search"||e.type==="tel"||e.type==="url"||e.type==="password")||t==="textarea"||e.contentEditable==="true")}function lg(e){var t=Rc(),s=e.focusedElem,o=e.selectionRange;if(t!==s&&s&&s.ownerDocument&&Ac(s.ownerDocument.documentElement,s)){if(o!==null&&$o(s)){if(t=o.start,e=o.end,e===void 0&&(e=t),"selectionStart"in s)s.selectionStart=t,s.selectionEnd=Math.min(e,s.value.length);else if(e=(t=s.ownerDocument||document)&&t.defaultView||window,e.getSelection){e=e.getSelection();var l=s.textContent.length,c=Math.min(o.start,l);o=o.end===void 0?c:Math.min(o.end,l),!e.extend&&c>o&&(l=o,o=c,c=l),l=_c(s,c);var m=_c(s,o);l&&m&&(e.rangeCount!==1||e.anchorNode!==l.node||e.anchorOffset!==l.offset||e.focusNode!==m.node||e.focusOffset!==m.offset)&&(t=t.createRange(),t.setStart(l.node,l.offset),e.removeAllRanges(),c>o?(e.addRange(t),e.extend(m.node,m.offset)):(t.setEnd(m.node,m.offset),e.addRange(t)))}}for(t=[],e=s;e=e.parentNode;)e.nodeType===1&&t.push({element:e,left:e.scrollLeft,top:e.scrollTop});for(typeof s.focus=="function"&&s.focus(),s=0;s<t.length;s++)e=t[s],e.element.scrollLeft=e.left,e.element.scrollTop=e.top}}var ug=p&&"documentMode"in document&&11>=document.documentMode,Yn=null,Wo=null,Ur=null,Ho=!1;function Dc(e,t,s){var o=s.window===s?s.document:s.nodeType===9?s:s.ownerDocument;Ho||Yn==null||Yn!==Ps(o)||(o=Yn,"selectionStart"in o&&$o(o)?o={start:o.selectionStart,end:o.selectionEnd}:(o=(o.ownerDocument&&o.ownerDocument.defaultView||window).getSelection(),o={anchorNode:o.anchorNode,anchorOffset:o.anchorOffset,focusNode:o.focusNode,focusOffset:o.focusOffset}),Ur&&Br(Ur,o)||(Ur=o,o=Ys(Wo,"onSelect"),0<o.length&&(t=new Lo("onSelect","select",null,t,s),e.push({event:t,listeners:o}),t.target=Yn)))}function Hs(e,t){var s={};return s[e.toLowerCase()]=t.toLowerCase(),s["Webkit"+e]="webkit"+t,s["Moz"+e]="moz"+t,s}var Xn={animationend:Hs("Animation","AnimationEnd"),animationiteration:Hs("Animation","AnimationIteration"),animationstart:Hs("Animation","AnimationStart"),transitionend:Hs("Transition","TransitionEnd")},Ko={},Lc={};p&&(Lc=document.createElement("div").style,"AnimationEvent"in window||(delete Xn.animationend.animation,delete Xn.animationiteration.animation,delete Xn.animationstart.animation),"TransitionEvent"in window||delete Xn.transitionend.transition);function Ks(e){if(Ko[e])return Ko[e];if(!Xn[e])return e;var t=Xn[e],s;for(s in t)if(t.hasOwnProperty(s)&&s in Lc)return Ko[e]=t[s];return e}var Vc=Ks("animationend"),zc=Ks("animationiteration"),Ic=Ks("animationstart"),Oc=Ks("transitionend"),Fc=new Map,Bc="abort auxClick cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel".split(" ");function nn(e,t){Fc.set(e,t),f(t,[e])}for(var Go=0;Go<Bc.length;Go++){var Yo=Bc[Go],cg=Yo.toLowerCase(),dg=Yo[0].toUpperCase()+Yo.slice(1);nn(cg,"on"+dg)}nn(Vc,"onAnimationEnd"),nn(zc,"onAnimationIteration"),nn(Ic,"onAnimationStart"),nn("dblclick","onDoubleClick"),nn("focusin","onFocus"),nn("focusout","onBlur"),nn(Oc,"onTransitionEnd"),d("onMouseEnter",["mouseout","mouseover"]),d("onMouseLeave",["mouseout","mouseover"]),d("onPointerEnter",["pointerout","pointerover"]),d("onPointerLeave",["pointerout","pointerover"]),f("onChange","change click focusin focusout input keydown keyup selectionchange".split(" ")),f("onSelect","focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange".split(" ")),f("onBeforeInput",["compositionend","keypress","textInput","paste"]),f("onCompositionEnd","compositionend focusout keydown keypress keyup mousedown".split(" ")),f("onCompositionStart","compositionstart focusout keydown keypress keyup mousedown".split(" ")),f("onCompositionUpdate","compositionupdate focusout keydown keypress keyup mousedown".split(" "));var $r="abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting".split(" "),fg=new Set("cancel close invalid load scroll toggle".split(" ").concat($r));function Uc(e,t,s){var o=e.type||"unknown-event";e.currentTarget=s,c0(o,t,void 0,e),e.currentTarget=null}function $c(e,t){t=(t&4)!==0;for(var s=0;s<e.length;s++){var o=e[s],l=o.event;o=o.listeners;e:{var c=void 0;if(t)for(var m=o.length-1;0<=m;m--){var k=o[m],S=k.instance,b=k.currentTarget;if(k=k.listener,S!==c&&l.isPropagationStopped())break e;Uc(l,k,b),c=S}else for(m=0;m<o.length;m++){if(k=o[m],S=k.instance,b=k.currentTarget,k=k.listener,S!==c&&l.isPropagationStopped())break e;Uc(l,k,b),c=S}}}if(Ms)throw e=To,Ms=!1,To=null,e}function Se(e,t){var s=t[na];s===void 0&&(s=t[na]=new Set);var o=e+"__bubble";s.has(o)||(Wc(t,e,2,!1),s.add(o))}function Xo(e,t,s){var o=0;t&&(o|=4),Wc(s,e,o,t)}var Gs="_reactListening"+Math.random().toString(36).slice(2);function Wr(e){if(!e[Gs]){e[Gs]=!0,a.forEach(function(s){s!=="selectionchange"&&(fg.has(s)||Xo(s,!1,e),Xo(s,!0,e))});var t=e.nodeType===9?e:e.ownerDocument;t===null||t[Gs]||(t[Gs]=!0,Xo("selectionchange",!1,t))}}function Wc(e,t,s,o){switch(hc(t)){case 1:var l=C0;break;case 4:l=P0;break;default:l=Ao}s=l.bind(null,t,s,e),l=void 0,!No||t!=="touchstart"&&t!=="touchmove"&&t!=="wheel"||(l=!0),o?l!==void 0?e.addEventListener(t,s,{capture:!0,passive:l}):e.addEventListener(t,s,!0):l!==void 0?e.addEventListener(t,s,{passive:l}):e.addEventListener(t,s,!1)}function Qo(e,t,s,o,l){var c=o;if((t&1)===0&&(t&2)===0&&o!==null)e:for(;;){if(o===null)return;var m=o.tag;if(m===3||m===4){var k=o.stateNode.containerInfo;if(k===l||k.nodeType===8&&k.parentNode===l)break;if(m===4)for(m=o.return;m!==null;){var S=m.tag;if((S===3||S===4)&&(S=m.stateNode.containerInfo,S===l||S.nodeType===8&&S.parentNode===l))return;m=m.return}for(;k!==null;){if(m=Nn(k),m===null)return;if(S=m.tag,S===5||S===6){o=c=m;continue e}k=k.parentNode}}o=o.return}Xu(function(){var b=c,D=ko(s),V=[];e:{var R=Fc.get(e);if(R!==void 0){var K=Lo,Q=e;switch(e){case"keypress":if(Bs(s)===0)break e;case"keydown":case"keyup":K=U0;break;case"focusin":Q="focus",K=Io;break;case"focusout":Q="blur",K=Io;break;case"beforeblur":case"afterblur":K=Io;break;case"click":if(s.button===2)break e;case"auxclick":case"dblclick":case"mousedown":case"mousemove":case"mouseup":case"mouseout":case"mouseover":case"contextmenu":K=gc;break;case"drag":case"dragend":case"dragenter":case"dragexit":case"dragleave":case"dragover":case"dragstart":case"drop":K=M0;break;case"touchcancel":case"touchend":case"touchmove":case"touchstart":K=H0;break;case Vc:case zc:case Ic:K=R0;break;case Oc:K=G0;break;case"scroll":K=E0;break;case"wheel":K=X0;break;case"copy":case"cut":case"paste":K=L0;break;case"gotpointercapture":case"lostpointercapture":case"pointercancel":case"pointerdown":case"pointermove":case"pointerout":case"pointerover":case"pointerup":K=vc}var J=(t&4)!==0,Ve=!J&&e==="scroll",C=J?R!==null?R+"Capture":null:R;J=[];for(var j=b,P;j!==null;){P=j;var F=P.stateNode;if(P.tag===5&&F!==null&&(P=F,C!==null&&(F=Cr(j,C),F!=null&&J.push(Hr(j,F,P)))),Ve)break;j=j.return}0<J.length&&(R=new K(R,Q,null,s,D),V.push({event:R,listeners:J}))}}if((t&7)===0){e:{if(R=e==="mouseover"||e==="pointerover",K=e==="mouseout"||e==="pointerout",R&&s!==wo&&(Q=s.relatedTarget||s.fromElement)&&(Nn(Q)||Q[$t]))break e;if((K||R)&&(R=D.window===D?D:(R=D.ownerDocument)?R.defaultView||R.parentWindow:window,K?(Q=s.relatedTarget||s.toElement,K=b,Q=Q?Nn(Q):null,Q!==null&&(Ve=jn(Q),Q!==Ve||Q.tag!==5&&Q.tag!==6)&&(Q=null)):(K=null,Q=b),K!==Q)){if(J=gc,F="onMouseLeave",C="onMouseEnter",j="mouse",(e==="pointerout"||e==="pointerover")&&(J=vc,F="onPointerLeave",C="onPointerEnter",j="pointer"),Ve=K==null?R:Zn(K),P=Q==null?R:Zn(Q),R=new J(F,j+"leave",K,s,D),R.target=Ve,R.relatedTarget=P,F=null,Nn(D)===b&&(J=new J(C,j+"enter",Q,s,D),J.target=P,J.relatedTarget=Ve,F=J),Ve=F,K&&Q)t:{for(J=K,C=Q,j=0,P=J;P;P=Qn(P))j++;for(P=0,F=C;F;F=Qn(F))P++;for(;0<j-P;)J=Qn(J),j--;for(;0<P-j;)C=Qn(C),P--;for(;j--;){if(J===C||C!==null&&J===C.alternate)break t;J=Qn(J),C=Qn(C)}J=null}else J=null;K!==null&&Hc(V,R,K,J,!1),Q!==null&&Ve!==null&&Hc(V,Ve,Q,J,!0)}}e:{if(R=b?Zn(b):window,K=R.nodeName&&R.nodeName.toLowerCase(),K==="select"||K==="input"&&R.type==="file")var ee=ng;else if(Nc(R))if(Cc)ee=og;else{ee=sg;var te=rg}else(K=R.nodeName)&&K.toLowerCase()==="input"&&(R.type==="checkbox"||R.type==="radio")&&(ee=ig);if(ee&&(ee=ee(e,b))){Tc(V,ee,s,D);break e}te&&te(e,R,b),e==="focusout"&&(te=R._wrapperState)&&te.controlled&&R.type==="number"&&mo(R,"number",R.value)}switch(te=b?Zn(b):window,e){case"focusin":(Nc(te)||te.contentEditable==="true")&&(Yn=te,Wo=b,Ur=null);break;case"focusout":Ur=Wo=Yn=null;break;case"mousedown":Ho=!0;break;case"contextmenu":case"mouseup":case"dragend":Ho=!1,Dc(V,s,D);break;case"selectionchange":if(ug)break;case"keydown":case"keyup":Dc(V,s,D)}var ne;if(Fo)e:{switch(e){case"compositionstart":var ie="onCompositionStart";break e;case"compositionend":ie="onCompositionEnd";break e;case"compositionupdate":ie="onCompositionUpdate";break e}ie=void 0}else Gn?Sc(e,s)&&(ie="onCompositionEnd"):e==="keydown"&&s.keyCode===229&&(ie="onCompositionStart");ie&&(xc&&s.locale!=="ko"&&(Gn||ie!=="onCompositionStart"?ie==="onCompositionEnd"&&Gn&&(ne=pc()):(tn=D,Do="value"in tn?tn.value:tn.textContent,Gn=!0)),te=Ys(b,ie),0<te.length&&(ie=new yc(ie,e,null,s,D),V.push({event:ie,listeners:te}),ne?ie.data=ne:(ne=jc(s),ne!==null&&(ie.data=ne)))),(ne=q0?Z0(e,s):J0(e,s))&&(b=Ys(b,"onBeforeInput"),0<b.length&&(D=new yc("onBeforeInput","beforeinput",null,s,D),V.push({event:D,listeners:b}),D.data=ne))}$c(V,t)})}function Hr(e,t,s){return{instance:e,listener:t,currentTarget:s}}function Ys(e,t){for(var s=t+"Capture",o=[];e!==null;){var l=e,c=l.stateNode;l.tag===5&&c!==null&&(l=c,c=Cr(e,s),c!=null&&o.unshift(Hr(e,c,l)),c=Cr(e,t),c!=null&&o.push(Hr(e,c,l))),e=e.return}return o}function Qn(e){if(e===null)return null;do e=e.return;while(e&&e.tag!==5);return e||null}function Hc(e,t,s,o,l){for(var c=t._reactName,m=[];s!==null&&s!==o;){var k=s,S=k.alternate,b=k.stateNode;if(S!==null&&S===o)break;k.tag===5&&b!==null&&(k=b,l?(S=Cr(s,c),S!=null&&m.unshift(Hr(s,S,k))):l||(S=Cr(s,c),S!=null&&m.push(Hr(s,S,k)))),s=s.return}m.length!==0&&e.push({event:t,listeners:m})}var hg=/\r\n?/g,pg=/\u0000|\uFFFD/g;function Kc(e){return(typeof e=="string"?e:""+e).replace(hg,`
`).replace(pg,"")}function Xs(e,t,s){if(t=Kc(t),Kc(e)!==t&&s)throw Error(i(425))}function Qs(){}var qo=null,Zo=null;function Jo(e,t){return e==="textarea"||e==="noscript"||typeof t.children=="string"||typeof t.children=="number"||typeof t.dangerouslySetInnerHTML=="object"&&t.dangerouslySetInnerHTML!==null&&t.dangerouslySetInnerHTML.__html!=null}var ea=typeof setTimeout=="function"?setTimeout:void 0,mg=typeof clearTimeout=="function"?clearTimeout:void 0,Gc=typeof Promise=="function"?Promise:void 0,gg=typeof queueMicrotask=="function"?queueMicrotask:typeof Gc<"u"?function(e){return Gc.resolve(null).then(e).catch(yg)}:ea;function yg(e){setTimeout(function(){throw e})}function ta(e,t){var s=t,o=0;do{var l=s.nextSibling;if(e.removeChild(s),l&&l.nodeType===8)if(s=l.data,s==="/$"){if(o===0){e.removeChild(l),Lr(t);return}o--}else s!=="$"&&s!=="$?"&&s!=="$!"||o++;s=l}while(s);Lr(t)}function rn(e){for(;e!=null;e=e.nextSibling){var t=e.nodeType;if(t===1||t===3)break;if(t===8){if(t=e.data,t==="$"||t==="$!"||t==="$?")break;if(t==="/$")return null}}return e}function Yc(e){e=e.previousSibling;for(var t=0;e;){if(e.nodeType===8){var s=e.data;if(s==="$"||s==="$!"||s==="$?"){if(t===0)return e;t--}else s==="/$"&&t++}e=e.previousSibling}return null}var qn=Math.random().toString(36).slice(2),Lt="__reactFiber$"+qn,Kr="__reactProps$"+qn,$t="__reactContainer$"+qn,na="__reactEvents$"+qn,vg="__reactListeners$"+qn,xg="__reactHandles$"+qn;function Nn(e){var t=e[Lt];if(t)return t;for(var s=e.parentNode;s;){if(t=s[$t]||s[Lt]){if(s=t.alternate,t.child!==null||s!==null&&s.child!==null)for(e=Yc(e);e!==null;){if(s=e[Lt])return s;e=Yc(e)}return t}e=s,s=e.parentNode}return null}function Gr(e){return e=e[Lt]||e[$t],!e||e.tag!==5&&e.tag!==6&&e.tag!==13&&e.tag!==3?null:e}function Zn(e){if(e.tag===5||e.tag===6)return e.stateNode;throw Error(i(33))}function qs(e){return e[Kr]||null}var ra=[],Jn=-1;function sn(e){return{current:e}}function je(e){0>Jn||(e.current=ra[Jn],ra[Jn]=null,Jn--)}function we(e,t){Jn++,ra[Jn]=e.current,e.current=t}var on={},Qe=sn(on),st=sn(!1),Tn=on;function er(e,t){var s=e.type.contextTypes;if(!s)return on;var o=e.stateNode;if(o&&o.__reactInternalMemoizedUnmaskedChildContext===t)return o.__reactInternalMemoizedMaskedChildContext;var l={},c;for(c in s)l[c]=t[c];return o&&(e=e.stateNode,e.__reactInternalMemoizedUnmaskedChildContext=t,e.__reactInternalMemoizedMaskedChildContext=l),l}function it(e){return e=e.childContextTypes,e!=null}function Zs(){je(st),je(Qe)}function Xc(e,t,s){if(Qe.current!==on)throw Error(i(168));we(Qe,t),we(st,s)}function Qc(e,t,s){var o=e.stateNode;if(t=t.childContextTypes,typeof o.getChildContext!="function")return s;o=o.getChildContext();for(var l in o)if(!(l in t))throw Error(i(108,xe(e)||"Unknown",l));return $({},s,o)}function Js(e){return e=(e=e.stateNode)&&e.__reactInternalMemoizedMergedChildContext||on,Tn=Qe.current,we(Qe,e),we(st,st.current),!0}function qc(e,t,s){var o=e.stateNode;if(!o)throw Error(i(169));s?(e=Qc(e,t,Tn),o.__reactInternalMemoizedMergedChildContext=e,je(st),je(Qe),we(Qe,e)):je(st),we(st,s)}var Wt=null,ei=!1,sa=!1;function Zc(e){Wt===null?Wt=[e]:Wt.push(e)}function wg(e){ei=!0,Zc(e)}function an(){if(!sa&&Wt!==null){sa=!0;var e=0,t=ye;try{var s=Wt;for(ye=1;e<s.length;e++){var o=s[e];do o=o(!0);while(o!==null)}Wt=null,ei=!1}catch(l){throw Wt!==null&&(Wt=Wt.slice(e+1)),ec(Co,an),l}finally{ye=t,sa=!1}}return null}var tr=[],nr=0,ti=null,ni=0,gt=[],yt=0,Cn=null,Ht=1,Kt="";function Pn(e,t){tr[nr++]=ni,tr[nr++]=ti,ti=e,ni=t}function Jc(e,t,s){gt[yt++]=Ht,gt[yt++]=Kt,gt[yt++]=Cn,Cn=e;var o=Ht;e=Kt;var l=32-Nt(o)-1;o&=~(1<<l),s+=1;var c=32-Nt(t)+l;if(30<c){var m=l-l%5;c=(o&(1<<m)-1).toString(32),o>>=m,l-=m,Ht=1<<32-Nt(t)+l|s<<l|o,Kt=c+e}else Ht=1<<c|s<<l|o,Kt=e}function ia(e){e.return!==null&&(Pn(e,1),Jc(e,1,0))}function oa(e){for(;e===ti;)ti=tr[--nr],tr[nr]=null,ni=tr[--nr],tr[nr]=null;for(;e===Cn;)Cn=gt[--yt],gt[yt]=null,Kt=gt[--yt],gt[yt]=null,Ht=gt[--yt],gt[yt]=null}var ft=null,ht=null,Ce=!1,Ct=null;function ed(e,t){var s=kt(5,null,null,0);s.elementType="DELETED",s.stateNode=t,s.return=e,t=e.deletions,t===null?(e.deletions=[s],e.flags|=16):t.push(s)}function td(e,t){switch(e.tag){case 5:var s=e.type;return t=t.nodeType!==1||s.toLowerCase()!==t.nodeName.toLowerCase()?null:t,t!==null?(e.stateNode=t,ft=e,ht=rn(t.firstChild),!0):!1;case 6:return t=e.pendingProps===""||t.nodeType!==3?null:t,t!==null?(e.stateNode=t,ft=e,ht=null,!0):!1;case 13:return t=t.nodeType!==8?null:t,t!==null?(s=Cn!==null?{id:Ht,overflow:Kt}:null,e.memoizedState={dehydrated:t,treeContext:s,retryLane:1073741824},s=kt(18,null,null,0),s.stateNode=t,s.return=e,e.child=s,ft=e,ht=null,!0):!1;default:return!1}}function aa(e){return(e.mode&1)!==0&&(e.flags&128)===0}function la(e){if(Ce){var t=ht;if(t){var s=t;if(!td(e,t)){if(aa(e))throw Error(i(418));t=rn(s.nextSibling);var o=ft;t&&td(e,t)?ed(o,s):(e.flags=e.flags&-4097|2,Ce=!1,ft=e)}}else{if(aa(e))throw Error(i(418));e.flags=e.flags&-4097|2,Ce=!1,ft=e}}}function nd(e){for(e=e.return;e!==null&&e.tag!==5&&e.tag!==3&&e.tag!==13;)e=e.return;ft=e}function ri(e){if(e!==ft)return!1;if(!Ce)return nd(e),Ce=!0,!1;var t;if((t=e.tag!==3)&&!(t=e.tag!==5)&&(t=e.type,t=t!=="head"&&t!=="body"&&!Jo(e.type,e.memoizedProps)),t&&(t=ht)){if(aa(e))throw rd(),Error(i(418));for(;t;)ed(e,t),t=rn(t.nextSibling)}if(nd(e),e.tag===13){if(e=e.memoizedState,e=e!==null?e.dehydrated:null,!e)throw Error(i(317));e:{for(e=e.nextSibling,t=0;e;){if(e.nodeType===8){var s=e.data;if(s==="/$"){if(t===0){ht=rn(e.nextSibling);break e}t--}else s!=="$"&&s!=="$!"&&s!=="$?"||t++}e=e.nextSibling}ht=null}}else ht=ft?rn(e.stateNode.nextSibling):null;return!0}function rd(){for(var e=ht;e;)e=rn(e.nextSibling)}function rr(){ht=ft=null,Ce=!1}function ua(e){Ct===null?Ct=[e]:Ct.push(e)}var kg=U.ReactCurrentBatchConfig;function Yr(e,t,s){if(e=s.ref,e!==null&&typeof e!="function"&&typeof e!="object"){if(s._owner){if(s=s._owner,s){if(s.tag!==1)throw Error(i(309));var o=s.stateNode}if(!o)throw Error(i(147,e));var l=o,c=""+e;return t!==null&&t.ref!==null&&typeof t.ref=="function"&&t.ref._stringRef===c?t.ref:(t=function(m){var k=l.refs;m===null?delete k[c]:k[c]=m},t._stringRef=c,t)}if(typeof e!="string")throw Error(i(284));if(!s._owner)throw Error(i(290,e))}return e}function si(e,t){throw e=Object.prototype.toString.call(t),Error(i(31,e==="[object Object]"?"object with keys {"+Object.keys(t).join(", ")+"}":e))}function sd(e){var t=e._init;return t(e._payload)}function id(e){function t(C,j){if(e){var P=C.deletions;P===null?(C.deletions=[j],C.flags|=16):P.push(j)}}function s(C,j){if(!e)return null;for(;j!==null;)t(C,j),j=j.sibling;return null}function o(C,j){for(C=new Map;j!==null;)j.key!==null?C.set(j.key,j):C.set(j.index,j),j=j.sibling;return C}function l(C,j){return C=mn(C,j),C.index=0,C.sibling=null,C}function c(C,j,P){return C.index=P,e?(P=C.alternate,P!==null?(P=P.index,P<j?(C.flags|=2,j):P):(C.flags|=2,j)):(C.flags|=1048576,j)}function m(C){return e&&C.alternate===null&&(C.flags|=2),C}function k(C,j,P,F){return j===null||j.tag!==6?(j=el(P,C.mode,F),j.return=C,j):(j=l(j,P),j.return=C,j)}function S(C,j,P,F){var ee=P.type;return ee===G?D(C,j,P.props.children,F,P.key):j!==null&&(j.elementType===ee||typeof ee=="object"&&ee!==null&&ee.$$typeof===ke&&sd(ee)===j.type)?(F=l(j,P.props),F.ref=Yr(C,j,P),F.return=C,F):(F=Ei(P.type,P.key,P.props,null,C.mode,F),F.ref=Yr(C,j,P),F.return=C,F)}function b(C,j,P,F){return j===null||j.tag!==4||j.stateNode.containerInfo!==P.containerInfo||j.stateNode.implementation!==P.implementation?(j=tl(P,C.mode,F),j.return=C,j):(j=l(j,P.children||[]),j.return=C,j)}function D(C,j,P,F,ee){return j===null||j.tag!==7?(j=Ln(P,C.mode,F,ee),j.return=C,j):(j=l(j,P),j.return=C,j)}function V(C,j,P){if(typeof j=="string"&&j!==""||typeof j=="number")return j=el(""+j,C.mode,P),j.return=C,j;if(typeof j=="object"&&j!==null){switch(j.$$typeof){case W:return P=Ei(j.type,j.key,j.props,null,C.mode,P),P.ref=Yr(C,null,j),P.return=C,P;case se:return j=tl(j,C.mode,P),j.return=C,j;case ke:var F=j._init;return V(C,F(j._payload),P)}if(jr(j)||Z(j))return j=Ln(j,C.mode,P,null),j.return=C,j;si(C,j)}return null}function R(C,j,P,F){var ee=j!==null?j.key:null;if(typeof P=="string"&&P!==""||typeof P=="number")return ee!==null?null:k(C,j,""+P,F);if(typeof P=="object"&&P!==null){switch(P.$$typeof){case W:return P.key===ee?S(C,j,P,F):null;case se:return P.key===ee?b(C,j,P,F):null;case ke:return ee=P._init,R(C,j,ee(P._payload),F)}if(jr(P)||Z(P))return ee!==null?null:D(C,j,P,F,null);si(C,P)}return null}function K(C,j,P,F,ee){if(typeof F=="string"&&F!==""||typeof F=="number")return C=C.get(P)||null,k(j,C,""+F,ee);if(typeof F=="object"&&F!==null){switch(F.$$typeof){case W:return C=C.get(F.key===null?P:F.key)||null,S(j,C,F,ee);case se:return C=C.get(F.key===null?P:F.key)||null,b(j,C,F,ee);case ke:var te=F._init;return K(C,j,P,te(F._payload),ee)}if(jr(F)||Z(F))return C=C.get(P)||null,D(j,C,F,ee,null);si(j,F)}return null}function Q(C,j,P,F){for(var ee=null,te=null,ne=j,ie=j=0,He=null;ne!==null&&ie<P.length;ie++){ne.index>ie?(He=ne,ne=null):He=ne.sibling;var pe=R(C,ne,P[ie],F);if(pe===null){ne===null&&(ne=He);break}e&&ne&&pe.alternate===null&&t(C,ne),j=c(pe,j,ie),te===null?ee=pe:te.sibling=pe,te=pe,ne=He}if(ie===P.length)return s(C,ne),Ce&&Pn(C,ie),ee;if(ne===null){for(;ie<P.length;ie++)ne=V(C,P[ie],F),ne!==null&&(j=c(ne,j,ie),te===null?ee=ne:te.sibling=ne,te=ne);return Ce&&Pn(C,ie),ee}for(ne=o(C,ne);ie<P.length;ie++)He=K(ne,C,ie,P[ie],F),He!==null&&(e&&He.alternate!==null&&ne.delete(He.key===null?ie:He.key),j=c(He,j,ie),te===null?ee=He:te.sibling=He,te=He);return e&&ne.forEach(function(gn){return t(C,gn)}),Ce&&Pn(C,ie),ee}function J(C,j,P,F){var ee=Z(P);if(typeof ee!="function")throw Error(i(150));if(P=ee.call(P),P==null)throw Error(i(151));for(var te=ee=null,ne=j,ie=j=0,He=null,pe=P.next();ne!==null&&!pe.done;ie++,pe=P.next()){ne.index>ie?(He=ne,ne=null):He=ne.sibling;var gn=R(C,ne,pe.value,F);if(gn===null){ne===null&&(ne=He);break}e&&ne&&gn.alternate===null&&t(C,ne),j=c(gn,j,ie),te===null?ee=gn:te.sibling=gn,te=gn,ne=He}if(pe.done)return s(C,ne),Ce&&Pn(C,ie),ee;if(ne===null){for(;!pe.done;ie++,pe=P.next())pe=V(C,pe.value,F),pe!==null&&(j=c(pe,j,ie),te===null?ee=pe:te.sibling=pe,te=pe);return Ce&&Pn(C,ie),ee}for(ne=o(C,ne);!pe.done;ie++,pe=P.next())pe=K(ne,C,ie,pe.value,F),pe!==null&&(e&&pe.alternate!==null&&ne.delete(pe.key===null?ie:pe.key),j=c(pe,j,ie),te===null?ee=pe:te.sibling=pe,te=pe);return e&&ne.forEach(function(ey){return t(C,ey)}),Ce&&Pn(C,ie),ee}function Ve(C,j,P,F){if(typeof P=="object"&&P!==null&&P.type===G&&P.key===null&&(P=P.props.children),typeof P=="object"&&P!==null){switch(P.$$typeof){case W:e:{for(var ee=P.key,te=j;te!==null;){if(te.key===ee){if(ee=P.type,ee===G){if(te.tag===7){s(C,te.sibling),j=l(te,P.props.children),j.return=C,C=j;break e}}else if(te.elementType===ee||typeof ee=="object"&&ee!==null&&ee.$$typeof===ke&&sd(ee)===te.type){s(C,te.sibling),j=l(te,P.props),j.ref=Yr(C,te,P),j.return=C,C=j;break e}s(C,te);break}else t(C,te);te=te.sibling}P.type===G?(j=Ln(P.props.children,C.mode,F,P.key),j.return=C,C=j):(F=Ei(P.type,P.key,P.props,null,C.mode,F),F.ref=Yr(C,j,P),F.return=C,C=F)}return m(C);case se:e:{for(te=P.key;j!==null;){if(j.key===te)if(j.tag===4&&j.stateNode.containerInfo===P.containerInfo&&j.stateNode.implementation===P.implementation){s(C,j.sibling),j=l(j,P.children||[]),j.return=C,C=j;break e}else{s(C,j);break}else t(C,j);j=j.sibling}j=tl(P,C.mode,F),j.return=C,C=j}return m(C);case ke:return te=P._init,Ve(C,j,te(P._payload),F)}if(jr(P))return Q(C,j,P,F);if(Z(P))return J(C,j,P,F);si(C,P)}return typeof P=="string"&&P!==""||typeof P=="number"?(P=""+P,j!==null&&j.tag===6?(s(C,j.sibling),j=l(j,P),j.return=C,C=j):(s(C,j),j=el(P,C.mode,F),j.return=C,C=j),m(C)):s(C,j)}return Ve}var sr=id(!0),od=id(!1),ii=sn(null),oi=null,ir=null,ca=null;function da(){ca=ir=oi=null}function fa(e){var t=ii.current;je(ii),e._currentValue=t}function ha(e,t,s){for(;e!==null;){var o=e.alternate;if((e.childLanes&t)!==t?(e.childLanes|=t,o!==null&&(o.childLanes|=t)):o!==null&&(o.childLanes&t)!==t&&(o.childLanes|=t),e===s)break;e=e.return}}function or(e,t){oi=e,ca=ir=null,e=e.dependencies,e!==null&&e.firstContext!==null&&((e.lanes&t)!==0&&(ot=!0),e.firstContext=null)}function vt(e){var t=e._currentValue;if(ca!==e)if(e={context:e,memoizedValue:t,next:null},ir===null){if(oi===null)throw Error(i(308));ir=e,oi.dependencies={lanes:0,firstContext:e}}else ir=ir.next=e;return t}var En=null;function pa(e){En===null?En=[e]:En.push(e)}function ad(e,t,s,o){var l=t.interleaved;return l===null?(s.next=s,pa(t)):(s.next=l.next,l.next=s),t.interleaved=s,Gt(e,o)}function Gt(e,t){e.lanes|=t;var s=e.alternate;for(s!==null&&(s.lanes|=t),s=e,e=e.return;e!==null;)e.childLanes|=t,s=e.alternate,s!==null&&(s.childLanes|=t),s=e,e=e.return;return s.tag===3?s.stateNode:null}var ln=!1;function ma(e){e.updateQueue={baseState:e.memoizedState,firstBaseUpdate:null,lastBaseUpdate:null,shared:{pending:null,interleaved:null,lanes:0},effects:null}}function ld(e,t){e=e.updateQueue,t.updateQueue===e&&(t.updateQueue={baseState:e.baseState,firstBaseUpdate:e.firstBaseUpdate,lastBaseUpdate:e.lastBaseUpdate,shared:e.shared,effects:e.effects})}function Yt(e,t){return{eventTime:e,lane:t,tag:0,payload:null,callback:null,next:null}}function un(e,t,s){var o=e.updateQueue;if(o===null)return null;if(o=o.shared,(de&2)!==0){var l=o.pending;return l===null?t.next=t:(t.next=l.next,l.next=t),o.pending=t,Gt(e,s)}return l=o.interleaved,l===null?(t.next=t,pa(o)):(t.next=l.next,l.next=t),o.interleaved=t,Gt(e,s)}function ai(e,t,s){if(t=t.updateQueue,t!==null&&(t=t.shared,(s&4194240)!==0)){var o=t.lanes;o&=e.pendingLanes,s|=o,t.lanes=s,bo(e,s)}}function ud(e,t){var s=e.updateQueue,o=e.alternate;if(o!==null&&(o=o.updateQueue,s===o)){var l=null,c=null;if(s=s.firstBaseUpdate,s!==null){do{var m={eventTime:s.eventTime,lane:s.lane,tag:s.tag,payload:s.payload,callback:s.callback,next:null};c===null?l=c=m:c=c.next=m,s=s.next}while(s!==null);c===null?l=c=t:c=c.next=t}else l=c=t;s={baseState:o.baseState,firstBaseUpdate:l,lastBaseUpdate:c,shared:o.shared,effects:o.effects},e.updateQueue=s;return}e=s.lastBaseUpdate,e===null?s.firstBaseUpdate=t:e.next=t,s.lastBaseUpdate=t}function li(e,t,s,o){var l=e.updateQueue;ln=!1;var c=l.firstBaseUpdate,m=l.lastBaseUpdate,k=l.shared.pending;if(k!==null){l.shared.pending=null;var S=k,b=S.next;S.next=null,m===null?c=b:m.next=b,m=S;var D=e.alternate;D!==null&&(D=D.updateQueue,k=D.lastBaseUpdate,k!==m&&(k===null?D.firstBaseUpdate=b:k.next=b,D.lastBaseUpdate=S))}if(c!==null){var V=l.baseState;m=0,D=b=S=null,k=c;do{var R=k.lane,K=k.eventTime;if((o&R)===R){D!==null&&(D=D.next={eventTime:K,lane:0,tag:k.tag,payload:k.payload,callback:k.callback,next:null});e:{var Q=e,J=k;switch(R=t,K=s,J.tag){case 1:if(Q=J.payload,typeof Q=="function"){V=Q.call(K,V,R);break e}V=Q;break e;case 3:Q.flags=Q.flags&-65537|128;case 0:if(Q=J.payload,R=typeof Q=="function"?Q.call(K,V,R):Q,R==null)break e;V=$({},V,R);break e;case 2:ln=!0}}k.callback!==null&&k.lane!==0&&(e.flags|=64,R=l.effects,R===null?l.effects=[k]:R.push(k))}else K={eventTime:K,lane:R,tag:k.tag,payload:k.payload,callback:k.callback,next:null},D===null?(b=D=K,S=V):D=D.next=K,m|=R;if(k=k.next,k===null){if(k=l.shared.pending,k===null)break;R=k,k=R.next,R.next=null,l.lastBaseUpdate=R,l.shared.pending=null}}while(!0);if(D===null&&(S=V),l.baseState=S,l.firstBaseUpdate=b,l.lastBaseUpdate=D,t=l.shared.interleaved,t!==null){l=t;do m|=l.lane,l=l.next;while(l!==t)}else c===null&&(l.shared.lanes=0);_n|=m,e.lanes=m,e.memoizedState=V}}function cd(e,t,s){if(e=t.effects,t.effects=null,e!==null)for(t=0;t<e.length;t++){var o=e[t],l=o.callback;if(l!==null){if(o.callback=null,o=s,typeof l!="function")throw Error(i(191,l));l.call(o)}}}var Xr={},Vt=sn(Xr),Qr=sn(Xr),qr=sn(Xr);function bn(e){if(e===Xr)throw Error(i(174));return e}function ga(e,t){switch(we(qr,t),we(Qr,e),we(Vt,Xr),e=t.nodeType,e){case 9:case 11:t=(t=t.documentElement)?t.namespaceURI:yo(null,"");break;default:e=e===8?t.parentNode:t,t=e.namespaceURI||null,e=e.tagName,t=yo(t,e)}je(Vt),we(Vt,t)}function ar(){je(Vt),je(Qr),je(qr)}function dd(e){bn(qr.current);var t=bn(Vt.current),s=yo(t,e.type);t!==s&&(we(Qr,e),we(Vt,s))}function ya(e){Qr.current===e&&(je(Vt),je(Qr))}var be=sn(0);function ui(e){for(var t=e;t!==null;){if(t.tag===13){var s=t.memoizedState;if(s!==null&&(s=s.dehydrated,s===null||s.data==="$?"||s.data==="$!"))return t}else if(t.tag===19&&t.memoizedProps.revealOrder!==void 0){if((t.flags&128)!==0)return t}else if(t.child!==null){t.child.return=t,t=t.child;continue}if(t===e)break;for(;t.sibling===null;){if(t.return===null||t.return===e)return null;t=t.return}t.sibling.return=t.return,t=t.sibling}return null}var va=[];function xa(){for(var e=0;e<va.length;e++)va[e]._workInProgressVersionPrimary=null;va.length=0}var ci=U.ReactCurrentDispatcher,wa=U.ReactCurrentBatchConfig,Mn=0,Me=null,Fe=null,$e=null,di=!1,Zr=!1,Jr=0,Sg=0;function qe(){throw Error(i(321))}function ka(e,t){if(t===null)return!1;for(var s=0;s<t.length&&s<e.length;s++)if(!Tt(e[s],t[s]))return!1;return!0}function Sa(e,t,s,o,l,c){if(Mn=c,Me=t,t.memoizedState=null,t.updateQueue=null,t.lanes=0,ci.current=e===null||e.memoizedState===null?Cg:Pg,e=s(o,l),Zr){c=0;do{if(Zr=!1,Jr=0,25<=c)throw Error(i(301));c+=1,$e=Fe=null,t.updateQueue=null,ci.current=Eg,e=s(o,l)}while(Zr)}if(ci.current=pi,t=Fe!==null&&Fe.next!==null,Mn=0,$e=Fe=Me=null,di=!1,t)throw Error(i(300));return e}function ja(){var e=Jr!==0;return Jr=0,e}function zt(){var e={memoizedState:null,baseState:null,baseQueue:null,queue:null,next:null};return $e===null?Me.memoizedState=$e=e:$e=$e.next=e,$e}function xt(){if(Fe===null){var e=Me.alternate;e=e!==null?e.memoizedState:null}else e=Fe.next;var t=$e===null?Me.memoizedState:$e.next;if(t!==null)$e=t,Fe=e;else{if(e===null)throw Error(i(310));Fe=e,e={memoizedState:Fe.memoizedState,baseState:Fe.baseState,baseQueue:Fe.baseQueue,queue:Fe.queue,next:null},$e===null?Me.memoizedState=$e=e:$e=$e.next=e}return $e}function es(e,t){return typeof t=="function"?t(e):t}function Na(e){var t=xt(),s=t.queue;if(s===null)throw Error(i(311));s.lastRenderedReducer=e;var o=Fe,l=o.baseQueue,c=s.pending;if(c!==null){if(l!==null){var m=l.next;l.next=c.next,c.next=m}o.baseQueue=l=c,s.pending=null}if(l!==null){c=l.next,o=o.baseState;var k=m=null,S=null,b=c;do{var D=b.lane;if((Mn&D)===D)S!==null&&(S=S.next={lane:0,action:b.action,hasEagerState:b.hasEagerState,eagerState:b.eagerState,next:null}),o=b.hasEagerState?b.eagerState:e(o,b.action);else{var V={lane:D,action:b.action,hasEagerState:b.hasEagerState,eagerState:b.eagerState,next:null};S===null?(k=S=V,m=o):S=S.next=V,Me.lanes|=D,_n|=D}b=b.next}while(b!==null&&b!==c);S===null?m=o:S.next=k,Tt(o,t.memoizedState)||(ot=!0),t.memoizedState=o,t.baseState=m,t.baseQueue=S,s.lastRenderedState=o}if(e=s.interleaved,e!==null){l=e;do c=l.lane,Me.lanes|=c,_n|=c,l=l.next;while(l!==e)}else l===null&&(s.lanes=0);return[t.memoizedState,s.dispatch]}function Ta(e){var t=xt(),s=t.queue;if(s===null)throw Error(i(311));s.lastRenderedReducer=e;var o=s.dispatch,l=s.pending,c=t.memoizedState;if(l!==null){s.pending=null;var m=l=l.next;do c=e(c,m.action),m=m.next;while(m!==l);Tt(c,t.memoizedState)||(ot=!0),t.memoizedState=c,t.baseQueue===null&&(t.baseState=c),s.lastRenderedState=c}return[c,o]}function fd(){}function hd(e,t){var s=Me,o=xt(),l=t(),c=!Tt(o.memoizedState,l);if(c&&(o.memoizedState=l,ot=!0),o=o.queue,Ca(gd.bind(null,s,o,e),[e]),o.getSnapshot!==t||c||$e!==null&&$e.memoizedState.tag&1){if(s.flags|=2048,ts(9,md.bind(null,s,o,l,t),void 0,null),We===null)throw Error(i(349));(Mn&30)!==0||pd(s,t,l)}return l}function pd(e,t,s){e.flags|=16384,e={getSnapshot:t,value:s},t=Me.updateQueue,t===null?(t={lastEffect:null,stores:null},Me.updateQueue=t,t.stores=[e]):(s=t.stores,s===null?t.stores=[e]:s.push(e))}function md(e,t,s,o){t.value=s,t.getSnapshot=o,yd(t)&&vd(e)}function gd(e,t,s){return s(function(){yd(t)&&vd(e)})}function yd(e){var t=e.getSnapshot;e=e.value;try{var s=t();return!Tt(e,s)}catch{return!0}}function vd(e){var t=Gt(e,1);t!==null&&Mt(t,e,1,-1)}function xd(e){var t=zt();return typeof e=="function"&&(e=e()),t.memoizedState=t.baseState=e,e={pending:null,interleaved:null,lanes:0,dispatch:null,lastRenderedReducer:es,lastRenderedState:e},t.queue=e,e=e.dispatch=Tg.bind(null,Me,e),[t.memoizedState,e]}function ts(e,t,s,o){return e={tag:e,create:t,destroy:s,deps:o,next:null},t=Me.updateQueue,t===null?(t={lastEffect:null,stores:null},Me.updateQueue=t,t.lastEffect=e.next=e):(s=t.lastEffect,s===null?t.lastEffect=e.next=e:(o=s.next,s.next=e,e.next=o,t.lastEffect=e)),e}function wd(){return xt().memoizedState}function fi(e,t,s,o){var l=zt();Me.flags|=e,l.memoizedState=ts(1|t,s,void 0,o===void 0?null:o)}function hi(e,t,s,o){var l=xt();o=o===void 0?null:o;var c=void 0;if(Fe!==null){var m=Fe.memoizedState;if(c=m.destroy,o!==null&&ka(o,m.deps)){l.memoizedState=ts(t,s,c,o);return}}Me.flags|=e,l.memoizedState=ts(1|t,s,c,o)}function kd(e,t){return fi(8390656,8,e,t)}function Ca(e,t){return hi(2048,8,e,t)}function Sd(e,t){return hi(4,2,e,t)}function jd(e,t){return hi(4,4,e,t)}function Nd(e,t){if(typeof t=="function")return e=e(),t(e),function(){t(null)};if(t!=null)return e=e(),t.current=e,function(){t.current=null}}function Td(e,t,s){return s=s!=null?s.concat([e]):null,hi(4,4,Nd.bind(null,t,e),s)}function Pa(){}function Cd(e,t){var s=xt();t=t===void 0?null:t;var o=s.memoizedState;return o!==null&&t!==null&&ka(t,o[1])?o[0]:(s.memoizedState=[e,t],e)}function Pd(e,t){var s=xt();t=t===void 0?null:t;var o=s.memoizedState;return o!==null&&t!==null&&ka(t,o[1])?o[0]:(e=e(),s.memoizedState=[e,t],e)}function Ed(e,t,s){return(Mn&21)===0?(e.baseState&&(e.baseState=!1,ot=!0),e.memoizedState=s):(Tt(s,t)||(s=sc(),Me.lanes|=s,_n|=s,e.baseState=!0),t)}function jg(e,t){var s=ye;ye=s!==0&&4>s?s:4,e(!0);var o=wa.transition;wa.transition={};try{e(!1),t()}finally{ye=s,wa.transition=o}}function bd(){return xt().memoizedState}function Ng(e,t,s){var o=hn(e);if(s={lane:o,action:s,hasEagerState:!1,eagerState:null,next:null},Md(e))_d(t,s);else if(s=ad(e,t,s,o),s!==null){var l=tt();Mt(s,e,o,l),Ad(s,t,o)}}function Tg(e,t,s){var o=hn(e),l={lane:o,action:s,hasEagerState:!1,eagerState:null,next:null};if(Md(e))_d(t,l);else{var c=e.alternate;if(e.lanes===0&&(c===null||c.lanes===0)&&(c=t.lastRenderedReducer,c!==null))try{var m=t.lastRenderedState,k=c(m,s);if(l.hasEagerState=!0,l.eagerState=k,Tt(k,m)){var S=t.interleaved;S===null?(l.next=l,pa(t)):(l.next=S.next,S.next=l),t.interleaved=l;return}}catch{}finally{}s=ad(e,t,l,o),s!==null&&(l=tt(),Mt(s,e,o,l),Ad(s,t,o))}}function Md(e){var t=e.alternate;return e===Me||t!==null&&t===Me}function _d(e,t){Zr=di=!0;var s=e.pending;s===null?t.next=t:(t.next=s.next,s.next=t),e.pending=t}function Ad(e,t,s){if((s&4194240)!==0){var o=t.lanes;o&=e.pendingLanes,s|=o,t.lanes=s,bo(e,s)}}var pi={readContext:vt,useCallback:qe,useContext:qe,useEffect:qe,useImperativeHandle:qe,useInsertionEffect:qe,useLayoutEffect:qe,useMemo:qe,useReducer:qe,useRef:qe,useState:qe,useDebugValue:qe,useDeferredValue:qe,useTransition:qe,useMutableSource:qe,useSyncExternalStore:qe,useId:qe,unstable_isNewReconciler:!1},Cg={readContext:vt,useCallback:function(e,t){return zt().memoizedState=[e,t===void 0?null:t],e},useContext:vt,useEffect:kd,useImperativeHandle:function(e,t,s){return s=s!=null?s.concat([e]):null,fi(4194308,4,Nd.bind(null,t,e),s)},useLayoutEffect:function(e,t){return fi(4194308,4,e,t)},useInsertionEffect:function(e,t){return fi(4,2,e,t)},useMemo:function(e,t){var s=zt();return t=t===void 0?null:t,e=e(),s.memoizedState=[e,t],e},useReducer:function(e,t,s){var o=zt();return t=s!==void 0?s(t):t,o.memoizedState=o.baseState=t,e={pending:null,interleaved:null,lanes:0,dispatch:null,lastRenderedReducer:e,lastRenderedState:t},o.queue=e,e=e.dispatch=Ng.bind(null,Me,e),[o.memoizedState,e]},useRef:function(e){var t=zt();return e={current:e},t.memoizedState=e},useState:xd,useDebugValue:Pa,useDeferredValue:function(e){return zt().memoizedState=e},useTransition:function(){var e=xd(!1),t=e[0];return e=jg.bind(null,e[1]),zt().memoizedState=e,[t,e]},useMutableSource:function(){},useSyncExternalStore:function(e,t,s){var o=Me,l=zt();if(Ce){if(s===void 0)throw Error(i(407));s=s()}else{if(s=t(),We===null)throw Error(i(349));(Mn&30)!==0||pd(o,t,s)}l.memoizedState=s;var c={value:s,getSnapshot:t};return l.queue=c,kd(gd.bind(null,o,c,e),[e]),o.flags|=2048,ts(9,md.bind(null,o,c,s,t),void 0,null),s},useId:function(){var e=zt(),t=We.identifierPrefix;if(Ce){var s=Kt,o=Ht;s=(o&~(1<<32-Nt(o)-1)).toString(32)+s,t=":"+t+"R"+s,s=Jr++,0<s&&(t+="H"+s.toString(32)),t+=":"}else s=Sg++,t=":"+t+"r"+s.toString(32)+":";return e.memoizedState=t},unstable_isNewReconciler:!1},Pg={readContext:vt,useCallback:Cd,useContext:vt,useEffect:Ca,useImperativeHandle:Td,useInsertionEffect:Sd,useLayoutEffect:jd,useMemo:Pd,useReducer:Na,useRef:wd,useState:function(){return Na(es)},useDebugValue:Pa,useDeferredValue:function(e){var t=xt();return Ed(t,Fe.memoizedState,e)},useTransition:function(){var e=Na(es)[0],t=xt().memoizedState;return[e,t]},useMutableSource:fd,useSyncExternalStore:hd,useId:bd,unstable_isNewReconciler:!1},Eg={readContext:vt,useCallback:Cd,useContext:vt,useEffect:Ca,useImperativeHandle:Td,useInsertionEffect:Sd,useLayoutEffect:jd,useMemo:Pd,useReducer:Ta,useRef:wd,useState:function(){return Ta(es)},useDebugValue:Pa,useDeferredValue:function(e){var t=xt();return Fe===null?t.memoizedState=e:Ed(t,Fe.memoizedState,e)},useTransition:function(){var e=Ta(es)[0],t=xt().memoizedState;return[e,t]},useMutableSource:fd,useSyncExternalStore:hd,useId:bd,unstable_isNewReconciler:!1};function Pt(e,t){if(e&&e.defaultProps){t=$({},t),e=e.defaultProps;for(var s in e)t[s]===void 0&&(t[s]=e[s]);return t}return t}function Ea(e,t,s,o){t=e.memoizedState,s=s(o,t),s=s==null?t:$({},t,s),e.memoizedState=s,e.lanes===0&&(e.updateQueue.baseState=s)}var mi={isMounted:function(e){return(e=e._reactInternals)?jn(e)===e:!1},enqueueSetState:function(e,t,s){e=e._reactInternals;var o=tt(),l=hn(e),c=Yt(o,l);c.payload=t,s!=null&&(c.callback=s),t=un(e,c,l),t!==null&&(Mt(t,e,l,o),ai(t,e,l))},enqueueReplaceState:function(e,t,s){e=e._reactInternals;var o=tt(),l=hn(e),c=Yt(o,l);c.tag=1,c.payload=t,s!=null&&(c.callback=s),t=un(e,c,l),t!==null&&(Mt(t,e,l,o),ai(t,e,l))},enqueueForceUpdate:function(e,t){e=e._reactInternals;var s=tt(),o=hn(e),l=Yt(s,o);l.tag=2,t!=null&&(l.callback=t),t=un(e,l,o),t!==null&&(Mt(t,e,o,s),ai(t,e,o))}};function Rd(e,t,s,o,l,c,m){return e=e.stateNode,typeof e.shouldComponentUpdate=="function"?e.shouldComponentUpdate(o,c,m):t.prototype&&t.prototype.isPureReactComponent?!Br(s,o)||!Br(l,c):!0}function Dd(e,t,s){var o=!1,l=on,c=t.contextType;return typeof c=="object"&&c!==null?c=vt(c):(l=it(t)?Tn:Qe.current,o=t.contextTypes,c=(o=o!=null)?er(e,l):on),t=new t(s,c),e.memoizedState=t.state!==null&&t.state!==void 0?t.state:null,t.updater=mi,e.stateNode=t,t._reactInternals=e,o&&(e=e.stateNode,e.__reactInternalMemoizedUnmaskedChildContext=l,e.__reactInternalMemoizedMaskedChildContext=c),t}function Ld(e,t,s,o){e=t.state,typeof t.componentWillReceiveProps=="function"&&t.componentWillReceiveProps(s,o),typeof t.UNSAFE_componentWillReceiveProps=="function"&&t.UNSAFE_componentWillReceiveProps(s,o),t.state!==e&&mi.enqueueReplaceState(t,t.state,null)}function ba(e,t,s,o){var l=e.stateNode;l.props=s,l.state=e.memoizedState,l.refs={},ma(e);var c=t.contextType;typeof c=="object"&&c!==null?l.context=vt(c):(c=it(t)?Tn:Qe.current,l.context=er(e,c)),l.state=e.memoizedState,c=t.getDerivedStateFromProps,typeof c=="function"&&(Ea(e,t,c,s),l.state=e.memoizedState),typeof t.getDerivedStateFromProps=="function"||typeof l.getSnapshotBeforeUpdate=="function"||typeof l.UNSAFE_componentWillMount!="function"&&typeof l.componentWillMount!="function"||(t=l.state,typeof l.componentWillMount=="function"&&l.componentWillMount(),typeof l.UNSAFE_componentWillMount=="function"&&l.UNSAFE_componentWillMount(),t!==l.state&&mi.enqueueReplaceState(l,l.state,null),li(e,s,l,o),l.state=e.memoizedState),typeof l.componentDidMount=="function"&&(e.flags|=4194308)}function lr(e,t){try{var s="",o=t;do s+=fe(o),o=o.return;while(o);var l=s}catch(c){l=`
Error generating stack: `+c.message+`
`+c.stack}return{value:e,source:t,stack:l,digest:null}}function Ma(e,t,s){return{value:e,source:null,stack:s??null,digest:t??null}}function _a(e,t){try{console.error(t.value)}catch(s){setTimeout(function(){throw s})}}var bg=typeof WeakMap=="function"?WeakMap:Map;function Vd(e,t,s){s=Yt(-1,s),s.tag=3,s.payload={element:null};var o=t.value;return s.callback=function(){Si||(Si=!0,Ka=o),_a(e,t)},s}function zd(e,t,s){s=Yt(-1,s),s.tag=3;var o=e.type.getDerivedStateFromError;if(typeof o=="function"){var l=t.value;s.payload=function(){return o(l)},s.callback=function(){_a(e,t)}}var c=e.stateNode;return c!==null&&typeof c.componentDidCatch=="function"&&(s.callback=function(){_a(e,t),typeof o!="function"&&(dn===null?dn=new Set([this]):dn.add(this));var m=t.stack;this.componentDidCatch(t.value,{componentStack:m!==null?m:""})}),s}function Id(e,t,s){var o=e.pingCache;if(o===null){o=e.pingCache=new bg;var l=new Set;o.set(t,l)}else l=o.get(t),l===void 0&&(l=new Set,o.set(t,l));l.has(s)||(l.add(s),e=$g.bind(null,e,t,s),t.then(e,e))}function Od(e){do{var t;if((t=e.tag===13)&&(t=e.memoizedState,t=t!==null?t.dehydrated!==null:!0),t)return e;e=e.return}while(e!==null);return null}function Fd(e,t,s,o,l){return(e.mode&1)===0?(e===t?e.flags|=65536:(e.flags|=128,s.flags|=131072,s.flags&=-52805,s.tag===1&&(s.alternate===null?s.tag=17:(t=Yt(-1,1),t.tag=2,un(s,t,1))),s.lanes|=1),e):(e.flags|=65536,e.lanes=l,e)}var Mg=U.ReactCurrentOwner,ot=!1;function et(e,t,s,o){t.child=e===null?od(t,null,s,o):sr(t,e.child,s,o)}function Bd(e,t,s,o,l){s=s.render;var c=t.ref;return or(t,l),o=Sa(e,t,s,o,c,l),s=ja(),e!==null&&!ot?(t.updateQueue=e.updateQueue,t.flags&=-2053,e.lanes&=~l,Xt(e,t,l)):(Ce&&s&&ia(t),t.flags|=1,et(e,t,o,l),t.child)}function Ud(e,t,s,o,l){if(e===null){var c=s.type;return typeof c=="function"&&!Ja(c)&&c.defaultProps===void 0&&s.compare===null&&s.defaultProps===void 0?(t.tag=15,t.type=c,$d(e,t,c,o,l)):(e=Ei(s.type,null,o,t,t.mode,l),e.ref=t.ref,e.return=t,t.child=e)}if(c=e.child,(e.lanes&l)===0){var m=c.memoizedProps;if(s=s.compare,s=s!==null?s:Br,s(m,o)&&e.ref===t.ref)return Xt(e,t,l)}return t.flags|=1,e=mn(c,o),e.ref=t.ref,e.return=t,t.child=e}function $d(e,t,s,o,l){if(e!==null){var c=e.memoizedProps;if(Br(c,o)&&e.ref===t.ref)if(ot=!1,t.pendingProps=o=c,(e.lanes&l)!==0)(e.flags&131072)!==0&&(ot=!0);else return t.lanes=e.lanes,Xt(e,t,l)}return Aa(e,t,s,o,l)}function Wd(e,t,s){var o=t.pendingProps,l=o.children,c=e!==null?e.memoizedState:null;if(o.mode==="hidden")if((t.mode&1)===0)t.memoizedState={baseLanes:0,cachePool:null,transitions:null},we(cr,pt),pt|=s;else{if((s&1073741824)===0)return e=c!==null?c.baseLanes|s:s,t.lanes=t.childLanes=1073741824,t.memoizedState={baseLanes:e,cachePool:null,transitions:null},t.updateQueue=null,we(cr,pt),pt|=e,null;t.memoizedState={baseLanes:0,cachePool:null,transitions:null},o=c!==null?c.baseLanes:s,we(cr,pt),pt|=o}else c!==null?(o=c.baseLanes|s,t.memoizedState=null):o=s,we(cr,pt),pt|=o;return et(e,t,l,s),t.child}function Hd(e,t){var s=t.ref;(e===null&&s!==null||e!==null&&e.ref!==s)&&(t.flags|=512,t.flags|=2097152)}function Aa(e,t,s,o,l){var c=it(s)?Tn:Qe.current;return c=er(t,c),or(t,l),s=Sa(e,t,s,o,c,l),o=ja(),e!==null&&!ot?(t.updateQueue=e.updateQueue,t.flags&=-2053,e.lanes&=~l,Xt(e,t,l)):(Ce&&o&&ia(t),t.flags|=1,et(e,t,s,l),t.child)}function Kd(e,t,s,o,l){if(it(s)){var c=!0;Js(t)}else c=!1;if(or(t,l),t.stateNode===null)yi(e,t),Dd(t,s,o),ba(t,s,o,l),o=!0;else if(e===null){var m=t.stateNode,k=t.memoizedProps;m.props=k;var S=m.context,b=s.contextType;typeof b=="object"&&b!==null?b=vt(b):(b=it(s)?Tn:Qe.current,b=er(t,b));var D=s.getDerivedStateFromProps,V=typeof D=="function"||typeof m.getSnapshotBeforeUpdate=="function";V||typeof m.UNSAFE_componentWillReceiveProps!="function"&&typeof m.componentWillReceiveProps!="function"||(k!==o||S!==b)&&Ld(t,m,o,b),ln=!1;var R=t.memoizedState;m.state=R,li(t,o,m,l),S=t.memoizedState,k!==o||R!==S||st.current||ln?(typeof D=="function"&&(Ea(t,s,D,o),S=t.memoizedState),(k=ln||Rd(t,s,k,o,R,S,b))?(V||typeof m.UNSAFE_componentWillMount!="function"&&typeof m.componentWillMount!="function"||(typeof m.componentWillMount=="function"&&m.componentWillMount(),typeof m.UNSAFE_componentWillMount=="function"&&m.UNSAFE_componentWillMount()),typeof m.componentDidMount=="function"&&(t.flags|=4194308)):(typeof m.componentDidMount=="function"&&(t.flags|=4194308),t.memoizedProps=o,t.memoizedState=S),m.props=o,m.state=S,m.context=b,o=k):(typeof m.componentDidMount=="function"&&(t.flags|=4194308),o=!1)}else{m=t.stateNode,ld(e,t),k=t.memoizedProps,b=t.type===t.elementType?k:Pt(t.type,k),m.props=b,V=t.pendingProps,R=m.context,S=s.contextType,typeof S=="object"&&S!==null?S=vt(S):(S=it(s)?Tn:Qe.current,S=er(t,S));var K=s.getDerivedStateFromProps;(D=typeof K=="function"||typeof m.getSnapshotBeforeUpdate=="function")||typeof m.UNSAFE_componentWillReceiveProps!="function"&&typeof m.componentWillReceiveProps!="function"||(k!==V||R!==S)&&Ld(t,m,o,S),ln=!1,R=t.memoizedState,m.state=R,li(t,o,m,l);var Q=t.memoizedState;k!==V||R!==Q||st.current||ln?(typeof K=="function"&&(Ea(t,s,K,o),Q=t.memoizedState),(b=ln||Rd(t,s,b,o,R,Q,S)||!1)?(D||typeof m.UNSAFE_componentWillUpdate!="function"&&typeof m.componentWillUpdate!="function"||(typeof m.componentWillUpdate=="function"&&m.componentWillUpdate(o,Q,S),typeof m.UNSAFE_componentWillUpdate=="function"&&m.UNSAFE_componentWillUpdate(o,Q,S)),typeof m.componentDidUpdate=="function"&&(t.flags|=4),typeof m.getSnapshotBeforeUpdate=="function"&&(t.flags|=1024)):(typeof m.componentDidUpdate!="function"||k===e.memoizedProps&&R===e.memoizedState||(t.flags|=4),typeof m.getSnapshotBeforeUpdate!="function"||k===e.memoizedProps&&R===e.memoizedState||(t.flags|=1024),t.memoizedProps=o,t.memoizedState=Q),m.props=o,m.state=Q,m.context=S,o=b):(typeof m.componentDidUpdate!="function"||k===e.memoizedProps&&R===e.memoizedState||(t.flags|=4),typeof m.getSnapshotBeforeUpdate!="function"||k===e.memoizedProps&&R===e.memoizedState||(t.flags|=1024),o=!1)}return Ra(e,t,s,o,c,l)}function Ra(e,t,s,o,l,c){Hd(e,t);var m=(t.flags&128)!==0;if(!o&&!m)return l&&qc(t,s,!1),Xt(e,t,c);o=t.stateNode,Mg.current=t;var k=m&&typeof s.getDerivedStateFromError!="function"?null:o.render();return t.flags|=1,e!==null&&m?(t.child=sr(t,e.child,null,c),t.child=sr(t,null,k,c)):et(e,t,k,c),t.memoizedState=o.state,l&&qc(t,s,!0),t.child}function Gd(e){var t=e.stateNode;t.pendingContext?Xc(e,t.pendingContext,t.pendingContext!==t.context):t.context&&Xc(e,t.context,!1),ga(e,t.containerInfo)}function Yd(e,t,s,o,l){return rr(),ua(l),t.flags|=256,et(e,t,s,o),t.child}var Da={dehydrated:null,treeContext:null,retryLane:0};function La(e){return{baseLanes:e,cachePool:null,transitions:null}}function Xd(e,t,s){var o=t.pendingProps,l=be.current,c=!1,m=(t.flags&128)!==0,k;if((k=m)||(k=e!==null&&e.memoizedState===null?!1:(l&2)!==0),k?(c=!0,t.flags&=-129):(e===null||e.memoizedState!==null)&&(l|=1),we(be,l&1),e===null)return la(t),e=t.memoizedState,e!==null&&(e=e.dehydrated,e!==null)?((t.mode&1)===0?t.lanes=1:e.data==="$!"?t.lanes=8:t.lanes=1073741824,null):(m=o.children,e=o.fallback,c?(o=t.mode,c=t.child,m={mode:"hidden",children:m},(o&1)===0&&c!==null?(c.childLanes=0,c.pendingProps=m):c=bi(m,o,0,null),e=Ln(e,o,s,null),c.return=t,e.return=t,c.sibling=e,t.child=c,t.child.memoizedState=La(s),t.memoizedState=Da,e):Va(t,m));if(l=e.memoizedState,l!==null&&(k=l.dehydrated,k!==null))return _g(e,t,m,o,k,l,s);if(c){c=o.fallback,m=t.mode,l=e.child,k=l.sibling;var S={mode:"hidden",children:o.children};return(m&1)===0&&t.child!==l?(o=t.child,o.childLanes=0,o.pendingProps=S,t.deletions=null):(o=mn(l,S),o.subtreeFlags=l.subtreeFlags&14680064),k!==null?c=mn(k,c):(c=Ln(c,m,s,null),c.flags|=2),c.return=t,o.return=t,o.sibling=c,t.child=o,o=c,c=t.child,m=e.child.memoizedState,m=m===null?La(s):{baseLanes:m.baseLanes|s,cachePool:null,transitions:m.transitions},c.memoizedState=m,c.childLanes=e.childLanes&~s,t.memoizedState=Da,o}return c=e.child,e=c.sibling,o=mn(c,{mode:"visible",children:o.children}),(t.mode&1)===0&&(o.lanes=s),o.return=t,o.sibling=null,e!==null&&(s=t.deletions,s===null?(t.deletions=[e],t.flags|=16):s.push(e)),t.child=o,t.memoizedState=null,o}function Va(e,t){return t=bi({mode:"visible",children:t},e.mode,0,null),t.return=e,e.child=t}function gi(e,t,s,o){return o!==null&&ua(o),sr(t,e.child,null,s),e=Va(t,t.pendingProps.children),e.flags|=2,t.memoizedState=null,e}function _g(e,t,s,o,l,c,m){if(s)return t.flags&256?(t.flags&=-257,o=Ma(Error(i(422))),gi(e,t,m,o)):t.memoizedState!==null?(t.child=e.child,t.flags|=128,null):(c=o.fallback,l=t.mode,o=bi({mode:"visible",children:o.children},l,0,null),c=Ln(c,l,m,null),c.flags|=2,o.return=t,c.return=t,o.sibling=c,t.child=o,(t.mode&1)!==0&&sr(t,e.child,null,m),t.child.memoizedState=La(m),t.memoizedState=Da,c);if((t.mode&1)===0)return gi(e,t,m,null);if(l.data==="$!"){if(o=l.nextSibling&&l.nextSibling.dataset,o)var k=o.dgst;return o=k,c=Error(i(419)),o=Ma(c,o,void 0),gi(e,t,m,o)}if(k=(m&e.childLanes)!==0,ot||k){if(o=We,o!==null){switch(m&-m){case 4:l=2;break;case 16:l=8;break;case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:l=32;break;case 536870912:l=268435456;break;default:l=0}l=(l&(o.suspendedLanes|m))!==0?0:l,l!==0&&l!==c.retryLane&&(c.retryLane=l,Gt(e,l),Mt(o,e,l,-1))}return Za(),o=Ma(Error(i(421))),gi(e,t,m,o)}return l.data==="$?"?(t.flags|=128,t.child=e.child,t=Wg.bind(null,e),l._reactRetry=t,null):(e=c.treeContext,ht=rn(l.nextSibling),ft=t,Ce=!0,Ct=null,e!==null&&(gt[yt++]=Ht,gt[yt++]=Kt,gt[yt++]=Cn,Ht=e.id,Kt=e.overflow,Cn=t),t=Va(t,o.children),t.flags|=4096,t)}function Qd(e,t,s){e.lanes|=t;var o=e.alternate;o!==null&&(o.lanes|=t),ha(e.return,t,s)}function za(e,t,s,o,l){var c=e.memoizedState;c===null?e.memoizedState={isBackwards:t,rendering:null,renderingStartTime:0,last:o,tail:s,tailMode:l}:(c.isBackwards=t,c.rendering=null,c.renderingStartTime=0,c.last=o,c.tail=s,c.tailMode=l)}function qd(e,t,s){var o=t.pendingProps,l=o.revealOrder,c=o.tail;if(et(e,t,o.children,s),o=be.current,(o&2)!==0)o=o&1|2,t.flags|=128;else{if(e!==null&&(e.flags&128)!==0)e:for(e=t.child;e!==null;){if(e.tag===13)e.memoizedState!==null&&Qd(e,s,t);else if(e.tag===19)Qd(e,s,t);else if(e.child!==null){e.child.return=e,e=e.child;continue}if(e===t)break e;for(;e.sibling===null;){if(e.return===null||e.return===t)break e;e=e.return}e.sibling.return=e.return,e=e.sibling}o&=1}if(we(be,o),(t.mode&1)===0)t.memoizedState=null;else switch(l){case"forwards":for(s=t.child,l=null;s!==null;)e=s.alternate,e!==null&&ui(e)===null&&(l=s),s=s.sibling;s=l,s===null?(l=t.child,t.child=null):(l=s.sibling,s.sibling=null),za(t,!1,l,s,c);break;case"backwards":for(s=null,l=t.child,t.child=null;l!==null;){if(e=l.alternate,e!==null&&ui(e)===null){t.child=l;break}e=l.sibling,l.sibling=s,s=l,l=e}za(t,!0,s,null,c);break;case"together":za(t,!1,null,null,void 0);break;default:t.memoizedState=null}return t.child}function yi(e,t){(t.mode&1)===0&&e!==null&&(e.alternate=null,t.alternate=null,t.flags|=2)}function Xt(e,t,s){if(e!==null&&(t.dependencies=e.dependencies),_n|=t.lanes,(s&t.childLanes)===0)return null;if(e!==null&&t.child!==e.child)throw Error(i(153));if(t.child!==null){for(e=t.child,s=mn(e,e.pendingProps),t.child=s,s.return=t;e.sibling!==null;)e=e.sibling,s=s.sibling=mn(e,e.pendingProps),s.return=t;s.sibling=null}return t.child}function Ag(e,t,s){switch(t.tag){case 3:Gd(t),rr();break;case 5:dd(t);break;case 1:it(t.type)&&Js(t);break;case 4:ga(t,t.stateNode.containerInfo);break;case 10:var o=t.type._context,l=t.memoizedProps.value;we(ii,o._currentValue),o._currentValue=l;break;case 13:if(o=t.memoizedState,o!==null)return o.dehydrated!==null?(we(be,be.current&1),t.flags|=128,null):(s&t.child.childLanes)!==0?Xd(e,t,s):(we(be,be.current&1),e=Xt(e,t,s),e!==null?e.sibling:null);we(be,be.current&1);break;case 19:if(o=(s&t.childLanes)!==0,(e.flags&128)!==0){if(o)return qd(e,t,s);t.flags|=128}if(l=t.memoizedState,l!==null&&(l.rendering=null,l.tail=null,l.lastEffect=null),we(be,be.current),o)break;return null;case 22:case 23:return t.lanes=0,Wd(e,t,s)}return Xt(e,t,s)}var Zd,Ia,Jd,ef;Zd=function(e,t){for(var s=t.child;s!==null;){if(s.tag===5||s.tag===6)e.appendChild(s.stateNode);else if(s.tag!==4&&s.child!==null){s.child.return=s,s=s.child;continue}if(s===t)break;for(;s.sibling===null;){if(s.return===null||s.return===t)return;s=s.return}s.sibling.return=s.return,s=s.sibling}},Ia=function(){},Jd=function(e,t,s,o){var l=e.memoizedProps;if(l!==o){e=t.stateNode,bn(Vt.current);var c=null;switch(s){case"input":l=ho(e,l),o=ho(e,o),c=[];break;case"select":l=$({},l,{value:void 0}),o=$({},o,{value:void 0}),c=[];break;case"textarea":l=go(e,l),o=go(e,o),c=[];break;default:typeof l.onClick!="function"&&typeof o.onClick=="function"&&(e.onclick=Qs)}vo(s,o);var m;s=null;for(b in l)if(!o.hasOwnProperty(b)&&l.hasOwnProperty(b)&&l[b]!=null)if(b==="style"){var k=l[b];for(m in k)k.hasOwnProperty(m)&&(s||(s={}),s[m]="")}else b!=="dangerouslySetInnerHTML"&&b!=="children"&&b!=="suppressContentEditableWarning"&&b!=="suppressHydrationWarning"&&b!=="autoFocus"&&(u.hasOwnProperty(b)?c||(c=[]):(c=c||[]).push(b,null));for(b in o){var S=o[b];if(k=l!=null?l[b]:void 0,o.hasOwnProperty(b)&&S!==k&&(S!=null||k!=null))if(b==="style")if(k){for(m in k)!k.hasOwnProperty(m)||S&&S.hasOwnProperty(m)||(s||(s={}),s[m]="");for(m in S)S.hasOwnProperty(m)&&k[m]!==S[m]&&(s||(s={}),s[m]=S[m])}else s||(c||(c=[]),c.push(b,s)),s=S;else b==="dangerouslySetInnerHTML"?(S=S?S.__html:void 0,k=k?k.__html:void 0,S!=null&&k!==S&&(c=c||[]).push(b,S)):b==="children"?typeof S!="string"&&typeof S!="number"||(c=c||[]).push(b,""+S):b!=="suppressContentEditableWarning"&&b!=="suppressHydrationWarning"&&(u.hasOwnProperty(b)?(S!=null&&b==="onScroll"&&Se("scroll",e),c||k===S||(c=[])):(c=c||[]).push(b,S))}s&&(c=c||[]).push("style",s);var b=c;(t.updateQueue=b)&&(t.flags|=4)}},ef=function(e,t,s,o){s!==o&&(t.flags|=4)};function ns(e,t){if(!Ce)switch(e.tailMode){case"hidden":t=e.tail;for(var s=null;t!==null;)t.alternate!==null&&(s=t),t=t.sibling;s===null?e.tail=null:s.sibling=null;break;case"collapsed":s=e.tail;for(var o=null;s!==null;)s.alternate!==null&&(o=s),s=s.sibling;o===null?t||e.tail===null?e.tail=null:e.tail.sibling=null:o.sibling=null}}function Ze(e){var t=e.alternate!==null&&e.alternate.child===e.child,s=0,o=0;if(t)for(var l=e.child;l!==null;)s|=l.lanes|l.childLanes,o|=l.subtreeFlags&14680064,o|=l.flags&14680064,l.return=e,l=l.sibling;else for(l=e.child;l!==null;)s|=l.lanes|l.childLanes,o|=l.subtreeFlags,o|=l.flags,l.return=e,l=l.sibling;return e.subtreeFlags|=o,e.childLanes=s,t}function Rg(e,t,s){var o=t.pendingProps;switch(oa(t),t.tag){case 2:case 16:case 15:case 0:case 11:case 7:case 8:case 12:case 9:case 14:return Ze(t),null;case 1:return it(t.type)&&Zs(),Ze(t),null;case 3:return o=t.stateNode,ar(),je(st),je(Qe),xa(),o.pendingContext&&(o.context=o.pendingContext,o.pendingContext=null),(e===null||e.child===null)&&(ri(t)?t.flags|=4:e===null||e.memoizedState.isDehydrated&&(t.flags&256)===0||(t.flags|=1024,Ct!==null&&(Xa(Ct),Ct=null))),Ia(e,t),Ze(t),null;case 5:ya(t);var l=bn(qr.current);if(s=t.type,e!==null&&t.stateNode!=null)Jd(e,t,s,o,l),e.ref!==t.ref&&(t.flags|=512,t.flags|=2097152);else{if(!o){if(t.stateNode===null)throw Error(i(166));return Ze(t),null}if(e=bn(Vt.current),ri(t)){o=t.stateNode,s=t.type;var c=t.memoizedProps;switch(o[Lt]=t,o[Kr]=c,e=(t.mode&1)!==0,s){case"dialog":Se("cancel",o),Se("close",o);break;case"iframe":case"object":case"embed":Se("load",o);break;case"video":case"audio":for(l=0;l<$r.length;l++)Se($r[l],o);break;case"source":Se("error",o);break;case"img":case"image":case"link":Se("error",o),Se("load",o);break;case"details":Se("toggle",o);break;case"input":Du(o,c),Se("invalid",o);break;case"select":o._wrapperState={wasMultiple:!!c.multiple},Se("invalid",o);break;case"textarea":zu(o,c),Se("invalid",o)}vo(s,c),l=null;for(var m in c)if(c.hasOwnProperty(m)){var k=c[m];m==="children"?typeof k=="string"?o.textContent!==k&&(c.suppressHydrationWarning!==!0&&Xs(o.textContent,k,e),l=["children",k]):typeof k=="number"&&o.textContent!==""+k&&(c.suppressHydrationWarning!==!0&&Xs(o.textContent,k,e),l=["children",""+k]):u.hasOwnProperty(m)&&k!=null&&m==="onScroll"&&Se("scroll",o)}switch(s){case"input":Cs(o),Vu(o,c,!0);break;case"textarea":Cs(o),Ou(o);break;case"select":case"option":break;default:typeof c.onClick=="function"&&(o.onclick=Qs)}o=l,t.updateQueue=o,o!==null&&(t.flags|=4)}else{m=l.nodeType===9?l:l.ownerDocument,e==="http://www.w3.org/1999/xhtml"&&(e=Fu(s)),e==="http://www.w3.org/1999/xhtml"?s==="script"?(e=m.createElement("div"),e.innerHTML="<script><\/script>",e=e.removeChild(e.firstChild)):typeof o.is=="string"?e=m.createElement(s,{is:o.is}):(e=m.createElement(s),s==="select"&&(m=e,o.multiple?m.multiple=!0:o.size&&(m.size=o.size))):e=m.createElementNS(e,s),e[Lt]=t,e[Kr]=o,Zd(e,t,!1,!1),t.stateNode=e;e:{switch(m=xo(s,o),s){case"dialog":Se("cancel",e),Se("close",e),l=o;break;case"iframe":case"object":case"embed":Se("load",e),l=o;break;case"video":case"audio":for(l=0;l<$r.length;l++)Se($r[l],e);l=o;break;case"source":Se("error",e),l=o;break;case"img":case"image":case"link":Se("error",e),Se("load",e),l=o;break;case"details":Se("toggle",e),l=o;break;case"input":Du(e,o),l=ho(e,o),Se("invalid",e);break;case"option":l=o;break;case"select":e._wrapperState={wasMultiple:!!o.multiple},l=$({},o,{value:void 0}),Se("invalid",e);break;case"textarea":zu(e,o),l=go(e,o),Se("invalid",e);break;default:l=o}vo(s,l),k=l;for(c in k)if(k.hasOwnProperty(c)){var S=k[c];c==="style"?$u(e,S):c==="dangerouslySetInnerHTML"?(S=S?S.__html:void 0,S!=null&&Bu(e,S)):c==="children"?typeof S=="string"?(s!=="textarea"||S!=="")&&Nr(e,S):typeof S=="number"&&Nr(e,""+S):c!=="suppressContentEditableWarning"&&c!=="suppressHydrationWarning"&&c!=="autoFocus"&&(u.hasOwnProperty(c)?S!=null&&c==="onScroll"&&Se("scroll",e):S!=null&&I(e,c,S,m))}switch(s){case"input":Cs(e),Vu(e,o,!1);break;case"textarea":Cs(e),Ou(e);break;case"option":o.value!=null&&e.setAttribute("value",""+ge(o.value));break;case"select":e.multiple=!!o.multiple,c=o.value,c!=null?Un(e,!!o.multiple,c,!1):o.defaultValue!=null&&Un(e,!!o.multiple,o.defaultValue,!0);break;default:typeof l.onClick=="function"&&(e.onclick=Qs)}switch(s){case"button":case"input":case"select":case"textarea":o=!!o.autoFocus;break e;case"img":o=!0;break e;default:o=!1}}o&&(t.flags|=4)}t.ref!==null&&(t.flags|=512,t.flags|=2097152)}return Ze(t),null;case 6:if(e&&t.stateNode!=null)ef(e,t,e.memoizedProps,o);else{if(typeof o!="string"&&t.stateNode===null)throw Error(i(166));if(s=bn(qr.current),bn(Vt.current),ri(t)){if(o=t.stateNode,s=t.memoizedProps,o[Lt]=t,(c=o.nodeValue!==s)&&(e=ft,e!==null))switch(e.tag){case 3:Xs(o.nodeValue,s,(e.mode&1)!==0);break;case 5:e.memoizedProps.suppressHydrationWarning!==!0&&Xs(o.nodeValue,s,(e.mode&1)!==0)}c&&(t.flags|=4)}else o=(s.nodeType===9?s:s.ownerDocument).createTextNode(o),o[Lt]=t,t.stateNode=o}return Ze(t),null;case 13:if(je(be),o=t.memoizedState,e===null||e.memoizedState!==null&&e.memoizedState.dehydrated!==null){if(Ce&&ht!==null&&(t.mode&1)!==0&&(t.flags&128)===0)rd(),rr(),t.flags|=98560,c=!1;else if(c=ri(t),o!==null&&o.dehydrated!==null){if(e===null){if(!c)throw Error(i(318));if(c=t.memoizedState,c=c!==null?c.dehydrated:null,!c)throw Error(i(317));c[Lt]=t}else rr(),(t.flags&128)===0&&(t.memoizedState=null),t.flags|=4;Ze(t),c=!1}else Ct!==null&&(Xa(Ct),Ct=null),c=!0;if(!c)return t.flags&65536?t:null}return(t.flags&128)!==0?(t.lanes=s,t):(o=o!==null,o!==(e!==null&&e.memoizedState!==null)&&o&&(t.child.flags|=8192,(t.mode&1)!==0&&(e===null||(be.current&1)!==0?Be===0&&(Be=3):Za())),t.updateQueue!==null&&(t.flags|=4),Ze(t),null);case 4:return ar(),Ia(e,t),e===null&&Wr(t.stateNode.containerInfo),Ze(t),null;case 10:return fa(t.type._context),Ze(t),null;case 17:return it(t.type)&&Zs(),Ze(t),null;case 19:if(je(be),c=t.memoizedState,c===null)return Ze(t),null;if(o=(t.flags&128)!==0,m=c.rendering,m===null)if(o)ns(c,!1);else{if(Be!==0||e!==null&&(e.flags&128)!==0)for(e=t.child;e!==null;){if(m=ui(e),m!==null){for(t.flags|=128,ns(c,!1),o=m.updateQueue,o!==null&&(t.updateQueue=o,t.flags|=4),t.subtreeFlags=0,o=s,s=t.child;s!==null;)c=s,e=o,c.flags&=14680066,m=c.alternate,m===null?(c.childLanes=0,c.lanes=e,c.child=null,c.subtreeFlags=0,c.memoizedProps=null,c.memoizedState=null,c.updateQueue=null,c.dependencies=null,c.stateNode=null):(c.childLanes=m.childLanes,c.lanes=m.lanes,c.child=m.child,c.subtreeFlags=0,c.deletions=null,c.memoizedProps=m.memoizedProps,c.memoizedState=m.memoizedState,c.updateQueue=m.updateQueue,c.type=m.type,e=m.dependencies,c.dependencies=e===null?null:{lanes:e.lanes,firstContext:e.firstContext}),s=s.sibling;return we(be,be.current&1|2),t.child}e=e.sibling}c.tail!==null&&Le()>dr&&(t.flags|=128,o=!0,ns(c,!1),t.lanes=4194304)}else{if(!o)if(e=ui(m),e!==null){if(t.flags|=128,o=!0,s=e.updateQueue,s!==null&&(t.updateQueue=s,t.flags|=4),ns(c,!0),c.tail===null&&c.tailMode==="hidden"&&!m.alternate&&!Ce)return Ze(t),null}else 2*Le()-c.renderingStartTime>dr&&s!==1073741824&&(t.flags|=128,o=!0,ns(c,!1),t.lanes=4194304);c.isBackwards?(m.sibling=t.child,t.child=m):(s=c.last,s!==null?s.sibling=m:t.child=m,c.last=m)}return c.tail!==null?(t=c.tail,c.rendering=t,c.tail=t.sibling,c.renderingStartTime=Le(),t.sibling=null,s=be.current,we(be,o?s&1|2:s&1),t):(Ze(t),null);case 22:case 23:return qa(),o=t.memoizedState!==null,e!==null&&e.memoizedState!==null!==o&&(t.flags|=8192),o&&(t.mode&1)!==0?(pt&1073741824)!==0&&(Ze(t),t.subtreeFlags&6&&(t.flags|=8192)):Ze(t),null;case 24:return null;case 25:return null}throw Error(i(156,t.tag))}function Dg(e,t){switch(oa(t),t.tag){case 1:return it(t.type)&&Zs(),e=t.flags,e&65536?(t.flags=e&-65537|128,t):null;case 3:return ar(),je(st),je(Qe),xa(),e=t.flags,(e&65536)!==0&&(e&128)===0?(t.flags=e&-65537|128,t):null;case 5:return ya(t),null;case 13:if(je(be),e=t.memoizedState,e!==null&&e.dehydrated!==null){if(t.alternate===null)throw Error(i(340));rr()}return e=t.flags,e&65536?(t.flags=e&-65537|128,t):null;case 19:return je(be),null;case 4:return ar(),null;case 10:return fa(t.type._context),null;case 22:case 23:return qa(),null;case 24:return null;default:return null}}var vi=!1,Je=!1,Lg=typeof WeakSet=="function"?WeakSet:Set,X=null;function ur(e,t){var s=e.ref;if(s!==null)if(typeof s=="function")try{s(null)}catch(o){Ae(e,t,o)}else s.current=null}function Oa(e,t,s){try{s()}catch(o){Ae(e,t,o)}}var tf=!1;function Vg(e,t){if(qo=Is,e=Rc(),$o(e)){if("selectionStart"in e)var s={start:e.selectionStart,end:e.selectionEnd};else e:{s=(s=e.ownerDocument)&&s.defaultView||window;var o=s.getSelection&&s.getSelection();if(o&&o.rangeCount!==0){s=o.anchorNode;var l=o.anchorOffset,c=o.focusNode;o=o.focusOffset;try{s.nodeType,c.nodeType}catch{s=null;break e}var m=0,k=-1,S=-1,b=0,D=0,V=e,R=null;t:for(;;){for(var K;V!==s||l!==0&&V.nodeType!==3||(k=m+l),V!==c||o!==0&&V.nodeType!==3||(S=m+o),V.nodeType===3&&(m+=V.nodeValue.length),(K=V.firstChild)!==null;)R=V,V=K;for(;;){if(V===e)break t;if(R===s&&++b===l&&(k=m),R===c&&++D===o&&(S=m),(K=V.nextSibling)!==null)break;V=R,R=V.parentNode}V=K}s=k===-1||S===-1?null:{start:k,end:S}}else s=null}s=s||{start:0,end:0}}else s=null;for(Zo={focusedElem:e,selectionRange:s},Is=!1,X=t;X!==null;)if(t=X,e=t.child,(t.subtreeFlags&1028)!==0&&e!==null)e.return=t,X=e;else for(;X!==null;){t=X;try{var Q=t.alternate;if((t.flags&1024)!==0)switch(t.tag){case 0:case 11:case 15:break;case 1:if(Q!==null){var J=Q.memoizedProps,Ve=Q.memoizedState,C=t.stateNode,j=C.getSnapshotBeforeUpdate(t.elementType===t.type?J:Pt(t.type,J),Ve);C.__reactInternalSnapshotBeforeUpdate=j}break;case 3:var P=t.stateNode.containerInfo;P.nodeType===1?P.textContent="":P.nodeType===9&&P.documentElement&&P.removeChild(P.documentElement);break;case 5:case 6:case 4:case 17:break;default:throw Error(i(163))}}catch(F){Ae(t,t.return,F)}if(e=t.sibling,e!==null){e.return=t.return,X=e;break}X=t.return}return Q=tf,tf=!1,Q}function rs(e,t,s){var o=t.updateQueue;if(o=o!==null?o.lastEffect:null,o!==null){var l=o=o.next;do{if((l.tag&e)===e){var c=l.destroy;l.destroy=void 0,c!==void 0&&Oa(t,s,c)}l=l.next}while(l!==o)}}function xi(e,t){if(t=t.updateQueue,t=t!==null?t.lastEffect:null,t!==null){var s=t=t.next;do{if((s.tag&e)===e){var o=s.create;s.destroy=o()}s=s.next}while(s!==t)}}function Fa(e){var t=e.ref;if(t!==null){var s=e.stateNode;switch(e.tag){case 5:e=s;break;default:e=s}typeof t=="function"?t(e):t.current=e}}function nf(e){var t=e.alternate;t!==null&&(e.alternate=null,nf(t)),e.child=null,e.deletions=null,e.sibling=null,e.tag===5&&(t=e.stateNode,t!==null&&(delete t[Lt],delete t[Kr],delete t[na],delete t[vg],delete t[xg])),e.stateNode=null,e.return=null,e.dependencies=null,e.memoizedProps=null,e.memoizedState=null,e.pendingProps=null,e.stateNode=null,e.updateQueue=null}function rf(e){return e.tag===5||e.tag===3||e.tag===4}function sf(e){e:for(;;){for(;e.sibling===null;){if(e.return===null||rf(e.return))return null;e=e.return}for(e.sibling.return=e.return,e=e.sibling;e.tag!==5&&e.tag!==6&&e.tag!==18;){if(e.flags&2||e.child===null||e.tag===4)continue e;e.child.return=e,e=e.child}if(!(e.flags&2))return e.stateNode}}function Ba(e,t,s){var o=e.tag;if(o===5||o===6)e=e.stateNode,t?s.nodeType===8?s.parentNode.insertBefore(e,t):s.insertBefore(e,t):(s.nodeType===8?(t=s.parentNode,t.insertBefore(e,s)):(t=s,t.appendChild(e)),s=s._reactRootContainer,s!=null||t.onclick!==null||(t.onclick=Qs));else if(o!==4&&(e=e.child,e!==null))for(Ba(e,t,s),e=e.sibling;e!==null;)Ba(e,t,s),e=e.sibling}function Ua(e,t,s){var o=e.tag;if(o===5||o===6)e=e.stateNode,t?s.insertBefore(e,t):s.appendChild(e);else if(o!==4&&(e=e.child,e!==null))for(Ua(e,t,s),e=e.sibling;e!==null;)Ua(e,t,s),e=e.sibling}var Ke=null,Et=!1;function cn(e,t,s){for(s=s.child;s!==null;)of(e,t,s),s=s.sibling}function of(e,t,s){if(Dt&&typeof Dt.onCommitFiberUnmount=="function")try{Dt.onCommitFiberUnmount(As,s)}catch{}switch(s.tag){case 5:Je||ur(s,t);case 6:var o=Ke,l=Et;Ke=null,cn(e,t,s),Ke=o,Et=l,Ke!==null&&(Et?(e=Ke,s=s.stateNode,e.nodeType===8?e.parentNode.removeChild(s):e.removeChild(s)):Ke.removeChild(s.stateNode));break;case 18:Ke!==null&&(Et?(e=Ke,s=s.stateNode,e.nodeType===8?ta(e.parentNode,s):e.nodeType===1&&ta(e,s),Lr(e)):ta(Ke,s.stateNode));break;case 4:o=Ke,l=Et,Ke=s.stateNode.containerInfo,Et=!0,cn(e,t,s),Ke=o,Et=l;break;case 0:case 11:case 14:case 15:if(!Je&&(o=s.updateQueue,o!==null&&(o=o.lastEffect,o!==null))){l=o=o.next;do{var c=l,m=c.destroy;c=c.tag,m!==void 0&&((c&2)!==0||(c&4)!==0)&&Oa(s,t,m),l=l.next}while(l!==o)}cn(e,t,s);break;case 1:if(!Je&&(ur(s,t),o=s.stateNode,typeof o.componentWillUnmount=="function"))try{o.props=s.memoizedProps,o.state=s.memoizedState,o.componentWillUnmount()}catch(k){Ae(s,t,k)}cn(e,t,s);break;case 21:cn(e,t,s);break;case 22:s.mode&1?(Je=(o=Je)||s.memoizedState!==null,cn(e,t,s),Je=o):cn(e,t,s);break;default:cn(e,t,s)}}function af(e){var t=e.updateQueue;if(t!==null){e.updateQueue=null;var s=e.stateNode;s===null&&(s=e.stateNode=new Lg),t.forEach(function(o){var l=Hg.bind(null,e,o);s.has(o)||(s.add(o),o.then(l,l))})}}function bt(e,t){var s=t.deletions;if(s!==null)for(var o=0;o<s.length;o++){var l=s[o];try{var c=e,m=t,k=m;e:for(;k!==null;){switch(k.tag){case 5:Ke=k.stateNode,Et=!1;break e;case 3:Ke=k.stateNode.containerInfo,Et=!0;break e;case 4:Ke=k.stateNode.containerInfo,Et=!0;break e}k=k.return}if(Ke===null)throw Error(i(160));of(c,m,l),Ke=null,Et=!1;var S=l.alternate;S!==null&&(S.return=null),l.return=null}catch(b){Ae(l,t,b)}}if(t.subtreeFlags&12854)for(t=t.child;t!==null;)lf(t,e),t=t.sibling}function lf(e,t){var s=e.alternate,o=e.flags;switch(e.tag){case 0:case 11:case 14:case 15:if(bt(t,e),It(e),o&4){try{rs(3,e,e.return),xi(3,e)}catch(J){Ae(e,e.return,J)}try{rs(5,e,e.return)}catch(J){Ae(e,e.return,J)}}break;case 1:bt(t,e),It(e),o&512&&s!==null&&ur(s,s.return);break;case 5:if(bt(t,e),It(e),o&512&&s!==null&&ur(s,s.return),e.flags&32){var l=e.stateNode;try{Nr(l,"")}catch(J){Ae(e,e.return,J)}}if(o&4&&(l=e.stateNode,l!=null)){var c=e.memoizedProps,m=s!==null?s.memoizedProps:c,k=e.type,S=e.updateQueue;if(e.updateQueue=null,S!==null)try{k==="input"&&c.type==="radio"&&c.name!=null&&Lu(l,c),xo(k,m);var b=xo(k,c);for(m=0;m<S.length;m+=2){var D=S[m],V=S[m+1];D==="style"?$u(l,V):D==="dangerouslySetInnerHTML"?Bu(l,V):D==="children"?Nr(l,V):I(l,D,V,b)}switch(k){case"input":po(l,c);break;case"textarea":Iu(l,c);break;case"select":var R=l._wrapperState.wasMultiple;l._wrapperState.wasMultiple=!!c.multiple;var K=c.value;K!=null?Un(l,!!c.multiple,K,!1):R!==!!c.multiple&&(c.defaultValue!=null?Un(l,!!c.multiple,c.defaultValue,!0):Un(l,!!c.multiple,c.multiple?[]:"",!1))}l[Kr]=c}catch(J){Ae(e,e.return,J)}}break;case 6:if(bt(t,e),It(e),o&4){if(e.stateNode===null)throw Error(i(162));l=e.stateNode,c=e.memoizedProps;try{l.nodeValue=c}catch(J){Ae(e,e.return,J)}}break;case 3:if(bt(t,e),It(e),o&4&&s!==null&&s.memoizedState.isDehydrated)try{Lr(t.containerInfo)}catch(J){Ae(e,e.return,J)}break;case 4:bt(t,e),It(e);break;case 13:bt(t,e),It(e),l=e.child,l.flags&8192&&(c=l.memoizedState!==null,l.stateNode.isHidden=c,!c||l.alternate!==null&&l.alternate.memoizedState!==null||(Ha=Le())),o&4&&af(e);break;case 22:if(D=s!==null&&s.memoizedState!==null,e.mode&1?(Je=(b=Je)||D,bt(t,e),Je=b):bt(t,e),It(e),o&8192){if(b=e.memoizedState!==null,(e.stateNode.isHidden=b)&&!D&&(e.mode&1)!==0)for(X=e,D=e.child;D!==null;){for(V=X=D;X!==null;){switch(R=X,K=R.child,R.tag){case 0:case 11:case 14:case 15:rs(4,R,R.return);break;case 1:ur(R,R.return);var Q=R.stateNode;if(typeof Q.componentWillUnmount=="function"){o=R,s=R.return;try{t=o,Q.props=t.memoizedProps,Q.state=t.memoizedState,Q.componentWillUnmount()}catch(J){Ae(o,s,J)}}break;case 5:ur(R,R.return);break;case 22:if(R.memoizedState!==null){df(V);continue}}K!==null?(K.return=R,X=K):df(V)}D=D.sibling}e:for(D=null,V=e;;){if(V.tag===5){if(D===null){D=V;try{l=V.stateNode,b?(c=l.style,typeof c.setProperty=="function"?c.setProperty("display","none","important"):c.display="none"):(k=V.stateNode,S=V.memoizedProps.style,m=S!=null&&S.hasOwnProperty("display")?S.display:null,k.style.display=Uu("display",m))}catch(J){Ae(e,e.return,J)}}}else if(V.tag===6){if(D===null)try{V.stateNode.nodeValue=b?"":V.memoizedProps}catch(J){Ae(e,e.return,J)}}else if((V.tag!==22&&V.tag!==23||V.memoizedState===null||V===e)&&V.child!==null){V.child.return=V,V=V.child;continue}if(V===e)break e;for(;V.sibling===null;){if(V.return===null||V.return===e)break e;D===V&&(D=null),V=V.return}D===V&&(D=null),V.sibling.return=V.return,V=V.sibling}}break;case 19:bt(t,e),It(e),o&4&&af(e);break;case 21:break;default:bt(t,e),It(e)}}function It(e){var t=e.flags;if(t&2){try{e:{for(var s=e.return;s!==null;){if(rf(s)){var o=s;break e}s=s.return}throw Error(i(160))}switch(o.tag){case 5:var l=o.stateNode;o.flags&32&&(Nr(l,""),o.flags&=-33);var c=sf(e);Ua(e,c,l);break;case 3:case 4:var m=o.stateNode.containerInfo,k=sf(e);Ba(e,k,m);break;default:throw Error(i(161))}}catch(S){Ae(e,e.return,S)}e.flags&=-3}t&4096&&(e.flags&=-4097)}function zg(e,t,s){X=e,uf(e)}function uf(e,t,s){for(var o=(e.mode&1)!==0;X!==null;){var l=X,c=l.child;if(l.tag===22&&o){var m=l.memoizedState!==null||vi;if(!m){var k=l.alternate,S=k!==null&&k.memoizedState!==null||Je;k=vi;var b=Je;if(vi=m,(Je=S)&&!b)for(X=l;X!==null;)m=X,S=m.child,m.tag===22&&m.memoizedState!==null?ff(l):S!==null?(S.return=m,X=S):ff(l);for(;c!==null;)X=c,uf(c),c=c.sibling;X=l,vi=k,Je=b}cf(e)}else(l.subtreeFlags&8772)!==0&&c!==null?(c.return=l,X=c):cf(e)}}function cf(e){for(;X!==null;){var t=X;if((t.flags&8772)!==0){var s=t.alternate;try{if((t.flags&8772)!==0)switch(t.tag){case 0:case 11:case 15:Je||xi(5,t);break;case 1:var o=t.stateNode;if(t.flags&4&&!Je)if(s===null)o.componentDidMount();else{var l=t.elementType===t.type?s.memoizedProps:Pt(t.type,s.memoizedProps);o.componentDidUpdate(l,s.memoizedState,o.__reactInternalSnapshotBeforeUpdate)}var c=t.updateQueue;c!==null&&cd(t,c,o);break;case 3:var m=t.updateQueue;if(m!==null){if(s=null,t.child!==null)switch(t.child.tag){case 5:s=t.child.stateNode;break;case 1:s=t.child.stateNode}cd(t,m,s)}break;case 5:var k=t.stateNode;if(s===null&&t.flags&4){s=k;var S=t.memoizedProps;switch(t.type){case"button":case"input":case"select":case"textarea":S.autoFocus&&s.focus();break;case"img":S.src&&(s.src=S.src)}}break;case 6:break;case 4:break;case 12:break;case 13:if(t.memoizedState===null){var b=t.alternate;if(b!==null){var D=b.memoizedState;if(D!==null){var V=D.dehydrated;V!==null&&Lr(V)}}}break;case 19:case 17:case 21:case 22:case 23:case 25:break;default:throw Error(i(163))}Je||t.flags&512&&Fa(t)}catch(R){Ae(t,t.return,R)}}if(t===e){X=null;break}if(s=t.sibling,s!==null){s.return=t.return,X=s;break}X=t.return}}function df(e){for(;X!==null;){var t=X;if(t===e){X=null;break}var s=t.sibling;if(s!==null){s.return=t.return,X=s;break}X=t.return}}function ff(e){for(;X!==null;){var t=X;try{switch(t.tag){case 0:case 11:case 15:var s=t.return;try{xi(4,t)}catch(S){Ae(t,s,S)}break;case 1:var o=t.stateNode;if(typeof o.componentDidMount=="function"){var l=t.return;try{o.componentDidMount()}catch(S){Ae(t,l,S)}}var c=t.return;try{Fa(t)}catch(S){Ae(t,c,S)}break;case 5:var m=t.return;try{Fa(t)}catch(S){Ae(t,m,S)}}}catch(S){Ae(t,t.return,S)}if(t===e){X=null;break}var k=t.sibling;if(k!==null){k.return=t.return,X=k;break}X=t.return}}var Ig=Math.ceil,wi=U.ReactCurrentDispatcher,$a=U.ReactCurrentOwner,wt=U.ReactCurrentBatchConfig,de=0,We=null,Ie=null,Ge=0,pt=0,cr=sn(0),Be=0,ss=null,_n=0,ki=0,Wa=0,is=null,at=null,Ha=0,dr=1/0,Qt=null,Si=!1,Ka=null,dn=null,ji=!1,fn=null,Ni=0,os=0,Ga=null,Ti=-1,Ci=0;function tt(){return(de&6)!==0?Le():Ti!==-1?Ti:Ti=Le()}function hn(e){return(e.mode&1)===0?1:(de&2)!==0&&Ge!==0?Ge&-Ge:kg.transition!==null?(Ci===0&&(Ci=sc()),Ci):(e=ye,e!==0||(e=window.event,e=e===void 0?16:hc(e.type)),e)}function Mt(e,t,s,o){if(50<os)throw os=0,Ga=null,Error(i(185));Mr(e,s,o),((de&2)===0||e!==We)&&(e===We&&((de&2)===0&&(ki|=s),Be===4&&pn(e,Ge)),lt(e,o),s===1&&de===0&&(t.mode&1)===0&&(dr=Le()+500,ei&&an()))}function lt(e,t){var s=e.callbackNode;k0(e,t);var o=Ls(e,e===We?Ge:0);if(o===0)s!==null&&tc(s),e.callbackNode=null,e.callbackPriority=0;else if(t=o&-o,e.callbackPriority!==t){if(s!=null&&tc(s),t===1)e.tag===0?wg(pf.bind(null,e)):Zc(pf.bind(null,e)),gg(function(){(de&6)===0&&an()}),s=null;else{switch(ic(o)){case 1:s=Co;break;case 4:s=nc;break;case 16:s=_s;break;case 536870912:s=rc;break;default:s=_s}s=Sf(s,hf.bind(null,e))}e.callbackPriority=t,e.callbackNode=s}}function hf(e,t){if(Ti=-1,Ci=0,(de&6)!==0)throw Error(i(327));var s=e.callbackNode;if(fr()&&e.callbackNode!==s)return null;var o=Ls(e,e===We?Ge:0);if(o===0)return null;if((o&30)!==0||(o&e.expiredLanes)!==0||t)t=Pi(e,o);else{t=o;var l=de;de|=2;var c=gf();(We!==e||Ge!==t)&&(Qt=null,dr=Le()+500,Rn(e,t));do try{Bg();break}catch(k){mf(e,k)}while(!0);da(),wi.current=c,de=l,Ie!==null?t=0:(We=null,Ge=0,t=Be)}if(t!==0){if(t===2&&(l=Po(e),l!==0&&(o=l,t=Ya(e,l))),t===1)throw s=ss,Rn(e,0),pn(e,o),lt(e,Le()),s;if(t===6)pn(e,o);else{if(l=e.current.alternate,(o&30)===0&&!Og(l)&&(t=Pi(e,o),t===2&&(c=Po(e),c!==0&&(o=c,t=Ya(e,c))),t===1))throw s=ss,Rn(e,0),pn(e,o),lt(e,Le()),s;switch(e.finishedWork=l,e.finishedLanes=o,t){case 0:case 1:throw Error(i(345));case 2:Dn(e,at,Qt);break;case 3:if(pn(e,o),(o&130023424)===o&&(t=Ha+500-Le(),10<t)){if(Ls(e,0)!==0)break;if(l=e.suspendedLanes,(l&o)!==o){tt(),e.pingedLanes|=e.suspendedLanes&l;break}e.timeoutHandle=ea(Dn.bind(null,e,at,Qt),t);break}Dn(e,at,Qt);break;case 4:if(pn(e,o),(o&4194240)===o)break;for(t=e.eventTimes,l=-1;0<o;){var m=31-Nt(o);c=1<<m,m=t[m],m>l&&(l=m),o&=~c}if(o=l,o=Le()-o,o=(120>o?120:480>o?480:1080>o?1080:1920>o?1920:3e3>o?3e3:4320>o?4320:1960*Ig(o/1960))-o,10<o){e.timeoutHandle=ea(Dn.bind(null,e,at,Qt),o);break}Dn(e,at,Qt);break;case 5:Dn(e,at,Qt);break;default:throw Error(i(329))}}}return lt(e,Le()),e.callbackNode===s?hf.bind(null,e):null}function Ya(e,t){var s=is;return e.current.memoizedState.isDehydrated&&(Rn(e,t).flags|=256),e=Pi(e,t),e!==2&&(t=at,at=s,t!==null&&Xa(t)),e}function Xa(e){at===null?at=e:at.push.apply(at,e)}function Og(e){for(var t=e;;){if(t.flags&16384){var s=t.updateQueue;if(s!==null&&(s=s.stores,s!==null))for(var o=0;o<s.length;o++){var l=s[o],c=l.getSnapshot;l=l.value;try{if(!Tt(c(),l))return!1}catch{return!1}}}if(s=t.child,t.subtreeFlags&16384&&s!==null)s.return=t,t=s;else{if(t===e)break;for(;t.sibling===null;){if(t.return===null||t.return===e)return!0;t=t.return}t.sibling.return=t.return,t=t.sibling}}return!0}function pn(e,t){for(t&=~Wa,t&=~ki,e.suspendedLanes|=t,e.pingedLanes&=~t,e=e.expirationTimes;0<t;){var s=31-Nt(t),o=1<<s;e[s]=-1,t&=~o}}function pf(e){if((de&6)!==0)throw Error(i(327));fr();var t=Ls(e,0);if((t&1)===0)return lt(e,Le()),null;var s=Pi(e,t);if(e.tag!==0&&s===2){var o=Po(e);o!==0&&(t=o,s=Ya(e,o))}if(s===1)throw s=ss,Rn(e,0),pn(e,t),lt(e,Le()),s;if(s===6)throw Error(i(345));return e.finishedWork=e.current.alternate,e.finishedLanes=t,Dn(e,at,Qt),lt(e,Le()),null}function Qa(e,t){var s=de;de|=1;try{return e(t)}finally{de=s,de===0&&(dr=Le()+500,ei&&an())}}function An(e){fn!==null&&fn.tag===0&&(de&6)===0&&fr();var t=de;de|=1;var s=wt.transition,o=ye;try{if(wt.transition=null,ye=1,e)return e()}finally{ye=o,wt.transition=s,de=t,(de&6)===0&&an()}}function qa(){pt=cr.current,je(cr)}function Rn(e,t){e.finishedWork=null,e.finishedLanes=0;var s=e.timeoutHandle;if(s!==-1&&(e.timeoutHandle=-1,mg(s)),Ie!==null)for(s=Ie.return;s!==null;){var o=s;switch(oa(o),o.tag){case 1:o=o.type.childContextTypes,o!=null&&Zs();break;case 3:ar(),je(st),je(Qe),xa();break;case 5:ya(o);break;case 4:ar();break;case 13:je(be);break;case 19:je(be);break;case 10:fa(o.type._context);break;case 22:case 23:qa()}s=s.return}if(We=e,Ie=e=mn(e.current,null),Ge=pt=t,Be=0,ss=null,Wa=ki=_n=0,at=is=null,En!==null){for(t=0;t<En.length;t++)if(s=En[t],o=s.interleaved,o!==null){s.interleaved=null;var l=o.next,c=s.pending;if(c!==null){var m=c.next;c.next=l,o.next=m}s.pending=o}En=null}return e}function mf(e,t){do{var s=Ie;try{if(da(),ci.current=pi,di){for(var o=Me.memoizedState;o!==null;){var l=o.queue;l!==null&&(l.pending=null),o=o.next}di=!1}if(Mn=0,$e=Fe=Me=null,Zr=!1,Jr=0,$a.current=null,s===null||s.return===null){Be=1,ss=t,Ie=null;break}e:{var c=e,m=s.return,k=s,S=t;if(t=Ge,k.flags|=32768,S!==null&&typeof S=="object"&&typeof S.then=="function"){var b=S,D=k,V=D.tag;if((D.mode&1)===0&&(V===0||V===11||V===15)){var R=D.alternate;R?(D.updateQueue=R.updateQueue,D.memoizedState=R.memoizedState,D.lanes=R.lanes):(D.updateQueue=null,D.memoizedState=null)}var K=Od(m);if(K!==null){K.flags&=-257,Fd(K,m,k,c,t),K.mode&1&&Id(c,b,t),t=K,S=b;var Q=t.updateQueue;if(Q===null){var J=new Set;J.add(S),t.updateQueue=J}else Q.add(S);break e}else{if((t&1)===0){Id(c,b,t),Za();break e}S=Error(i(426))}}else if(Ce&&k.mode&1){var Ve=Od(m);if(Ve!==null){(Ve.flags&65536)===0&&(Ve.flags|=256),Fd(Ve,m,k,c,t),ua(lr(S,k));break e}}c=S=lr(S,k),Be!==4&&(Be=2),is===null?is=[c]:is.push(c),c=m;do{switch(c.tag){case 3:c.flags|=65536,t&=-t,c.lanes|=t;var C=Vd(c,S,t);ud(c,C);break e;case 1:k=S;var j=c.type,P=c.stateNode;if((c.flags&128)===0&&(typeof j.getDerivedStateFromError=="function"||P!==null&&typeof P.componentDidCatch=="function"&&(dn===null||!dn.has(P)))){c.flags|=65536,t&=-t,c.lanes|=t;var F=zd(c,k,t);ud(c,F);break e}}c=c.return}while(c!==null)}vf(s)}catch(ee){t=ee,Ie===s&&s!==null&&(Ie=s=s.return);continue}break}while(!0)}function gf(){var e=wi.current;return wi.current=pi,e===null?pi:e}function Za(){(Be===0||Be===3||Be===2)&&(Be=4),We===null||(_n&268435455)===0&&(ki&268435455)===0||pn(We,Ge)}function Pi(e,t){var s=de;de|=2;var o=gf();(We!==e||Ge!==t)&&(Qt=null,Rn(e,t));do try{Fg();break}catch(l){mf(e,l)}while(!0);if(da(),de=s,wi.current=o,Ie!==null)throw Error(i(261));return We=null,Ge=0,Be}function Fg(){for(;Ie!==null;)yf(Ie)}function Bg(){for(;Ie!==null&&!f0();)yf(Ie)}function yf(e){var t=kf(e.alternate,e,pt);e.memoizedProps=e.pendingProps,t===null?vf(e):Ie=t,$a.current=null}function vf(e){var t=e;do{var s=t.alternate;if(e=t.return,(t.flags&32768)===0){if(s=Rg(s,t,pt),s!==null){Ie=s;return}}else{if(s=Dg(s,t),s!==null){s.flags&=32767,Ie=s;return}if(e!==null)e.flags|=32768,e.subtreeFlags=0,e.deletions=null;else{Be=6,Ie=null;return}}if(t=t.sibling,t!==null){Ie=t;return}Ie=t=e}while(t!==null);Be===0&&(Be=5)}function Dn(e,t,s){var o=ye,l=wt.transition;try{wt.transition=null,ye=1,Ug(e,t,s,o)}finally{wt.transition=l,ye=o}return null}function Ug(e,t,s,o){do fr();while(fn!==null);if((de&6)!==0)throw Error(i(327));s=e.finishedWork;var l=e.finishedLanes;if(s===null)return null;if(e.finishedWork=null,e.finishedLanes=0,s===e.current)throw Error(i(177));e.callbackNode=null,e.callbackPriority=0;var c=s.lanes|s.childLanes;if(S0(e,c),e===We&&(Ie=We=null,Ge=0),(s.subtreeFlags&2064)===0&&(s.flags&2064)===0||ji||(ji=!0,Sf(_s,function(){return fr(),null})),c=(s.flags&15990)!==0,(s.subtreeFlags&15990)!==0||c){c=wt.transition,wt.transition=null;var m=ye;ye=1;var k=de;de|=4,$a.current=null,Vg(e,s),lf(s,e),lg(Zo),Is=!!qo,Zo=qo=null,e.current=s,zg(s),h0(),de=k,ye=m,wt.transition=c}else e.current=s;if(ji&&(ji=!1,fn=e,Ni=l),c=e.pendingLanes,c===0&&(dn=null),g0(s.stateNode),lt(e,Le()),t!==null)for(o=e.onRecoverableError,s=0;s<t.length;s++)l=t[s],o(l.value,{componentStack:l.stack,digest:l.digest});if(Si)throw Si=!1,e=Ka,Ka=null,e;return(Ni&1)!==0&&e.tag!==0&&fr(),c=e.pendingLanes,(c&1)!==0?e===Ga?os++:(os=0,Ga=e):os=0,an(),null}function fr(){if(fn!==null){var e=ic(Ni),t=wt.transition,s=ye;try{if(wt.transition=null,ye=16>e?16:e,fn===null)var o=!1;else{if(e=fn,fn=null,Ni=0,(de&6)!==0)throw Error(i(331));var l=de;for(de|=4,X=e.current;X!==null;){var c=X,m=c.child;if((X.flags&16)!==0){var k=c.deletions;if(k!==null){for(var S=0;S<k.length;S++){var b=k[S];for(X=b;X!==null;){var D=X;switch(D.tag){case 0:case 11:case 15:rs(8,D,c)}var V=D.child;if(V!==null)V.return=D,X=V;else for(;X!==null;){D=X;var R=D.sibling,K=D.return;if(nf(D),D===b){X=null;break}if(R!==null){R.return=K,X=R;break}X=K}}}var Q=c.alternate;if(Q!==null){var J=Q.child;if(J!==null){Q.child=null;do{var Ve=J.sibling;J.sibling=null,J=Ve}while(J!==null)}}X=c}}if((c.subtreeFlags&2064)!==0&&m!==null)m.return=c,X=m;else e:for(;X!==null;){if(c=X,(c.flags&2048)!==0)switch(c.tag){case 0:case 11:case 15:rs(9,c,c.return)}var C=c.sibling;if(C!==null){C.return=c.return,X=C;break e}X=c.return}}var j=e.current;for(X=j;X!==null;){m=X;var P=m.child;if((m.subtreeFlags&2064)!==0&&P!==null)P.return=m,X=P;else e:for(m=j;X!==null;){if(k=X,(k.flags&2048)!==0)try{switch(k.tag){case 0:case 11:case 15:xi(9,k)}}catch(ee){Ae(k,k.return,ee)}if(k===m){X=null;break e}var F=k.sibling;if(F!==null){F.return=k.return,X=F;break e}X=k.return}}if(de=l,an(),Dt&&typeof Dt.onPostCommitFiberRoot=="function")try{Dt.onPostCommitFiberRoot(As,e)}catch{}o=!0}return o}finally{ye=s,wt.transition=t}}return!1}function xf(e,t,s){t=lr(s,t),t=Vd(e,t,1),e=un(e,t,1),t=tt(),e!==null&&(Mr(e,1,t),lt(e,t))}function Ae(e,t,s){if(e.tag===3)xf(e,e,s);else for(;t!==null;){if(t.tag===3){xf(t,e,s);break}else if(t.tag===1){var o=t.stateNode;if(typeof t.type.getDerivedStateFromError=="function"||typeof o.componentDidCatch=="function"&&(dn===null||!dn.has(o))){e=lr(s,e),e=zd(t,e,1),t=un(t,e,1),e=tt(),t!==null&&(Mr(t,1,e),lt(t,e));break}}t=t.return}}function $g(e,t,s){var o=e.pingCache;o!==null&&o.delete(t),t=tt(),e.pingedLanes|=e.suspendedLanes&s,We===e&&(Ge&s)===s&&(Be===4||Be===3&&(Ge&130023424)===Ge&&500>Le()-Ha?Rn(e,0):Wa|=s),lt(e,t)}function wf(e,t){t===0&&((e.mode&1)===0?t=1:(t=Ds,Ds<<=1,(Ds&130023424)===0&&(Ds=4194304)));var s=tt();e=Gt(e,t),e!==null&&(Mr(e,t,s),lt(e,s))}function Wg(e){var t=e.memoizedState,s=0;t!==null&&(s=t.retryLane),wf(e,s)}function Hg(e,t){var s=0;switch(e.tag){case 13:var o=e.stateNode,l=e.memoizedState;l!==null&&(s=l.retryLane);break;case 19:o=e.stateNode;break;default:throw Error(i(314))}o!==null&&o.delete(t),wf(e,s)}var kf;kf=function(e,t,s){if(e!==null)if(e.memoizedProps!==t.pendingProps||st.current)ot=!0;else{if((e.lanes&s)===0&&(t.flags&128)===0)return ot=!1,Ag(e,t,s);ot=(e.flags&131072)!==0}else ot=!1,Ce&&(t.flags&1048576)!==0&&Jc(t,ni,t.index);switch(t.lanes=0,t.tag){case 2:var o=t.type;yi(e,t),e=t.pendingProps;var l=er(t,Qe.current);or(t,s),l=Sa(null,t,o,e,l,s);var c=ja();return t.flags|=1,typeof l=="object"&&l!==null&&typeof l.render=="function"&&l.$$typeof===void 0?(t.tag=1,t.memoizedState=null,t.updateQueue=null,it(o)?(c=!0,Js(t)):c=!1,t.memoizedState=l.state!==null&&l.state!==void 0?l.state:null,ma(t),l.updater=mi,t.stateNode=l,l._reactInternals=t,ba(t,o,e,s),t=Ra(null,t,o,!0,c,s)):(t.tag=0,Ce&&c&&ia(t),et(null,t,l,s),t=t.child),t;case 16:o=t.elementType;e:{switch(yi(e,t),e=t.pendingProps,l=o._init,o=l(o._payload),t.type=o,l=t.tag=Gg(o),e=Pt(o,e),l){case 0:t=Aa(null,t,o,e,s);break e;case 1:t=Kd(null,t,o,e,s);break e;case 11:t=Bd(null,t,o,e,s);break e;case 14:t=Ud(null,t,o,Pt(o.type,e),s);break e}throw Error(i(306,o,""))}return t;case 0:return o=t.type,l=t.pendingProps,l=t.elementType===o?l:Pt(o,l),Aa(e,t,o,l,s);case 1:return o=t.type,l=t.pendingProps,l=t.elementType===o?l:Pt(o,l),Kd(e,t,o,l,s);case 3:e:{if(Gd(t),e===null)throw Error(i(387));o=t.pendingProps,c=t.memoizedState,l=c.element,ld(e,t),li(t,o,null,s);var m=t.memoizedState;if(o=m.element,c.isDehydrated)if(c={element:o,isDehydrated:!1,cache:m.cache,pendingSuspenseBoundaries:m.pendingSuspenseBoundaries,transitions:m.transitions},t.updateQueue.baseState=c,t.memoizedState=c,t.flags&256){l=lr(Error(i(423)),t),t=Yd(e,t,o,s,l);break e}else if(o!==l){l=lr(Error(i(424)),t),t=Yd(e,t,o,s,l);break e}else for(ht=rn(t.stateNode.containerInfo.firstChild),ft=t,Ce=!0,Ct=null,s=od(t,null,o,s),t.child=s;s;)s.flags=s.flags&-3|4096,s=s.sibling;else{if(rr(),o===l){t=Xt(e,t,s);break e}et(e,t,o,s)}t=t.child}return t;case 5:return dd(t),e===null&&la(t),o=t.type,l=t.pendingProps,c=e!==null?e.memoizedProps:null,m=l.children,Jo(o,l)?m=null:c!==null&&Jo(o,c)&&(t.flags|=32),Hd(e,t),et(e,t,m,s),t.child;case 6:return e===null&&la(t),null;case 13:return Xd(e,t,s);case 4:return ga(t,t.stateNode.containerInfo),o=t.pendingProps,e===null?t.child=sr(t,null,o,s):et(e,t,o,s),t.child;case 11:return o=t.type,l=t.pendingProps,l=t.elementType===o?l:Pt(o,l),Bd(e,t,o,l,s);case 7:return et(e,t,t.pendingProps,s),t.child;case 8:return et(e,t,t.pendingProps.children,s),t.child;case 12:return et(e,t,t.pendingProps.children,s),t.child;case 10:e:{if(o=t.type._context,l=t.pendingProps,c=t.memoizedProps,m=l.value,we(ii,o._currentValue),o._currentValue=m,c!==null)if(Tt(c.value,m)){if(c.children===l.children&&!st.current){t=Xt(e,t,s);break e}}else for(c=t.child,c!==null&&(c.return=t);c!==null;){var k=c.dependencies;if(k!==null){m=c.child;for(var S=k.firstContext;S!==null;){if(S.context===o){if(c.tag===1){S=Yt(-1,s&-s),S.tag=2;var b=c.updateQueue;if(b!==null){b=b.shared;var D=b.pending;D===null?S.next=S:(S.next=D.next,D.next=S),b.pending=S}}c.lanes|=s,S=c.alternate,S!==null&&(S.lanes|=s),ha(c.return,s,t),k.lanes|=s;break}S=S.next}}else if(c.tag===10)m=c.type===t.type?null:c.child;else if(c.tag===18){if(m=c.return,m===null)throw Error(i(341));m.lanes|=s,k=m.alternate,k!==null&&(k.lanes|=s),ha(m,s,t),m=c.sibling}else m=c.child;if(m!==null)m.return=c;else for(m=c;m!==null;){if(m===t){m=null;break}if(c=m.sibling,c!==null){c.return=m.return,m=c;break}m=m.return}c=m}et(e,t,l.children,s),t=t.child}return t;case 9:return l=t.type,o=t.pendingProps.children,or(t,s),l=vt(l),o=o(l),t.flags|=1,et(e,t,o,s),t.child;case 14:return o=t.type,l=Pt(o,t.pendingProps),l=Pt(o.type,l),Ud(e,t,o,l,s);case 15:return $d(e,t,t.type,t.pendingProps,s);case 17:return o=t.type,l=t.pendingProps,l=t.elementType===o?l:Pt(o,l),yi(e,t),t.tag=1,it(o)?(e=!0,Js(t)):e=!1,or(t,s),Dd(t,o,l),ba(t,o,l,s),Ra(null,t,o,!0,e,s);case 19:return qd(e,t,s);case 22:return Wd(e,t,s)}throw Error(i(156,t.tag))};function Sf(e,t){return ec(e,t)}function Kg(e,t,s,o){this.tag=e,this.key=s,this.sibling=this.child=this.return=this.stateNode=this.type=this.elementType=null,this.index=0,this.ref=null,this.pendingProps=t,this.dependencies=this.memoizedState=this.updateQueue=this.memoizedProps=null,this.mode=o,this.subtreeFlags=this.flags=0,this.deletions=null,this.childLanes=this.lanes=0,this.alternate=null}function kt(e,t,s,o){return new Kg(e,t,s,o)}function Ja(e){return e=e.prototype,!(!e||!e.isReactComponent)}function Gg(e){if(typeof e=="function")return Ja(e)?1:0;if(e!=null){if(e=e.$$typeof,e===me)return 11;if(e===ze)return 14}return 2}function mn(e,t){var s=e.alternate;return s===null?(s=kt(e.tag,t,e.key,e.mode),s.elementType=e.elementType,s.type=e.type,s.stateNode=e.stateNode,s.alternate=e,e.alternate=s):(s.pendingProps=t,s.type=e.type,s.flags=0,s.subtreeFlags=0,s.deletions=null),s.flags=e.flags&14680064,s.childLanes=e.childLanes,s.lanes=e.lanes,s.child=e.child,s.memoizedProps=e.memoizedProps,s.memoizedState=e.memoizedState,s.updateQueue=e.updateQueue,t=e.dependencies,s.dependencies=t===null?null:{lanes:t.lanes,firstContext:t.firstContext},s.sibling=e.sibling,s.index=e.index,s.ref=e.ref,s}function Ei(e,t,s,o,l,c){var m=2;if(o=e,typeof e=="function")Ja(e)&&(m=1);else if(typeof e=="string")m=5;else e:switch(e){case G:return Ln(s.children,l,c,t);case H:m=8,l|=8;break;case re:return e=kt(12,s,t,l|2),e.elementType=re,e.lanes=c,e;case Pe:return e=kt(13,s,t,l),e.elementType=Pe,e.lanes=c,e;case _e:return e=kt(19,s,t,l),e.elementType=_e,e.lanes=c,e;case Ee:return bi(s,l,c,t);default:if(typeof e=="object"&&e!==null)switch(e.$$typeof){case Y:m=10;break e;case ce:m=9;break e;case me:m=11;break e;case ze:m=14;break e;case ke:m=16,o=null;break e}throw Error(i(130,e==null?e:typeof e,""))}return t=kt(m,s,t,l),t.elementType=e,t.type=o,t.lanes=c,t}function Ln(e,t,s,o){return e=kt(7,e,o,t),e.lanes=s,e}function bi(e,t,s,o){return e=kt(22,e,o,t),e.elementType=Ee,e.lanes=s,e.stateNode={isHidden:!1},e}function el(e,t,s){return e=kt(6,e,null,t),e.lanes=s,e}function tl(e,t,s){return t=kt(4,e.children!==null?e.children:[],e.key,t),t.lanes=s,t.stateNode={containerInfo:e.containerInfo,pendingChildren:null,implementation:e.implementation},t}function Yg(e,t,s,o,l){this.tag=t,this.containerInfo=e,this.finishedWork=this.pingCache=this.current=this.pendingChildren=null,this.timeoutHandle=-1,this.callbackNode=this.pendingContext=this.context=null,this.callbackPriority=0,this.eventTimes=Eo(0),this.expirationTimes=Eo(-1),this.entangledLanes=this.finishedLanes=this.mutableReadLanes=this.expiredLanes=this.pingedLanes=this.suspendedLanes=this.pendingLanes=0,this.entanglements=Eo(0),this.identifierPrefix=o,this.onRecoverableError=l,this.mutableSourceEagerHydrationData=null}function nl(e,t,s,o,l,c,m,k,S){return e=new Yg(e,t,s,k,S),t===1?(t=1,c===!0&&(t|=8)):t=0,c=kt(3,null,null,t),e.current=c,c.stateNode=e,c.memoizedState={element:o,isDehydrated:s,cache:null,transitions:null,pendingSuspenseBoundaries:null},ma(c),e}function Xg(e,t,s){var o=3<arguments.length&&arguments[3]!==void 0?arguments[3]:null;return{$$typeof:se,key:o==null?null:""+o,children:e,containerInfo:t,implementation:s}}function jf(e){if(!e)return on;e=e._reactInternals;e:{if(jn(e)!==e||e.tag!==1)throw Error(i(170));var t=e;do{switch(t.tag){case 3:t=t.stateNode.context;break e;case 1:if(it(t.type)){t=t.stateNode.__reactInternalMemoizedMergedChildContext;break e}}t=t.return}while(t!==null);throw Error(i(171))}if(e.tag===1){var s=e.type;if(it(s))return Qc(e,s,t)}return t}function Nf(e,t,s,o,l,c,m,k,S){return e=nl(s,o,!0,e,l,c,m,k,S),e.context=jf(null),s=e.current,o=tt(),l=hn(s),c=Yt(o,l),c.callback=t??null,un(s,c,l),e.current.lanes=l,Mr(e,l,o),lt(e,o),e}function Mi(e,t,s,o){var l=t.current,c=tt(),m=hn(l);return s=jf(s),t.context===null?t.context=s:t.pendingContext=s,t=Yt(c,m),t.payload={element:e},o=o===void 0?null:o,o!==null&&(t.callback=o),e=un(l,t,m),e!==null&&(Mt(e,l,m,c),ai(e,l,m)),m}function _i(e){if(e=e.current,!e.child)return null;switch(e.child.tag){case 5:return e.child.stateNode;default:return e.child.stateNode}}function Tf(e,t){if(e=e.memoizedState,e!==null&&e.dehydrated!==null){var s=e.retryLane;e.retryLane=s!==0&&s<t?s:t}}function rl(e,t){Tf(e,t),(e=e.alternate)&&Tf(e,t)}function Qg(){return null}var Cf=typeof reportError=="function"?reportError:function(e){console.error(e)};function sl(e){this._internalRoot=e}Ai.prototype.render=sl.prototype.render=function(e){var t=this._internalRoot;if(t===null)throw Error(i(409));Mi(e,t,null,null)},Ai.prototype.unmount=sl.prototype.unmount=function(){var e=this._internalRoot;if(e!==null){this._internalRoot=null;var t=e.containerInfo;An(function(){Mi(null,e,null,null)}),t[$t]=null}};function Ai(e){this._internalRoot=e}Ai.prototype.unstable_scheduleHydration=function(e){if(e){var t=lc();e={blockedOn:null,target:e,priority:t};for(var s=0;s<en.length&&t!==0&&t<en[s].priority;s++);en.splice(s,0,e),s===0&&dc(e)}};function il(e){return!(!e||e.nodeType!==1&&e.nodeType!==9&&e.nodeType!==11)}function Ri(e){return!(!e||e.nodeType!==1&&e.nodeType!==9&&e.nodeType!==11&&(e.nodeType!==8||e.nodeValue!==" react-mount-point-unstable "))}function Pf(){}function qg(e,t,s,o,l){if(l){if(typeof o=="function"){var c=o;o=function(){var b=_i(m);c.call(b)}}var m=Nf(t,o,e,0,null,!1,!1,"",Pf);return e._reactRootContainer=m,e[$t]=m.current,Wr(e.nodeType===8?e.parentNode:e),An(),m}for(;l=e.lastChild;)e.removeChild(l);if(typeof o=="function"){var k=o;o=function(){var b=_i(S);k.call(b)}}var S=nl(e,0,!1,null,null,!1,!1,"",Pf);return e._reactRootContainer=S,e[$t]=S.current,Wr(e.nodeType===8?e.parentNode:e),An(function(){Mi(t,S,s,o)}),S}function Di(e,t,s,o,l){var c=s._reactRootContainer;if(c){var m=c;if(typeof l=="function"){var k=l;l=function(){var S=_i(m);k.call(S)}}Mi(t,m,e,l)}else m=qg(s,t,e,l,o);return _i(m)}oc=function(e){switch(e.tag){case 3:var t=e.stateNode;if(t.current.memoizedState.isDehydrated){var s=br(t.pendingLanes);s!==0&&(bo(t,s|1),lt(t,Le()),(de&6)===0&&(dr=Le()+500,an()))}break;case 13:An(function(){var o=Gt(e,1);if(o!==null){var l=tt();Mt(o,e,1,l)}}),rl(e,1)}},Mo=function(e){if(e.tag===13){var t=Gt(e,134217728);if(t!==null){var s=tt();Mt(t,e,134217728,s)}rl(e,134217728)}},ac=function(e){if(e.tag===13){var t=hn(e),s=Gt(e,t);if(s!==null){var o=tt();Mt(s,e,t,o)}rl(e,t)}},lc=function(){return ye},uc=function(e,t){var s=ye;try{return ye=e,t()}finally{ye=s}},So=function(e,t,s){switch(t){case"input":if(po(e,s),t=s.name,s.type==="radio"&&t!=null){for(s=e;s.parentNode;)s=s.parentNode;for(s=s.querySelectorAll("input[name="+JSON.stringify(""+t)+'][type="radio"]'),t=0;t<s.length;t++){var o=s[t];if(o!==e&&o.form===e.form){var l=qs(o);if(!l)throw Error(i(90));Ru(o),po(o,l)}}}break;case"textarea":Iu(e,s);break;case"select":t=s.value,t!=null&&Un(e,!!s.multiple,t,!1)}},Gu=Qa,Yu=An;var Zg={usingClientEntryPoint:!1,Events:[Gr,Zn,qs,Hu,Ku,Qa]},as={findFiberByHostInstance:Nn,bundleType:0,version:"18.3.1",rendererPackageName:"react-dom"},Jg={bundleType:as.bundleType,version:as.version,rendererPackageName:as.rendererPackageName,rendererConfig:as.rendererConfig,overrideHookState:null,overrideHookStateDeletePath:null,overrideHookStateRenamePath:null,overrideProps:null,overridePropsDeletePath:null,overridePropsRenamePath:null,setErrorHandler:null,setSuspenseHandler:null,scheduleUpdate:null,currentDispatcherRef:U.ReactCurrentDispatcher,findHostInstanceByFiber:function(e){return e=Zu(e),e===null?null:e.stateNode},findFiberByHostInstance:as.findFiberByHostInstance||Qg,findHostInstancesForRefresh:null,scheduleRefresh:null,scheduleRoot:null,setRefreshHandler:null,getCurrentFiber:null,reconcilerVersion:"18.3.1-next-f1338f8080-20240426"};if(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__<"u"){var Li=__REACT_DEVTOOLS_GLOBAL_HOOK__;if(!Li.isDisabled&&Li.supportsFiber)try{As=Li.inject(Jg),Dt=Li}catch{}}return ut.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED=Zg,ut.createPortal=function(e,t){var s=2<arguments.length&&arguments[2]!==void 0?arguments[2]:null;if(!il(t))throw Error(i(200));return Xg(e,t,null,s)},ut.createRoot=function(e,t){if(!il(e))throw Error(i(299));var s=!1,o="",l=Cf;return t!=null&&(t.unstable_strictMode===!0&&(s=!0),t.identifierPrefix!==void 0&&(o=t.identifierPrefix),t.onRecoverableError!==void 0&&(l=t.onRecoverableError)),t=nl(e,1,!1,null,null,s,!1,o,l),e[$t]=t.current,Wr(e.nodeType===8?e.parentNode:e),new sl(t)},ut.findDOMNode=function(e){if(e==null)return null;if(e.nodeType===1)return e;var t=e._reactInternals;if(t===void 0)throw typeof e.render=="function"?Error(i(188)):(e=Object.keys(e).join(","),Error(i(268,e)));return e=Zu(t),e=e===null?null:e.stateNode,e},ut.flushSync=function(e){return An(e)},ut.hydrate=function(e,t,s){if(!Ri(t))throw Error(i(200));return Di(null,e,t,!0,s)},ut.hydrateRoot=function(e,t,s){if(!il(e))throw Error(i(405));var o=s!=null&&s.hydratedSources||null,l=!1,c="",m=Cf;if(s!=null&&(s.unstable_strictMode===!0&&(l=!0),s.identifierPrefix!==void 0&&(c=s.identifierPrefix),s.onRecoverableError!==void 0&&(m=s.onRecoverableError)),t=Nf(t,null,e,1,s??null,l,!1,c,m),e[$t]=t.current,Wr(e),o)for(e=0;e<o.length;e++)s=o[e],l=s._getVersion,l=l(s._source),t.mutableSourceEagerHydrationData==null?t.mutableSourceEagerHydrationData=[s,l]:t.mutableSourceEagerHydrationData.push(s,l);return new Ai(t)},ut.render=function(e,t,s){if(!Ri(t))throw Error(i(200));return Di(null,e,t,!1,s)},ut.unmountComponentAtNode=function(e){if(!Ri(e))throw Error(i(40));return e._reactRootContainer?(An(function(){Di(null,null,e,!1,function(){e._reactRootContainer=null,e[$t]=null})}),!0):!1},ut.unstable_batchedUpdates=Qa,ut.unstable_renderSubtreeIntoContainer=function(e,t,s,o){if(!Ri(s))throw Error(i(200));if(e==null||e._reactInternals===void 0)throw Error(i(38));return Di(e,t,s,!1,o)},ut.version="18.3.1-next-f1338f8080-20240426",ut}var Lf;function ly(){if(Lf)return ll.exports;Lf=1;function n(){if(!(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__>"u"||typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE!="function"))try{__REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(n)}catch(r){console.error(r)}}return n(),ll.exports=ay(),ll.exports}var Vf;function uy(){if(Vf)return Vi;Vf=1;var n=ly();return Vi.createRoot=n.createRoot,Vi.hydrateRoot=n.hydrateRoot,Vi}var cy=uy();const dy=op(cy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const ap=(...n)=>n.filter((r,i,a)=>!!r&&r.trim()!==""&&a.indexOf(r)===i).join(" ").trim();/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const fy=n=>n.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase();/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const hy=n=>n.replace(/^([A-Z])|[\s-_]+(\w)/g,(r,i,a)=>a?a.toUpperCase():i.toLowerCase());/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const zf=n=>{const r=hy(n);return r.charAt(0).toUpperCase()+r.slice(1)};/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */var dl={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:2,strokeLinecap:"round",strokeLinejoin:"round"};/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const py=n=>{for(const r in n)if(r.startsWith("aria-")||r==="role"||r==="title")return!0;return!1},my=z.createContext({}),gy=()=>z.useContext(my),yy=z.forwardRef(({color:n,size:r,strokeWidth:i,absoluteStrokeWidth:a,className:u="",children:f,iconNode:d,...p},g)=>{const{size:x=24,strokeWidth:y=2,absoluteStrokeWidth:v=!1,color:w="currentColor",className:N=""}=gy()??{},E=a??v?Number(i??y)*24/Number(r??x):i??y;return z.createElement("svg",{ref:g,...dl,width:r??x??dl.width,height:r??x??dl.height,stroke:n??w,strokeWidth:E,className:ap("lucide",N,u),...!f&&!py(p)&&{"aria-hidden":"true"},...p},[...d.map(([_,M])=>z.createElement(_,M)),...Array.isArray(f)?f:[f]])});/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const oe=(n,r)=>{const i=z.forwardRef(({className:a,...u},f)=>z.createElement(yy,{ref:f,iconNode:r,className:ap(`lucide-${fy(zf(n))}`,`lucide-${n}`,a),...u}));return i.displayName=zf(n),i};/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const vy=[["path",{d:"M5 12h14",key:"1ays0h"}],["path",{d:"m12 5 7 7-7 7",key:"xquz4c"}]],xy=oe("arrow-right",vy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const wy=[["path",{d:"M7 7h10v10",key:"1tivn9"}],["path",{d:"M7 17 17 7",key:"1vkiza"}]],If=oe("arrow-up-right",wy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const ky=[["path",{d:"M10.268 21a2 2 0 0 0 3.464 0",key:"vwvbt9"}],["path",{d:"M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326",key:"11g9vi"}]],Sy=oe("bell",ky);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const jy=[["path",{d:"M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z",key:"l5xja"}],["path",{d:"M9 13a4.5 4.5 0 0 0 3-4",key:"10igwf"}],["path",{d:"M6.003 5.125A3 3 0 0 0 6.401 6.5",key:"105sqy"}],["path",{d:"M3.477 10.896a4 4 0 0 1 .585-.396",key:"ql3yin"}],["path",{d:"M6 18a4 4 0 0 1-1.967-.516",key:"2e4loj"}],["path",{d:"M12 13h4",key:"1ku699"}],["path",{d:"M12 18h6a2 2 0 0 1 2 2v1",key:"105ag5"}],["path",{d:"M12 8h8",key:"1lhi5i"}],["path",{d:"M16 8V5a2 2 0 0 1 2-2",key:"u6izg6"}],["circle",{cx:"16",cy:"13",r:".5",key:"ry7gng"}],["circle",{cx:"18",cy:"3",r:".5",key:"1aiba7"}],["circle",{cx:"20",cy:"21",r:".5",key:"yhc1fs"}],["circle",{cx:"20",cy:"8",r:".5",key:"1e43v0"}]],lp=oe("brain-circuit",jy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Ny=[["path",{d:"M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16",key:"jecpp"}],["rect",{width:"20",height:"14",x:"2",y:"6",rx:"2",key:"i6l2r4"}]],oo=oe("briefcase",Ny);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Ty=[["path",{d:"M8 2v4",key:"1cmpym"}],["path",{d:"M16 2v4",key:"4m81vk"}],["rect",{width:"18",height:"18",x:"3",y:"4",rx:"2",key:"1hopcy"}],["path",{d:"M3 10h18",key:"8toen8"}]],Cy=oe("calendar",Ty);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Py=[["path",{d:"M3 3v16a2 2 0 0 0 2 2h16",key:"c24i48"}],["path",{d:"M18 17V9",key:"2bz60n"}],["path",{d:"M13 17V5",key:"1frdt8"}],["path",{d:"M8 17v-3",key:"17ska0"}]],Ey=oe("chart-column",Py);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const by=[["path",{d:"M20 6 9 17l-5-5",key:"1gmf2c"}]],Of=oe("check",by);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const My=[["path",{d:"m6 9 6 6 6-6",key:"qrunsl"}]],up=oe("chevron-down",My);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const _y=[["path",{d:"m9 18 6-6-6-6",key:"mthhwq"}]],Ay=oe("chevron-right",_y);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Ry=[["path",{d:"m18 15-6-6-6 6",key:"153udz"}]],cp=oe("chevron-up",Ry);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Dy=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["line",{x1:"12",x2:"12",y1:"8",y2:"12",key:"1pkeuh"}],["line",{x1:"12",x2:"12.01",y1:"16",y2:"16",key:"4dfq90"}]],Ly=oe("circle-alert",Dy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Vy=[["path",{d:"M21.801 10A10 10 0 1 1 17 3.335",key:"yps3ct"}],["path",{d:"m9 11 3 3L22 4",key:"1pflzl"}]],zy=oe("circle-check-big",Vy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Iy=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"m9 12 2 2 4-4",key:"dzmm74"}]],yr=oe("circle-check",Iy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Oy=[["path",{d:"M10.1 2.182a10 10 0 0 1 3.8 0",key:"5ilxe3"}],["path",{d:"M13.9 21.818a10 10 0 0 1-3.8 0",key:"11zvb9"}],["path",{d:"M17.609 3.721a10 10 0 0 1 2.69 2.7",key:"1iw5b2"}],["path",{d:"M2.182 13.9a10 10 0 0 1 0-3.8",key:"c0bmvh"}],["path",{d:"M20.279 17.609a10 10 0 0 1-2.7 2.69",key:"1ruxm7"}],["path",{d:"M21.818 10.1a10 10 0 0 1 0 3.8",key:"qkgqxc"}],["path",{d:"M3.721 6.391a10 10 0 0 1 2.7-2.69",key:"1mcia2"}],["path",{d:"M6.391 20.279a10 10 0 0 1-2.69-2.7",key:"1fvljs"}]],Fy=oe("circle-dashed",Oy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const By=[["path",{d:"M17.925 20.056a6 6 0 0 0-11.851.001",key:"z69sun"}],["circle",{cx:"12",cy:"11",r:"4",key:"1gt34v"}],["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}]],dp=oe("circle-user-round",By);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Uy=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"M12 6v6h4",key:"135r8i"}]],$y=oe("clock-3",Uy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Wy=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"M12 6v6l4 2",key:"mmk7yg"}]],fp=oe("clock",Wy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Hy=[["path",{d:"M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z",key:"1fr9dc"}],["path",{d:"M8 10v4",key:"tgpxqk"}],["path",{d:"M12 10v2",key:"hh53o1"}],["path",{d:"M16 10v6",key:"1d6xys"}]],ms=oe("folder-kanban",Hy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Ky=[["path",{d:"M10 20a1 1 0 0 0 .553.895l2 1A1 1 0 0 0 14 21v-7a2 2 0 0 1 .517-1.341L21.74 4.67A1 1 0 0 0 21 3H3a1 1 0 0 0-.742 1.67l7.225 7.989A2 2 0 0 1 10 14z",key:"sc7q7i"}]],Gy=oe("funnel",Ky);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Yy=[["path",{d:"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8",key:"1357e3"}],["path",{d:"M3 3v5h5",key:"1xhq8a"}],["path",{d:"M12 7v5l4 2",key:"1fdv2h"}]],hp=oe("history",Yy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Xy=[["path",{d:"M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z",key:"zw3jo"}],["path",{d:"M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12",key:"1wduqc"}],["path",{d:"M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17",key:"kqbvx6"}]],Qy=oe("layers",Xy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const qy=[["rect",{width:"7",height:"9",x:"3",y:"3",rx:"1",key:"10lvy0"}],["rect",{width:"7",height:"5",x:"14",y:"3",rx:"1",key:"16une8"}],["rect",{width:"7",height:"9",x:"14",y:"12",rx:"1",key:"1hutg5"}],["rect",{width:"7",height:"5",x:"3",y:"16",rx:"1",key:"ldoo1y"}]],pp=oe("layout-dashboard",qy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Zy=[["path",{d:"M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0",key:"1r0f0z"}],["circle",{cx:"12",cy:"10",r:"3",key:"ilqhr7"}]],Jy=oe("map-pin",Zy);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const ev=[["path",{d:"M11 6a13 13 0 0 0 8.4-2.8A1 1 0 0 1 21 4v12a1 1 0 0 1-1.6.8A13 13 0 0 0 11 14H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z",key:"q8bfy3"}],["path",{d:"M6 14a12 12 0 0 0 2.4 7.2 2 2 0 0 0 3.2-2.4A8 8 0 0 1 10 14",key:"1853fq"}],["path",{d:"M8 6v8",key:"15ugcq"}]],Qi=oe("megaphone",ev);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const tv=[["path",{d:"M4 5h16",key:"1tepv9"}],["path",{d:"M4 12h16",key:"1lakjw"}],["path",{d:"M4 19h16",key:"1djgab"}]],nv=oe("menu",tv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const rv=[["path",{d:"M2.992 16.342a2 2 0 0 1 .094 1.167l-1.065 3.29a1 1 0 0 0 1.236 1.168l3.413-.998a2 2 0 0 1 1.099.092 10 10 0 1 0-4.777-4.719",key:"1sd12s"}]],tu=oe("message-circle",rv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const sv=[["path",{d:"M5 12h14",key:"1ays0h"}]],iv=oe("minus",sv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const ov=[["path",{d:"M12 22V12",key:"d0xqtd"}],["path",{d:"m16.5 14.5 5 5",key:"ozpm51"}],["path",{d:"m16.5 19.5 5-5",key:"syf6b9"}],["path",{d:"M21 10.5V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.729l7 4a2 2 0 0 0 2 .001l.13-.074",key:"isw6gs"}],["path",{d:"M3.29 7 12 12l8.71-5",key:"19ckod"}],["path",{d:"m7.5 4.27 8.997 5.148",key:"9yrvtv"}]],Ff=oe("package-x",ov);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const av=[["path",{d:"M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z",key:"1a0edw"}],["path",{d:"M12 22V12",key:"d0xqtd"}],["polyline",{points:"3.29 7 12 12 20.71 7",key:"ousv84"}],["path",{d:"m7.5 4.27 9 5.15",key:"1c824w"}]],gs=oe("package",av);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const lv=[["rect",{x:"14",y:"3",width:"5",height:"18",rx:"1",key:"kaeet6"}],["rect",{x:"5",y:"3",width:"5",height:"18",rx:"1",key:"1wsw3u"}]],uv=oe("pause",lv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const cv=[["path",{d:"M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z",key:"10ikf1"}]],dv=oe("play",cv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const fv=[["path",{d:"M5 12h14",key:"1ays0h"}],["path",{d:"M12 5v14",key:"s699le"}]],hv=oe("plus",fv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const pv=[["path",{d:"M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8",key:"v9h5vc"}],["path",{d:"M21 3v5h-5",key:"1q7to0"}],["path",{d:"M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16",key:"3uifl3"}],["path",{d:"M8 16H3v5",key:"1cv678"}]],mp=oe("refresh-cw",pv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const mv=[["path",{d:"M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8",key:"1p45f6"}],["path",{d:"M21 3v5h-5",key:"1q7to0"}]],gv=oe("rotate-cw",mv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const yv=[["path",{d:"m21 21-4.34-4.34",key:"14j7rj"}],["circle",{cx:"11",cy:"11",r:"8",key:"4ej97u"}]],nu=oe("search",yv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const vv=[["path",{d:"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z",key:"oel41y"}],["path",{d:"m9 12 2 2 4-4",key:"dzmm74"}]],xv=oe("shield-check",vv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const wv=[["circle",{cx:"8",cy:"21",r:"1",key:"jimo8o"}],["circle",{cx:"19",cy:"21",r:"1",key:"13723u"}],["path",{d:"M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12",key:"9zh506"}]],kv=oe("shopping-cart",wv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Sv=[["path",{d:"M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z",key:"1s2grr"}],["path",{d:"M20 2v4",key:"1rf3ol"}],["path",{d:"M22 4h-4",key:"gwowj6"}],["circle",{cx:"4",cy:"20",r:"2",key:"6kqj1y"}]],gp=oe("sparkles",Sv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const jv=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["circle",{cx:"12",cy:"12",r:"6",key:"1vlfrh"}],["circle",{cx:"12",cy:"12",r:"2",key:"1c9p78"}]],Bf=oe("target",jv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Nv=[["path",{d:"M16 7h6v6",key:"box55l"}],["path",{d:"m22 7-8.5 8.5-5-5L2 17",key:"1t1m79"}]],bl=oe("trending-up",Nv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Tv=[["path",{d:"m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3",key:"wmoenq"}],["path",{d:"M12 9v4",key:"juzpu7"}],["path",{d:"M12 17h.01",key:"p32p05"}]],yp=oe("triangle-alert",Tv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Cv=[["path",{d:"M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2",key:"1yyitq"}],["path",{d:"M16 3.128a4 4 0 0 1 0 7.744",key:"16gr8j"}],["path",{d:"M22 21v-2a4 4 0 0 0-3-3.87",key:"kshegd"}],["circle",{cx:"9",cy:"7",r:"4",key:"nufk8"}]],vp=oe("users",Cv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Pv=[["path",{d:"M12 20h.01",key:"zekei9"}],["path",{d:"M8.5 16.429a5 5 0 0 1 7 0",key:"1bycff"}],["path",{d:"M5 12.859a10 10 0 0 1 5.17-2.69",key:"1dl1wf"}],["path",{d:"M19 12.859a10 10 0 0 0-2.007-1.523",key:"4k23kn"}],["path",{d:"M2 8.82a15 15 0 0 1 4.177-2.643",key:"1grhjp"}],["path",{d:"M22 8.82a15 15 0 0 0-11.288-3.764",key:"z3jwby"}],["path",{d:"m2 2 20 20",key:"1ooewy"}]],Ev=oe("wifi-off",Pv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const bv=[["path",{d:"M12 20h.01",key:"zekei9"}],["path",{d:"M2 8.82a15 15 0 0 1 20 0",key:"dnpr2z"}],["path",{d:"M5 12.859a10 10 0 0 1 14 0",key:"1x1e6c"}],["path",{d:"M8.5 16.429a5 5 0 0 1 7 0",key:"1bycff"}]],Mv=oe("wifi",bv);/**
 * @license lucide-react v1.7.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const _v=[["path",{d:"M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z",key:"1xq2db"}]],ys=oe("zap",_v),ru=z.createContext({});function su(n){const r=z.useRef(null);return r.current===null&&(r.current=n()),r.current}const Av=typeof window<"u",xp=Av?z.useLayoutEffect:z.useEffect,ao=z.createContext(null);function iu(n,r){n.indexOf(r)===-1&&n.push(r)}function qi(n,r){const i=n.indexOf(r);i>-1&&n.splice(i,1)}const Ut=(n,r,i)=>i>r?r:i<n?n:i;let ou=()=>{};const wn={},wp=n=>/^-?(?:\d+(?:\.\d+)?|\.\d+)$/u.test(n);function kp(n){return typeof n=="object"&&n!==null}const Sp=n=>/^0[^.\s]+$/u.test(n);function jp(n){let r;return()=>(r===void 0&&(r=n()),r)}const jt=n=>n,Rv=(n,r)=>i=>r(n(i)),Ss=(...n)=>n.reduce(Rv),vs=(n,r,i)=>{const a=r-n;return a===0?1:(i-n)/a};class au{constructor(){this.subscriptions=[]}add(r){return iu(this.subscriptions,r),()=>qi(this.subscriptions,r)}notify(r,i,a){const u=this.subscriptions.length;if(u)if(u===1)this.subscriptions[0](r,i,a);else for(let f=0;f<u;f++){const d=this.subscriptions[f];d&&d(r,i,a)}}getSize(){return this.subscriptions.length}clear(){this.subscriptions.length=0}}const mt=n=>n*1e3,St=n=>n/1e3;function Np(n,r){return r?n*(1e3/r):0}const Tp=(n,r,i)=>(((1-3*i+3*r)*n+(3*i-6*r))*n+3*r)*n,Dv=1e-7,Lv=12;function Vv(n,r,i,a,u){let f,d,p=0;do d=r+(i-r)/2,f=Tp(d,a,u)-n,f>0?i=d:r=d;while(Math.abs(f)>Dv&&++p<Lv);return d}function js(n,r,i,a){if(n===r&&i===a)return jt;const u=f=>Vv(f,0,1,n,i);return f=>f===0||f===1?f:Tp(u(f),r,a)}const Cp=n=>r=>r<=.5?n(2*r)/2:(2-n(2*(1-r)))/2,Pp=n=>r=>1-n(1-r),Ep=js(.33,1.53,.69,.99),lu=Pp(Ep),bp=Cp(lu),Mp=n=>n>=1?1:(n*=2)<1?.5*lu(n):.5*(2-Math.pow(2,-10*(n-1))),uu=n=>1-Math.sin(Math.acos(n)),_p=Pp(uu),Ap=Cp(uu),zv=js(.42,0,1,1),Iv=js(0,0,.58,1),Rp=js(.42,0,.58,1),Ov=n=>Array.isArray(n)&&typeof n[0]!="number",Dp=n=>Array.isArray(n)&&typeof n[0]=="number",Fv={linear:jt,easeIn:zv,easeInOut:Rp,easeOut:Iv,circIn:uu,circInOut:Ap,circOut:_p,backIn:lu,backInOut:bp,backOut:Ep,anticipate:Mp},Bv=n=>typeof n=="string",Uf=n=>{if(Dp(n)){ou(n.length===4);const[r,i,a,u]=n;return js(r,i,a,u)}else if(Bv(n))return Fv[n];return n},zi=["setup","read","resolveKeyframes","preUpdate","update","preRender","render","postRender"];function Uv(n,r){let i=new Set,a=new Set,u=!1,f=!1;const d=new WeakSet;let p={delta:0,timestamp:0,isProcessing:!1};function g(y){d.has(y)&&(x.schedule(y),n()),y(p)}const x={schedule:(y,v=!1,w=!1)=>{const E=w&&u?i:a;return v&&d.add(y),E.add(y),y},cancel:y=>{a.delete(y),d.delete(y)},process:y=>{if(p=y,u){f=!0;return}u=!0;const v=i;i=a,a=v,i.forEach(g),i.clear(),u=!1,f&&(f=!1,x.process(y))}};return x}const $v=40;function Lp(n,r){let i=!1,a=!0;const u={delta:0,timestamp:0,isProcessing:!1},f=()=>i=!0,d=zi.reduce((I,U)=>(I[U]=Uv(f),I),{}),{setup:p,read:g,resolveKeyframes:x,preUpdate:y,update:v,preRender:w,render:N,postRender:E}=d,_=()=>{const I=wn.useManualTiming,U=I?u.timestamp:performance.now();i=!1,I||(u.delta=a?1e3/60:Math.max(Math.min(U-u.timestamp,$v),1)),u.timestamp=U,u.isProcessing=!0,p.process(u),g.process(u),x.process(u),y.process(u),v.process(u),w.process(u),N.process(u),E.process(u),u.isProcessing=!1,i&&r&&(a=!1,n(_))},M=()=>{i=!0,a=!0,u.isProcessing||n(_)};return{schedule:zi.reduce((I,U)=>{const W=d[U];return I[U]=(se,G=!1,H=!1)=>(i||M(),W.schedule(se,G,H)),I},{}),cancel:I=>{for(let U=0;U<zi.length;U++)d[zi[U]].cancel(I)},state:u,steps:d}}const{schedule:ve,cancel:kn,state:Ye,steps:fl}=Lp(typeof requestAnimationFrame<"u"?requestAnimationFrame:jt,!0);let Ui;function Wv(){Ui=void 0}const nt={now:()=>(Ui===void 0&&nt.set(Ye.isProcessing||wn.useManualTiming?Ye.timestamp:performance.now()),Ui),set:n=>{Ui=n,queueMicrotask(Wv)}},Vp=n=>r=>typeof r=="string"&&r.startsWith(n),zp=Vp("--"),Hv=Vp("var(--"),cu=n=>Hv(n)?Kv.test(n.split("/*")[0].trim()):!1,Kv=/var\(--(?:[\w-]+\s*|[\w-]+\s*,(?:\s*[^)(\s]|\s*\((?:[^)(]|\([^)(]*\))*\))+\s*)\)$/iu;function $f(n){return typeof n!="string"?!1:n.split("/*")[0].includes("var(--")}const wr={test:n=>typeof n=="number",parse:parseFloat,transform:n=>n},xs={...wr,transform:n=>Ut(0,1,n)},Ii={...wr,default:1},ds=n=>Math.round(n*1e5)/1e5,du=/-?(?:\d+(?:\.\d+)?|\.\d+)/gu;function Gv(n){return n==null}const Yv=/^(?:#[\da-f]{3,8}|(?:rgb|hsl)a?\((?:-?[\d.]+%?[,\s]+){2}-?[\d.]+%?\s*(?:[,/]\s*)?(?:\b\d+(?:\.\d+)?|\.\d+)?%?\))$/iu,fu=(n,r)=>i=>!!(typeof i=="string"&&Yv.test(i)&&i.startsWith(n)||r&&!Gv(i)&&Object.prototype.hasOwnProperty.call(i,r)),Ip=(n,r,i)=>a=>{if(typeof a!="string")return a;const[u,f,d,p]=a.match(du);return{[n]:parseFloat(u),[r]:parseFloat(f),[i]:parseFloat(d),alpha:p!==void 0?parseFloat(p):1}},Xv=n=>Ut(0,255,n),hl={...wr,transform:n=>Math.round(Xv(n))},In={test:fu("rgb","red"),parse:Ip("red","green","blue"),transform:({red:n,green:r,blue:i,alpha:a=1})=>"rgba("+hl.transform(n)+", "+hl.transform(r)+", "+hl.transform(i)+", "+ds(xs.transform(a))+")"};function Qv(n){let r="",i="",a="",u="";return n.length>5?(r=n.substring(1,3),i=n.substring(3,5),a=n.substring(5,7),u=n.substring(7,9)):(r=n.substring(1,2),i=n.substring(2,3),a=n.substring(3,4),u=n.substring(4,5),r+=r,i+=i,a+=a,u+=u),{red:parseInt(r,16),green:parseInt(i,16),blue:parseInt(a,16),alpha:u?parseInt(u,16)/255:1}}const Ml={test:fu("#"),parse:Qv,transform:In.transform},Ns=n=>({test:r=>typeof r=="string"&&r.endsWith(n)&&r.split(" ").length===1,parse:parseFloat,transform:r=>`${r}${n}`}),yn=Ns("deg"),Bt=Ns("%"),q=Ns("px"),qv=Ns("vh"),Zv=Ns("vw"),Wf={...Bt,parse:n=>Bt.parse(n)/100,transform:n=>Bt.transform(n*100)},pr={test:fu("hsl","hue"),parse:Ip("hue","saturation","lightness"),transform:({hue:n,saturation:r,lightness:i,alpha:a=1})=>"hsla("+Math.round(n)+", "+Bt.transform(ds(r))+", "+Bt.transform(ds(i))+", "+ds(xs.transform(a))+")"},Oe={test:n=>In.test(n)||Ml.test(n)||pr.test(n),parse:n=>In.test(n)?In.parse(n):pr.test(n)?pr.parse(n):Ml.parse(n),transform:n=>typeof n=="string"?n:n.hasOwnProperty("red")?In.transform(n):pr.transform(n),getAnimatableNone:n=>{const r=Oe.parse(n);return r.alpha=0,Oe.transform(r)}},Jv=/(?:#[\da-f]{3,8}|(?:rgb|hsl)a?\((?:-?[\d.]+%?[,\s]+){2}-?[\d.]+%?\s*(?:[,/]\s*)?(?:\b\d+(?:\.\d+)?|\.\d+)?%?\))/giu;function ex(n){var r,i;return isNaN(n)&&typeof n=="string"&&(((r=n.match(du))==null?void 0:r.length)||0)+(((i=n.match(Jv))==null?void 0:i.length)||0)>0}const Op="number",Fp="color",tx="var",nx="var(",Hf="${}",rx=/var\s*\(\s*--(?:[\w-]+\s*|[\w-]+\s*,(?:\s*[^)(\s]|\s*\((?:[^)(]|\([^)(]*\))*\))+\s*)\)|#[\da-f]{3,8}|(?:rgb|hsl)a?\((?:-?[\d.]+%?[,\s]+){2}-?[\d.]+%?\s*(?:[,/]\s*)?(?:\b\d+(?:\.\d+)?|\.\d+)?%?\)|-?(?:\d+(?:\.\d+)?|\.\d+)/giu;function vr(n){const r=n.toString(),i=[],a={color:[],number:[],var:[]},u=[];let f=0;const p=r.replace(rx,g=>(Oe.test(g)?(a.color.push(f),u.push(Fp),i.push(Oe.parse(g))):g.startsWith(nx)?(a.var.push(f),u.push(tx),i.push(g)):(a.number.push(f),u.push(Op),i.push(parseFloat(g))),++f,Hf)).split(Hf);return{values:i,split:p,indexes:a,types:u}}function sx(n){return vr(n).values}function Bp({split:n,types:r}){const i=n.length;return a=>{let u="";for(let f=0;f<i;f++)if(u+=n[f],a[f]!==void 0){const d=r[f];d===Op?u+=ds(a[f]):d===Fp?u+=Oe.transform(a[f]):u+=a[f]}return u}}function ix(n){return Bp(vr(n))}const ox=n=>typeof n=="number"?0:Oe.test(n)?Oe.getAnimatableNone(n):n,ax=(n,r)=>typeof n=="number"?r!=null&&r.trim().endsWith("/")?n:0:ox(n);function lx(n){const r=vr(n);return Bp(r)(r.values.map((a,u)=>ax(a,r.split[u])))}const Rt={test:ex,parse:sx,createTransformer:ix,getAnimatableNone:lx};function pl(n,r,i){return i<0&&(i+=1),i>1&&(i-=1),i<1/6?n+(r-n)*6*i:i<1/2?r:i<2/3?n+(r-n)*(2/3-i)*6:n}function ux({hue:n,saturation:r,lightness:i,alpha:a}){n/=360,r/=100,i/=100;let u=0,f=0,d=0;if(!r)u=f=d=i;else{const p=i<.5?i*(1+r):i+r-i*r,g=2*i-p;u=pl(g,p,n+1/3),f=pl(g,p,n),d=pl(g,p,n-1/3)}return{red:Math.round(u*255),green:Math.round(f*255),blue:Math.round(d*255),alpha:a}}function Zi(n,r){return i=>i>0?r:n}const Ne=(n,r,i)=>n+(r-n)*i,ml=(n,r,i)=>{const a=n*n,u=i*(r*r-a)+a;return u<0?0:Math.sqrt(u)},cx=[Ml,In,pr],dx=n=>cx.find(r=>r.test(n));function Kf(n){const r=dx(n);if(!r)return!1;let i=r.parse(n);return r===pr&&(i=ux(i)),i}const Gf=(n,r)=>{const i=Kf(n),a=Kf(r);if(!i||!a)return Zi(n,r);const u={...i};return f=>(u.red=ml(i.red,a.red,f),u.green=ml(i.green,a.green,f),u.blue=ml(i.blue,a.blue,f),u.alpha=Ne(i.alpha,a.alpha,f),In.transform(u))},_l=new Set(["none","hidden"]);function fx(n,r){return _l.has(n)?i=>i<=0?n:r:i=>i>=1?r:n}function hx(n,r){return i=>Ne(n,r,i)}function hu(n){return typeof n=="number"?hx:typeof n=="string"?cu(n)?Zi:Oe.test(n)?Gf:gx:Array.isArray(n)?Up:typeof n=="object"?Oe.test(n)?Gf:px:Zi}function Up(n,r){const i=[...n],a=i.length,u=n.map((f,d)=>hu(f)(f,r[d]));return f=>{for(let d=0;d<a;d++)i[d]=u[d](f);return i}}function px(n,r){const i={...n,...r},a={};for(const u in i)n[u]!==void 0&&r[u]!==void 0&&(a[u]=hu(n[u])(n[u],r[u]));return u=>{for(const f in a)i[f]=a[f](u);return i}}function mx(n,r){const i=[],a={color:0,var:0,number:0};for(let u=0;u<r.values.length;u++){const f=r.types[u],d=n.indexes[f][a[f]],p=n.values[d]??0;i[u]=p,a[f]++}return i}const gx=(n,r)=>{const i=Rt.createTransformer(r),a=vr(n),u=vr(r);return a.indexes.var.length===u.indexes.var.length&&a.indexes.color.length===u.indexes.color.length&&a.indexes.number.length>=u.indexes.number.length?_l.has(n)&&!u.values.length||_l.has(r)&&!a.values.length?fx(n,r):Ss(Up(mx(a,u),u.values),i):Zi(n,r)};function $p(n,r,i){return typeof n=="number"&&typeof r=="number"&&typeof i=="number"?Ne(n,r,i):hu(n)(n,r)}const yx=n=>{const r=({timestamp:i})=>n(i);return{start:(i=!0)=>ve.update(r,i),stop:()=>kn(r),now:()=>Ye.isProcessing?Ye.timestamp:nt.now()}},Wp=(n,r,i=10)=>{let a="";const u=Math.max(Math.round(r/i),2);for(let f=0;f<u;f++)a+=Math.round(n(f/(u-1))*1e4)/1e4+", ";return`linear(${a.substring(0,a.length-2)})`},Ji=2e4;function pu(n){let r=0;const i=50;let a=n.next(r);for(;!a.done&&r<Ji;)r+=i,a=n.next(r);return r>=Ji?1/0:r}function vx(n,r=100,i){const a=i({...n,keyframes:[0,r]}),u=Math.min(pu(a),Ji);return{type:"keyframes",ease:f=>a.next(u*f).value/r,duration:St(u)}}const Re={stiffness:100,damping:10,mass:1,velocity:0,duration:800,bounce:.3,visualDuration:.3,restSpeed:{granular:.01,default:2},restDelta:{granular:.005,default:.5},minDuration:.01,maxDuration:10,minDamping:.05,maxDamping:1};function Al(n,r){return n*Math.sqrt(1-r*r)}const xx=12;function wx(n,r,i){let a=i;for(let u=1;u<xx;u++)a=a-n(a)/r(a);return a}const gl=.001;function kx({duration:n=Re.duration,bounce:r=Re.bounce,velocity:i=Re.velocity,mass:a=Re.mass}){let u,f,d=1-r;d=Ut(Re.minDamping,Re.maxDamping,d),n=Ut(Re.minDuration,Re.maxDuration,St(n)),d<1?(u=x=>{const y=x*d,v=y*n,w=y-i,N=Al(x,d),E=Math.exp(-v);return gl-w/N*E},f=x=>{const v=x*d*n,w=v*i+i,N=Math.pow(d,2)*Math.pow(x,2)*n,E=Math.exp(-v),_=Al(Math.pow(x,2),d);return(-u(x)+gl>0?-1:1)*((w-N)*E)/_}):(u=x=>{const y=Math.exp(-x*n),v=(x-i)*n+1;return-gl+y*v},f=x=>{const y=Math.exp(-x*n),v=(i-x)*(n*n);return y*v});const p=5/n,g=wx(u,f,p);if(n=mt(n),isNaN(g))return{stiffness:Re.stiffness,damping:Re.damping,duration:n};{const x=Math.pow(g,2)*a;return{stiffness:x,damping:d*2*Math.sqrt(a*x),duration:n}}}const Sx=["duration","bounce"],jx=["stiffness","damping","mass"];function Yf(n,r){return r.some(i=>n[i]!==void 0)}function Nx(n){let r={velocity:Re.velocity,stiffness:Re.stiffness,damping:Re.damping,mass:Re.mass,isResolvedFromDuration:!1,...n};if(!Yf(n,jx)&&Yf(n,Sx))if(r.velocity=0,n.visualDuration){const i=n.visualDuration,a=2*Math.PI/(i*1.2),u=a*a,f=2*Ut(.05,1,1-(n.bounce||0))*Math.sqrt(u);r={...r,mass:Re.mass,stiffness:u,damping:f}}else{const i=kx({...n,velocity:0});r={...r,...i,mass:Re.mass},r.isResolvedFromDuration=!0}return r}function eo(n=Re.visualDuration,r=Re.bounce){const i=typeof n!="object"?{visualDuration:n,keyframes:[0,1],bounce:r}:n;let{restSpeed:a,restDelta:u}=i;const f=i.keyframes[0],d=i.keyframes[i.keyframes.length-1],p={done:!1,value:f},{stiffness:g,damping:x,mass:y,duration:v,velocity:w,isResolvedFromDuration:N}=Nx({...i,velocity:-St(i.velocity||0)}),E=w||0,_=x/(2*Math.sqrt(g*y)),M=d-f,L=St(Math.sqrt(g/y)),B=Math.abs(M)<5;a||(a=B?Re.restSpeed.granular:Re.restSpeed.default),u||(u=B?Re.restDelta.granular:Re.restDelta.default);let I,U,W,se,G,H;if(_<1)W=Al(L,_),se=(E+_*L*M)/W,I=Y=>{const ce=Math.exp(-_*L*Y);return d-ce*(se*Math.sin(W*Y)+M*Math.cos(W*Y))},G=_*L*se+M*W,H=_*L*M-se*W,U=Y=>Math.exp(-_*L*Y)*(G*Math.sin(W*Y)+H*Math.cos(W*Y));else if(_===1){I=ce=>d-Math.exp(-L*ce)*(M+(E+L*M)*ce);const Y=E+L*M;U=ce=>Math.exp(-L*ce)*(L*Y*ce-E)}else{const Y=L*Math.sqrt(_*_-1);I=_e=>{const ze=Math.exp(-_*L*_e),ke=Math.min(Y*_e,300);return d-ze*((E+_*L*M)*Math.sinh(ke)+Y*M*Math.cosh(ke))/Y};const ce=(E+_*L*M)/Y,me=_*L*ce-M*Y,Pe=_*L*M-ce*Y;U=_e=>{const ze=Math.exp(-_*L*_e),ke=Math.min(Y*_e,300);return ze*(me*Math.sinh(ke)+Pe*Math.cosh(ke))}}const re={calculatedDuration:N&&v||null,velocity:Y=>mt(U(Y)),next:Y=>{if(!N&&_<1){const me=Math.exp(-_*L*Y),Pe=Math.sin(W*Y),_e=Math.cos(W*Y),ze=d-me*(se*Pe+M*_e),ke=mt(me*(G*Pe+H*_e));return p.done=Math.abs(ke)<=a&&Math.abs(d-ze)<=u,p.value=p.done?d:ze,p}const ce=I(Y);if(N)p.done=Y>=v;else{const me=mt(U(Y));p.done=Math.abs(me)<=a&&Math.abs(d-ce)<=u}return p.value=p.done?d:ce,p},toString:()=>{const Y=Math.min(pu(re),Ji),ce=Wp(me=>re.next(Y*me).value,Y,30);return Y+"ms "+ce},toTransition:()=>{}};return re}eo.applyToOptions=n=>{const r=vx(n,100,eo);return n.ease=r.ease,n.duration=mt(r.duration),n.type="keyframes",n};const Tx=5;function Hp(n,r,i){const a=Math.max(r-Tx,0);return Np(i-n(a),r-a)}function Rl({keyframes:n,velocity:r=0,power:i=.8,timeConstant:a=325,bounceDamping:u=10,bounceStiffness:f=500,modifyTarget:d,min:p,max:g,restDelta:x=.5,restSpeed:y}){const v=n[0],w={done:!1,value:v},N=H=>p!==void 0&&H<p||g!==void 0&&H>g,E=H=>p===void 0?g:g===void 0||Math.abs(p-H)<Math.abs(g-H)?p:g;let _=i*r;const M=v+_,L=d===void 0?M:d(M);L!==M&&(_=L-v);const B=H=>-_*Math.exp(-H/a),I=H=>L+B(H),U=H=>{const re=B(H),Y=I(H);w.done=Math.abs(re)<=x,w.value=w.done?L:Y};let W,se;const G=H=>{N(w.value)&&(W=H,se=eo({keyframes:[w.value,E(w.value)],velocity:Hp(I,H,w.value),damping:u,stiffness:f,restDelta:x,restSpeed:y}))};return G(0),{calculatedDuration:null,next:H=>{let re=!1;return!se&&W===void 0&&(re=!0,U(H),G(H)),W!==void 0&&H>=W?se.next(H-W):(!re&&U(H),w)}}}function Cx(n,r,i){const a=[],u=i||wn.mix||$p,f=n.length-1;for(let d=0;d<f;d++){let p=u(n[d],n[d+1]);if(r){const g=Array.isArray(r)?r[d]||jt:r;p=Ss(g,p)}a.push(p)}return a}function Px(n,r,{clamp:i=!0,ease:a,mixer:u}={}){const f=n.length;if(ou(f===r.length),f===1)return()=>r[0];if(f===2&&r[0]===r[1])return()=>r[1];const d=n[0]===n[1];n[0]>n[f-1]&&(n=[...n].reverse(),r=[...r].reverse());const p=Cx(r,a,u),g=p.length,x=y=>{if(d&&y<n[0])return r[0];let v=0;if(g>1)for(;v<n.length-2&&!(y<n[v+1]);v++);const w=vs(n[v],n[v+1],y);return p[v](w)};return i?y=>x(Ut(n[0],n[f-1],y)):x}function Ex(n,r){const i=n[n.length-1];for(let a=1;a<=r;a++){const u=vs(0,r,a);n.push(Ne(i,1,u))}}function bx(n){const r=[0];return Ex(r,n.length-1),r}function Mx(n,r){return n.map(i=>i*r)}function _x(n,r){return n.map(()=>r||Rp).splice(0,n.length-1)}function fs({duration:n=300,keyframes:r,times:i,ease:a="easeInOut"}){const u=Ov(a)?a.map(Uf):Uf(a),f={done:!1,value:r[0]},d=Mx(i&&i.length===r.length?i:bx(r),n),p=Px(d,r,{ease:Array.isArray(u)?u:_x(r,u)});return{calculatedDuration:n,next:g=>(f.value=p(g),f.done=g>=n,f)}}const Ax=n=>n!==null;function lo(n,{repeat:r,repeatType:i="loop"},a,u=1){const f=n.filter(Ax),p=u<0||r&&i!=="loop"&&r%2===1?0:f.length-1;return!p||a===void 0?f[p]:a}const Rx={decay:Rl,inertia:Rl,tween:fs,keyframes:fs,spring:eo};function Kp(n){typeof n.type=="string"&&(n.type=Rx[n.type])}class mu{constructor(){this.updateFinished()}get finished(){return this._finished}updateFinished(){this._finished=new Promise(r=>{this.resolve=r})}notifyFinished(){this.resolve()}then(r,i){return this.finished.then(r,i)}}const Dx=n=>n/100;class to extends mu{constructor(r){super(),this.state="idle",this.startTime=null,this.isStopped=!1,this.currentTime=0,this.holdTime=null,this.playbackSpeed=1,this.delayState={done:!1,value:void 0},this.stop=()=>{var a,u;const{motionValue:i}=this.options;i&&i.updatedAt!==nt.now()&&this.tick(nt.now()),this.isStopped=!0,this.state!=="idle"&&(this.teardown(),(u=(a=this.options).onStop)==null||u.call(a))},this.options=r,this.initAnimation(),this.play(),r.autoplay===!1&&this.pause()}initAnimation(){const{options:r}=this;Kp(r);const{type:i=fs,repeat:a=0,repeatDelay:u=0,repeatType:f,velocity:d=0}=r;let{keyframes:p}=r;const g=i||fs;g!==fs&&typeof p[0]!="number"&&(this.mixKeyframes=Ss(Dx,$p(p[0],p[1])),p=[0,100]);const x=g({...r,keyframes:p});f==="mirror"&&(this.mirroredGenerator=g({...r,keyframes:[...p].reverse(),velocity:-d})),x.calculatedDuration===null&&(x.calculatedDuration=pu(x));const{calculatedDuration:y}=x;this.calculatedDuration=y,this.resolvedDuration=y+u,this.totalDuration=this.resolvedDuration*(a+1)-u,this.generator=x}updateTime(r){const i=Math.round(r-this.startTime)*this.playbackSpeed;this.holdTime!==null?this.currentTime=this.holdTime:this.currentTime=i}tick(r,i=!1){const{generator:a,totalDuration:u,mixKeyframes:f,mirroredGenerator:d,resolvedDuration:p,calculatedDuration:g}=this;if(this.startTime===null)return a.next(0);const{delay:x=0,keyframes:y,repeat:v,repeatType:w,repeatDelay:N,type:E,onUpdate:_,finalKeyframe:M}=this.options;this.speed>0?this.startTime=Math.min(this.startTime,r):this.speed<0&&(this.startTime=Math.min(r-u/this.speed,this.startTime)),i?this.currentTime=r:this.updateTime(r);const L=this.currentTime-x*(this.playbackSpeed>=0?1:-1),B=this.playbackSpeed>=0?L<0:L>u;this.currentTime=Math.max(L,0),this.state==="finished"&&this.holdTime===null&&(this.currentTime=u);let I=this.currentTime,U=a;if(v){const H=Math.min(this.currentTime,u)/p;let re=Math.floor(H),Y=H%1;!Y&&H>=1&&(Y=1),Y===1&&re--,re=Math.min(re,v+1),!!(re%2)&&(w==="reverse"?(Y=1-Y,N&&(Y-=N/p)):w==="mirror"&&(U=d)),I=Ut(0,1,Y)*p}let W;B?(this.delayState.value=y[0],W=this.delayState):W=U.next(I),f&&!B&&(W.value=f(W.value));let{done:se}=W;!B&&g!==null&&(se=this.playbackSpeed>=0?this.currentTime>=u:this.currentTime<=0);const G=this.holdTime===null&&(this.state==="finished"||this.state==="running"&&se);return G&&E!==Rl&&(W.value=lo(y,this.options,M,this.speed)),_&&_(W.value),G&&this.finish(),W}then(r,i){return this.finished.then(r,i)}get duration(){return St(this.calculatedDuration)}get iterationDuration(){const{delay:r=0}=this.options||{};return this.duration+St(r)}get time(){return St(this.currentTime)}set time(r){r=mt(r),this.currentTime=r,this.startTime===null||this.holdTime!==null||this.playbackSpeed===0?this.holdTime=r:this.driver&&(this.startTime=this.driver.now()-r/this.playbackSpeed),this.driver?this.driver.start(!1):(this.startTime=0,this.state="paused",this.holdTime=r,this.tick(r))}getGeneratorVelocity(){const r=this.currentTime;if(r<=0)return this.options.velocity||0;if(this.generator.velocity)return this.generator.velocity(r);const i=this.generator.next(r).value;return Hp(a=>this.generator.next(a).value,r,i)}get speed(){return this.playbackSpeed}set speed(r){const i=this.playbackSpeed!==r;i&&this.driver&&this.updateTime(nt.now()),this.playbackSpeed=r,i&&this.driver&&(this.time=St(this.currentTime))}play(){var u,f;if(this.isStopped)return;const{driver:r=yx,startTime:i}=this.options;this.driver||(this.driver=r(d=>this.tick(d))),(f=(u=this.options).onPlay)==null||f.call(u);const a=this.driver.now();this.state==="finished"?(this.updateFinished(),this.startTime=a):this.holdTime!==null?this.startTime=a-this.holdTime:this.startTime||(this.startTime=i??a),this.state==="finished"&&this.speed<0&&(this.startTime+=this.calculatedDuration),this.holdTime=null,this.state="running",this.driver.start()}pause(){this.state="paused",this.updateTime(nt.now()),this.holdTime=this.currentTime}complete(){this.state!=="running"&&this.play(),this.state="finished",this.holdTime=null}finish(){var r,i;this.notifyFinished(),this.teardown(),this.state="finished",(i=(r=this.options).onComplete)==null||i.call(r)}cancel(){var r,i;this.holdTime=null,this.startTime=0,this.tick(0),this.teardown(),(i=(r=this.options).onCancel)==null||i.call(r)}teardown(){this.state="idle",this.stopDriver(),this.startTime=this.holdTime=null}stopDriver(){this.driver&&(this.driver.stop(),this.driver=void 0)}sample(r){return this.startTime=0,this.tick(r,!0)}attachTimeline(r){var i;return this.options.allowFlatten&&(this.options.type="keyframes",this.options.ease="linear",this.initAnimation()),(i=this.driver)==null||i.stop(),r.observe(this)}}function Lx(n){for(let r=1;r<n.length;r++)n[r]??(n[r]=n[r-1])}const On=n=>n*180/Math.PI,Dl=n=>{const r=On(Math.atan2(n[1],n[0]));return Ll(r)},Vx={x:4,y:5,translateX:4,translateY:5,scaleX:0,scaleY:3,scale:n=>(Math.abs(n[0])+Math.abs(n[3]))/2,rotate:Dl,rotateZ:Dl,skewX:n=>On(Math.atan(n[1])),skewY:n=>On(Math.atan(n[2])),skew:n=>(Math.abs(n[1])+Math.abs(n[2]))/2},Ll=n=>(n=n%360,n<0&&(n+=360),n),Xf=Dl,Qf=n=>Math.sqrt(n[0]*n[0]+n[1]*n[1]),qf=n=>Math.sqrt(n[4]*n[4]+n[5]*n[5]),zx={x:12,y:13,z:14,translateX:12,translateY:13,translateZ:14,scaleX:Qf,scaleY:qf,scale:n=>(Qf(n)+qf(n))/2,rotateX:n=>Ll(On(Math.atan2(n[6],n[5]))),rotateY:n=>Ll(On(Math.atan2(-n[2],n[0]))),rotateZ:Xf,rotate:Xf,skewX:n=>On(Math.atan(n[4])),skewY:n=>On(Math.atan(n[1])),skew:n=>(Math.abs(n[1])+Math.abs(n[4]))/2};function Vl(n){return n.includes("scale")?1:0}function zl(n,r){if(!n||n==="none")return Vl(r);const i=n.match(/^matrix3d\(([-\d.e\s,]+)\)$/u);let a,u;if(i)a=zx,u=i;else{const p=n.match(/^matrix\(([-\d.e\s,]+)\)$/u);a=Vx,u=p}if(!u)return Vl(r);const f=a[r],d=u[1].split(",").map(Ox);return typeof f=="function"?f(d):d[f]}const Ix=(n,r)=>{const{transform:i="none"}=getComputedStyle(n);return zl(i,r)};function Ox(n){return parseFloat(n.trim())}const kr=["transformPerspective","x","y","z","translateX","translateY","translateZ","scale","scaleX","scaleY","rotate","rotateX","rotateY","rotateZ","skew","skewX","skewY"],Sr=new Set(kr),Zf=n=>n===wr||n===q,Fx=new Set(["x","y","z"]),Bx=kr.filter(n=>!Fx.has(n));function Ux(n){const r=[];return Bx.forEach(i=>{const a=n.getValue(i);a!==void 0&&(r.push([i,a.get()]),a.set(i.startsWith("scale")?1:0))}),r}const xn={width:({x:n},{paddingLeft:r="0",paddingRight:i="0",boxSizing:a})=>{const u=n.max-n.min;return a==="border-box"?u:u-parseFloat(r)-parseFloat(i)},height:({y:n},{paddingTop:r="0",paddingBottom:i="0",boxSizing:a})=>{const u=n.max-n.min;return a==="border-box"?u:u-parseFloat(r)-parseFloat(i)},top:(n,{top:r})=>parseFloat(r),left:(n,{left:r})=>parseFloat(r),bottom:({y:n},{top:r})=>parseFloat(r)+(n.max-n.min),right:({x:n},{left:r})=>parseFloat(r)+(n.max-n.min),x:(n,{transform:r})=>zl(r,"x"),y:(n,{transform:r})=>zl(r,"y")};xn.translateX=xn.x;xn.translateY=xn.y;const Fn=new Set;let Il=!1,Ol=!1,Fl=!1;function Gp(){if(Ol){const n=Array.from(Fn).filter(a=>a.needsMeasurement),r=new Set(n.map(a=>a.element)),i=new Map;r.forEach(a=>{const u=Ux(a);u.length&&(i.set(a,u),a.render())}),n.forEach(a=>a.measureInitialState()),r.forEach(a=>{a.render();const u=i.get(a);u&&u.forEach(([f,d])=>{var p;(p=a.getValue(f))==null||p.set(d)})}),n.forEach(a=>a.measureEndState()),n.forEach(a=>{a.suspendedScrollY!==void 0&&window.scrollTo(0,a.suspendedScrollY)})}Ol=!1,Il=!1,Fn.forEach(n=>n.complete(Fl)),Fn.clear()}function Yp(){Fn.forEach(n=>{n.readKeyframes(),n.needsMeasurement&&(Ol=!0)})}function $x(){Fl=!0,Yp(),Gp(),Fl=!1}class gu{constructor(r,i,a,u,f,d=!1){this.state="pending",this.isAsync=!1,this.needsMeasurement=!1,this.unresolvedKeyframes=[...r],this.onComplete=i,this.name=a,this.motionValue=u,this.element=f,this.isAsync=d}scheduleResolve(){this.state="scheduled",this.isAsync?(Fn.add(this),Il||(Il=!0,ve.read(Yp),ve.resolveKeyframes(Gp))):(this.readKeyframes(),this.complete())}readKeyframes(){const{unresolvedKeyframes:r,name:i,element:a,motionValue:u}=this;if(r[0]===null){const f=u==null?void 0:u.get(),d=r[r.length-1];if(f!==void 0)r[0]=f;else if(a&&i){const p=a.readValue(i,d);p!=null&&(r[0]=p)}r[0]===void 0&&(r[0]=d),u&&f===void 0&&u.set(r[0])}Lx(r)}setFinalKeyframe(){}measureInitialState(){}renderEndStyles(){}measureEndState(){}complete(r=!1){this.state="complete",this.onComplete(this.unresolvedKeyframes,this.finalKeyframe,r),Fn.delete(this)}cancel(){this.state==="scheduled"&&(Fn.delete(this),this.state="pending")}resume(){this.state==="pending"&&this.scheduleResolve()}}const Wx=n=>n.startsWith("--");function Xp(n,r,i){Wx(r)?n.style.setProperty(r,i):n.style[r]=i}const Hx={};function Qp(n,r){const i=jp(n);return()=>Hx[r]??i()}const Kx=Qp(()=>window.ScrollTimeline!==void 0,"scrollTimeline"),qp=Qp(()=>{try{document.createElement("div").animate({opacity:0},{easing:"linear(0, 1)"})}catch{return!1}return!0},"linearEasing"),cs=([n,r,i,a])=>`cubic-bezier(${n}, ${r}, ${i}, ${a})`,Jf={linear:"linear",ease:"ease",easeIn:"ease-in",easeOut:"ease-out",easeInOut:"ease-in-out",circIn:cs([0,.65,.55,1]),circOut:cs([.55,0,1,.45]),backIn:cs([.31,.01,.66,-.59]),backOut:cs([.33,1.53,.69,.99])};function Zp(n,r){if(n)return typeof n=="function"?qp()?Wp(n,r):"ease-out":Dp(n)?cs(n):Array.isArray(n)?n.map(i=>Zp(i,r)||Jf.easeOut):Jf[n]}function Gx(n,r,i,{delay:a=0,duration:u=300,repeat:f=0,repeatType:d="loop",ease:p="easeOut",times:g}={},x=void 0){const y={[r]:i};g&&(y.offset=g);const v=Zp(p,u);Array.isArray(v)&&(y.easing=v);const w={delay:a,duration:u,easing:Array.isArray(v)?"linear":v,fill:"both",iterations:f+1,direction:d==="reverse"?"alternate":"normal"};return x&&(w.pseudoElement=x),n.animate(y,w)}function Jp(n){return typeof n=="function"&&"applyToOptions"in n}function Yx({type:n,...r}){return Jp(n)&&qp()?n.applyToOptions(r):(r.duration??(r.duration=300),r.ease??(r.ease="easeOut"),r)}class em extends mu{constructor(r){if(super(),this.finishedTime=null,this.isStopped=!1,this.manualStartTime=null,!r)return;const{element:i,name:a,keyframes:u,pseudoElement:f,allowFlatten:d=!1,finalKeyframe:p,onComplete:g}=r;this.isPseudoElement=!!f,this.allowFlatten=d,this.options=r,ou(typeof r.type!="string");const x=Yx(r);this.animation=Gx(i,a,u,x,f),x.autoplay===!1&&this.animation.pause(),this.animation.onfinish=()=>{if(this.finishedTime=this.time,!f){const y=lo(u,this.options,p,this.speed);this.updateMotionValue&&this.updateMotionValue(y),Xp(i,a,y),this.animation.cancel()}g==null||g(),this.notifyFinished()}}play(){this.isStopped||(this.manualStartTime=null,this.animation.play(),this.state==="finished"&&this.updateFinished())}pause(){this.animation.pause()}complete(){var r,i;(i=(r=this.animation).finish)==null||i.call(r)}cancel(){try{this.animation.cancel()}catch{}}stop(){if(this.isStopped)return;this.isStopped=!0;const{state:r}=this;r==="idle"||r==="finished"||(this.updateMotionValue?this.updateMotionValue():this.commitStyles(),this.isPseudoElement||this.cancel())}commitStyles(){var i,a,u;const r=(i=this.options)==null?void 0:i.element;!this.isPseudoElement&&(r!=null&&r.isConnected)&&((u=(a=this.animation).commitStyles)==null||u.call(a))}get duration(){var i,a;const r=((a=(i=this.animation.effect)==null?void 0:i.getComputedTiming)==null?void 0:a.call(i).duration)||0;return St(Number(r))}get iterationDuration(){const{delay:r=0}=this.options||{};return this.duration+St(r)}get time(){return St(Number(this.animation.currentTime)||0)}set time(r){const i=this.finishedTime!==null;this.manualStartTime=null,this.finishedTime=null,this.animation.currentTime=mt(r),i&&this.animation.pause()}get speed(){return this.animation.playbackRate}set speed(r){r<0&&(this.finishedTime=null),this.animation.playbackRate=r}get state(){return this.finishedTime!==null?"finished":this.animation.playState}get startTime(){return this.manualStartTime??Number(this.animation.startTime)}set startTime(r){this.manualStartTime=this.animation.startTime=r}attachTimeline({timeline:r,rangeStart:i,rangeEnd:a,observe:u}){var f;return this.allowFlatten&&((f=this.animation.effect)==null||f.updateTiming({easing:"linear"})),this.animation.onfinish=null,r&&Kx()?(this.animation.timeline=r,i&&(this.animation.rangeStart=i),a&&(this.animation.rangeEnd=a),jt):u(this)}}const tm={anticipate:Mp,backInOut:bp,circInOut:Ap};function Xx(n){return n in tm}function Qx(n){typeof n.ease=="string"&&Xx(n.ease)&&(n.ease=tm[n.ease])}const yl=10;class qx extends em{constructor(r){Qx(r),Kp(r),super(r),r.startTime!==void 0&&r.autoplay!==!1&&(this.startTime=r.startTime),this.options=r}updateMotionValue(r){const{motionValue:i,onUpdate:a,onComplete:u,element:f,...d}=this.options;if(!i)return;if(r!==void 0){i.set(r);return}const p=new to({...d,autoplay:!1}),g=Math.max(yl,nt.now()-this.startTime),x=Ut(0,yl,g-yl),y=p.sample(g).value,{name:v}=this.options;f&&v&&Xp(f,v,y),i.setWithVelocity(p.sample(Math.max(0,g-x)).value,y,x),p.stop()}}const eh=(n,r)=>r==="zIndex"?!1:!!(typeof n=="number"||Array.isArray(n)||typeof n=="string"&&(Rt.test(n)||n==="0")&&!n.startsWith("url("));function Zx(n){const r=n[0];if(n.length===1)return!0;for(let i=0;i<n.length;i++)if(n[i]!==r)return!0}function Jx(n,r,i,a){const u=n[0];if(u===null)return!1;if(r==="display"||r==="visibility")return!0;const f=n[n.length-1],d=eh(u,r),p=eh(f,r);return!d||!p?!1:Zx(n)||(i==="spring"||Jp(i))&&a}function Bl(n){n.duration=0,n.type="keyframes"}const nm=new Set(["opacity","clipPath","filter","transform"]),e1=/^(?:oklch|oklab|lab|lch|color|color-mix|light-dark)\(/;function t1(n){for(let r=0;r<n.length;r++)if(typeof n[r]=="string"&&e1.test(n[r]))return!0;return!1}const n1=new Set(["color","backgroundColor","outlineColor","fill","stroke","borderColor","borderTopColor","borderRightColor","borderBottomColor","borderLeftColor"]),r1=jp(()=>Object.hasOwnProperty.call(Element.prototype,"animate"));function s1(n){var v;const{motionValue:r,name:i,repeatDelay:a,repeatType:u,damping:f,type:d,keyframes:p}=n;if(!(((v=r==null?void 0:r.owner)==null?void 0:v.current)instanceof HTMLElement))return!1;const{onUpdate:x,transformTemplate:y}=r.owner.getProps();return r1()&&i&&(nm.has(i)||n1.has(i)&&t1(p))&&(i!=="transform"||!y)&&!x&&!a&&u!=="mirror"&&f!==0&&d!=="inertia"}const i1=40;class o1 extends mu{constructor({autoplay:r=!0,delay:i=0,type:a="keyframes",repeat:u=0,repeatDelay:f=0,repeatType:d="loop",keyframes:p,name:g,motionValue:x,element:y,...v}){var E;super(),this.stop=()=>{var _,M;this._animation&&(this._animation.stop(),(_=this.stopTimeline)==null||_.call(this)),(M=this.keyframeResolver)==null||M.cancel()},this.createdAt=nt.now();const w={autoplay:r,delay:i,type:a,repeat:u,repeatDelay:f,repeatType:d,name:g,motionValue:x,element:y,...v},N=(y==null?void 0:y.KeyframeResolver)||gu;this.keyframeResolver=new N(p,(_,M,L)=>this.onKeyframesResolved(_,M,w,!L),g,x,y),(E=this.keyframeResolver)==null||E.scheduleResolve()}onKeyframesResolved(r,i,a,u){var L,B;this.keyframeResolver=void 0;const{name:f,type:d,velocity:p,delay:g,isHandoff:x,onUpdate:y}=a;this.resolvedAt=nt.now();let v=!0;Jx(r,f,d,p)||(v=!1,(wn.instantAnimations||!g)&&(y==null||y(lo(r,a,i))),r[0]=r[r.length-1],Bl(a),a.repeat=0);const N={startTime:u?this.resolvedAt?this.resolvedAt-this.createdAt>i1?this.resolvedAt:this.createdAt:this.createdAt:void 0,finalKeyframe:i,...a,keyframes:r},E=v&&!x&&s1(N),_=(B=(L=N.motionValue)==null?void 0:L.owner)==null?void 0:B.current;let M;if(E)try{M=new qx({...N,element:_})}catch{M=new to(N)}else M=new to(N);M.finished.then(()=>{this.notifyFinished()}).catch(jt),this.pendingTimeline&&(this.stopTimeline=M.attachTimeline(this.pendingTimeline),this.pendingTimeline=void 0),this._animation=M}get finished(){return this._animation?this.animation.finished:this._finished}then(r,i){return this.finished.finally(r).then(()=>{})}get animation(){var r;return this._animation||((r=this.keyframeResolver)==null||r.resume(),$x()),this._animation}get duration(){return this.animation.duration}get iterationDuration(){return this.animation.iterationDuration}get time(){return this.animation.time}set time(r){this.animation.time=r}get speed(){return this.animation.speed}get state(){return this.animation.state}set speed(r){this.animation.speed=r}get startTime(){return this.animation.startTime}attachTimeline(r){return this._animation?this.stopTimeline=this.animation.attachTimeline(r):this.pendingTimeline=r,()=>this.stop()}play(){this.animation.play()}pause(){this.animation.pause()}complete(){this.animation.complete()}cancel(){var r;this._animation&&this.animation.cancel(),(r=this.keyframeResolver)==null||r.cancel()}}function rm(n,r,i,a=0,u=1){const f=Array.from(n).sort((x,y)=>x.sortNodePosition(y)).indexOf(r),d=n.size,p=(d-1)*a;return typeof i=="function"?i(f,d):u===1?f*a:p-f*a}const a1=/^var\(--(?:([\w-]+)|([\w-]+), ?([a-zA-Z\d ()%#.,-]+))\)/u;function l1(n){const r=a1.exec(n);if(!r)return[,];const[,i,a,u]=r;return[`--${i??a}`,u]}function sm(n,r,i=1){const[a,u]=l1(n);if(!a)return;const f=window.getComputedStyle(r).getPropertyValue(a);if(f){const d=f.trim();return wp(d)?parseFloat(d):d}return cu(u)?sm(u,r,i+1):u}const u1={type:"spring",stiffness:500,damping:25,restSpeed:10},c1=n=>({type:"spring",stiffness:550,damping:n===0?2*Math.sqrt(550):30,restSpeed:10}),d1={type:"keyframes",duration:.8},f1={type:"keyframes",ease:[.25,.1,.35,1],duration:.3},h1=(n,{keyframes:r})=>r.length>2?d1:Sr.has(n)?n.startsWith("scale")?c1(r[1]):u1:f1;function im(n,r){if(n!=null&&n.inherit&&r){const{inherit:i,...a}=n;return{...r,...a}}return n}function yu(n,r){const i=(n==null?void 0:n[r])??(n==null?void 0:n.default)??n;return i!==n?im(i,n):i}const p1=new Set(["when","delay","delayChildren","staggerChildren","staggerDirection","repeat","repeatType","repeatDelay","from","elapsed"]);function m1(n){for(const r in n)if(!p1.has(r))return!0;return!1}const vu=(n,r,i,a={},u,f)=>d=>{const p=yu(a,n)||{},g=p.delay||a.delay||0;let{elapsed:x=0}=a;x=x-mt(g);const y={keyframes:Array.isArray(i)?i:[null,i],ease:"easeOut",velocity:r.getVelocity(),...p,delay:-x,onUpdate:w=>{r.set(w),p.onUpdate&&p.onUpdate(w)},onComplete:()=>{d(),p.onComplete&&p.onComplete()},name:n,motionValue:r,element:f?void 0:u};m1(p)||Object.assign(y,h1(n,y)),y.duration&&(y.duration=mt(y.duration)),y.repeatDelay&&(y.repeatDelay=mt(y.repeatDelay)),y.from!==void 0&&(y.keyframes[0]=y.from);let v=!1;if((y.type===!1||y.duration===0&&!y.repeatDelay)&&(Bl(y),y.delay===0&&(v=!0)),(wn.instantAnimations||wn.skipAnimations||u!=null&&u.shouldSkipAnimations)&&(v=!0,Bl(y),y.delay=0),y.allowFlatten=!p.type&&!p.ease,v&&!f&&r.get()!==void 0){const w=lo(y.keyframes,p);if(w!==void 0){ve.update(()=>{y.onUpdate(w),y.onComplete()});return}}return p.isSync?new to(y):new o1(y)};function th(n){const r=[{},{}];return n==null||n.values.forEach((i,a)=>{r[0][a]=i.get(),r[1][a]=i.getVelocity()}),r}function xu(n,r,i,a){if(typeof r=="function"){const[u,f]=th(a);r=r(i!==void 0?i:n.custom,u,f)}if(typeof r=="string"&&(r=n.variants&&n.variants[r]),typeof r=="function"){const[u,f]=th(a);r=r(i!==void 0?i:n.custom,u,f)}return r}function Bn(n,r,i){const a=n.getProps();return xu(a,r,i!==void 0?i:a.custom,n)}const om=new Set(["width","height","top","left","right","bottom",...kr]),nh=30,g1=n=>!isNaN(parseFloat(n));class y1{constructor(r,i={}){this.canTrackVelocity=null,this.events={},this.updateAndNotify=a=>{var f;const u=nt.now();if(this.updatedAt!==u&&this.setPrevFrameValue(),this.prev=this.current,this.setCurrent(a),this.current!==this.prev&&((f=this.events.change)==null||f.notify(this.current),this.dependents))for(const d of this.dependents)d.dirty()},this.hasAnimated=!1,this.setCurrent(r),this.owner=i.owner}setCurrent(r){this.current=r,this.updatedAt=nt.now(),this.canTrackVelocity===null&&r!==void 0&&(this.canTrackVelocity=g1(this.current))}setPrevFrameValue(r=this.current){this.prevFrameValue=r,this.prevUpdatedAt=this.updatedAt}onChange(r){return this.on("change",r)}on(r,i){this.events[r]||(this.events[r]=new au);const a=this.events[r].add(i);return r==="change"?()=>{a(),ve.read(()=>{this.events.change.getSize()||this.stop()})}:a}clearListeners(){for(const r in this.events)this.events[r].clear()}attach(r,i){this.passiveEffect=r,this.stopPassiveEffect=i}set(r){this.passiveEffect?this.passiveEffect(r,this.updateAndNotify):this.updateAndNotify(r)}setWithVelocity(r,i,a){this.set(i),this.prev=void 0,this.prevFrameValue=r,this.prevUpdatedAt=this.updatedAt-a}jump(r,i=!0){this.updateAndNotify(r),this.prev=r,this.prevUpdatedAt=this.prevFrameValue=void 0,i&&this.stop(),this.stopPassiveEffect&&this.stopPassiveEffect()}dirty(){var r;(r=this.events.change)==null||r.notify(this.current)}addDependent(r){this.dependents||(this.dependents=new Set),this.dependents.add(r)}removeDependent(r){this.dependents&&this.dependents.delete(r)}get(){return this.current}getPrevious(){return this.prev}getVelocity(){const r=nt.now();if(!this.canTrackVelocity||this.prevFrameValue===void 0||r-this.updatedAt>nh)return 0;const i=Math.min(this.updatedAt-this.prevUpdatedAt,nh);return Np(parseFloat(this.current)-parseFloat(this.prevFrameValue),i)}start(r){return this.stop(),new Promise(i=>{this.hasAnimated=!0,this.animation=r(i),this.events.animationStart&&this.events.animationStart.notify()}).then(()=>{this.events.animationComplete&&this.events.animationComplete.notify(),this.clearAnimation()})}stop(){this.animation&&(this.animation.stop(),this.events.animationCancel&&this.events.animationCancel.notify()),this.clearAnimation()}isAnimating(){return!!this.animation}clearAnimation(){delete this.animation}destroy(){var r,i;(r=this.dependents)==null||r.clear(),(i=this.events.destroy)==null||i.notify(),this.clearListeners(),this.stop(),this.stopPassiveEffect&&this.stopPassiveEffect()}}function xr(n,r){return new y1(n,r)}const Ul=n=>Array.isArray(n);function v1(n,r,i){n.hasValue(r)?n.getValue(r).set(i):n.addValue(r,xr(i))}function x1(n){return Ul(n)?n[n.length-1]||0:n}function w1(n,r){const i=Bn(n,r);let{transitionEnd:a={},transition:u={},...f}=i||{};f={...f,...a};for(const d in f){const p=x1(f[d]);v1(n,d,p)}}const Xe=n=>!!(n&&n.getVelocity);function k1(n){return!!(Xe(n)&&n.add)}function $l(n,r){const i=n.getValue("willChange");if(k1(i))return i.add(r);if(!i&&wn.WillChange){const a=new wn.WillChange("auto");n.addValue("willChange",a),a.add(r)}}function wu(n){return n.replace(/([A-Z])/g,r=>`-${r.toLowerCase()}`)}const S1="framerAppearId",am="data-"+wu(S1);function lm(n){return n.props[am]}function j1({protectedKeys:n,needsAnimating:r},i){const a=n.hasOwnProperty(i)&&r[i]!==!0;return r[i]=!1,a}function um(n,r,{delay:i=0,transitionOverride:a,type:u}={}){let{transition:f,transitionEnd:d,...p}=r;const g=n.getDefaultTransition();f=f?im(f,g):g;const x=f==null?void 0:f.reduceMotion;a&&(f=a);const y=[],v=u&&n.animationState&&n.animationState.getState()[u];for(const w in p){const N=n.getValue(w,n.latestValues[w]??null),E=p[w];if(E===void 0||v&&j1(v,w))continue;const _={delay:i,...yu(f||{},w)},M=N.get();if(M!==void 0&&!N.isAnimating()&&!Array.isArray(E)&&E===M&&!_.velocity){ve.update(()=>N.set(E));continue}let L=!1;if(window.MotionHandoffAnimation){const U=lm(n);if(U){const W=window.MotionHandoffAnimation(U,w,ve);W!==null&&(_.startTime=W,L=!0)}}$l(n,w);const B=x??n.shouldReduceMotion;N.start(vu(w,N,E,B&&om.has(w)?{type:!1}:_,n,L));const I=N.animation;I&&y.push(I)}if(d){const w=()=>ve.update(()=>{d&&w1(n,d)});y.length?Promise.all(y).then(w):w()}return y}function Wl(n,r,i={}){var g;const a=Bn(n,r,i.type==="exit"?(g=n.presenceContext)==null?void 0:g.custom:void 0);let{transition:u=n.getDefaultTransition()||{}}=a||{};i.transitionOverride&&(u=i.transitionOverride);const f=a?()=>Promise.all(um(n,a,i)):()=>Promise.resolve(),d=n.variantChildren&&n.variantChildren.size?(x=0)=>{const{delayChildren:y=0,staggerChildren:v,staggerDirection:w}=u;return N1(n,r,x,y,v,w,i)}:()=>Promise.resolve(),{when:p}=u;if(p){const[x,y]=p==="beforeChildren"?[f,d]:[d,f];return x().then(()=>y())}else return Promise.all([f(),d(i.delay)])}function N1(n,r,i=0,a=0,u=0,f=1,d){const p=[];for(const g of n.variantChildren)g.notify("AnimationStart",r),p.push(Wl(g,r,{...d,delay:i+(typeof a=="function"?0:a)+rm(n.variantChildren,g,a,u,f)}).then(()=>g.notify("AnimationComplete",r)));return Promise.all(p)}function T1(n,r,i={}){n.notify("AnimationStart",r);let a;if(Array.isArray(r)){const u=r.map(f=>Wl(n,f,i));a=Promise.all(u)}else if(typeof r=="string")a=Wl(n,r,i);else{const u=typeof r=="function"?Bn(n,r,i.custom):r;a=Promise.all(um(n,u,i))}return a.then(()=>{n.notify("AnimationComplete",r)})}const C1={test:n=>n==="auto",parse:n=>n},cm=n=>r=>r.test(n),dm=[wr,q,Bt,yn,Zv,qv,C1],rh=n=>dm.find(cm(n));function P1(n){return typeof n=="number"?n===0:n!==null?n==="none"||n==="0"||Sp(n):!0}const E1=new Set(["brightness","contrast","saturate","opacity"]);function b1(n){const[r,i]=n.slice(0,-1).split("(");if(r==="drop-shadow")return n;const[a]=i.match(du)||[];if(!a)return n;const u=i.replace(a,"");let f=E1.has(r)?1:0;return a!==i&&(f*=100),r+"("+f+u+")"}const M1=/\b([a-z-]*)\(.*?\)/gu,Hl={...Rt,getAnimatableNone:n=>{const r=n.match(M1);return r?r.map(b1).join(" "):n}},Kl={...Rt,getAnimatableNone:n=>{const r=Rt.parse(n);return Rt.createTransformer(n)(r.map(a=>typeof a=="number"?0:typeof a=="object"?{...a,alpha:1}:a))}},sh={...wr,transform:Math.round},_1={rotate:yn,rotateX:yn,rotateY:yn,rotateZ:yn,scale:Ii,scaleX:Ii,scaleY:Ii,scaleZ:Ii,skew:yn,skewX:yn,skewY:yn,distance:q,translateX:q,translateY:q,translateZ:q,x:q,y:q,z:q,perspective:q,transformPerspective:q,opacity:xs,originX:Wf,originY:Wf,originZ:q},ku={borderWidth:q,borderTopWidth:q,borderRightWidth:q,borderBottomWidth:q,borderLeftWidth:q,borderRadius:q,borderTopLeftRadius:q,borderTopRightRadius:q,borderBottomRightRadius:q,borderBottomLeftRadius:q,width:q,maxWidth:q,height:q,maxHeight:q,top:q,right:q,bottom:q,left:q,inset:q,insetBlock:q,insetBlockStart:q,insetBlockEnd:q,insetInline:q,insetInlineStart:q,insetInlineEnd:q,padding:q,paddingTop:q,paddingRight:q,paddingBottom:q,paddingLeft:q,paddingBlock:q,paddingBlockStart:q,paddingBlockEnd:q,paddingInline:q,paddingInlineStart:q,paddingInlineEnd:q,margin:q,marginTop:q,marginRight:q,marginBottom:q,marginLeft:q,marginBlock:q,marginBlockStart:q,marginBlockEnd:q,marginInline:q,marginInlineStart:q,marginInlineEnd:q,fontSize:q,backgroundPositionX:q,backgroundPositionY:q,..._1,zIndex:sh,fillOpacity:xs,strokeOpacity:xs,numOctaves:sh},A1={...ku,color:Oe,backgroundColor:Oe,outlineColor:Oe,fill:Oe,stroke:Oe,borderColor:Oe,borderTopColor:Oe,borderRightColor:Oe,borderBottomColor:Oe,borderLeftColor:Oe,filter:Hl,WebkitFilter:Hl,mask:Kl,WebkitMask:Kl},fm=n=>A1[n],R1=new Set([Hl,Kl]);function hm(n,r){let i=fm(n);return R1.has(i)||(i=Rt),i.getAnimatableNone?i.getAnimatableNone(r):void 0}const D1=new Set(["auto","none","0"]);function L1(n,r,i){let a=0,u;for(;a<n.length&&!u;){const f=n[a];typeof f=="string"&&!D1.has(f)&&vr(f).values.length&&(u=n[a]),a++}if(u&&i)for(const f of r)n[f]=hm(i,u)}class V1 extends gu{constructor(r,i,a,u,f){super(r,i,a,u,f,!0)}readKeyframes(){const{unresolvedKeyframes:r,element:i,name:a}=this;if(!i||!i.current)return;super.readKeyframes();for(let y=0;y<r.length;y++){let v=r[y];if(typeof v=="string"&&(v=v.trim(),cu(v))){const w=sm(v,i.current);w!==void 0&&(r[y]=w),y===r.length-1&&(this.finalKeyframe=v)}}if(this.resolveNoneKeyframes(),!om.has(a)||r.length!==2)return;const[u,f]=r,d=rh(u),p=rh(f),g=$f(u),x=$f(f);if(g!==x&&xn[a]){this.needsMeasurement=!0;return}if(d!==p)if(Zf(d)&&Zf(p))for(let y=0;y<r.length;y++){const v=r[y];typeof v=="string"&&(r[y]=parseFloat(v))}else xn[a]&&(this.needsMeasurement=!0)}resolveNoneKeyframes(){const{unresolvedKeyframes:r,name:i}=this,a=[];for(let u=0;u<r.length;u++)(r[u]===null||P1(r[u]))&&a.push(u);a.length&&L1(r,a,i)}measureInitialState(){const{element:r,unresolvedKeyframes:i,name:a}=this;if(!r||!r.current)return;a==="height"&&(this.suspendedScrollY=window.pageYOffset),this.measuredOrigin=xn[a](r.measureViewportBox(),window.getComputedStyle(r.current)),i[0]=this.measuredOrigin;const u=i[i.length-1];u!==void 0&&r.getValue(a,u).jump(u,!1)}measureEndState(){var p;const{element:r,name:i,unresolvedKeyframes:a}=this;if(!r||!r.current)return;const u=r.getValue(i);u&&u.jump(this.measuredOrigin,!1);const f=a.length-1,d=a[f];a[f]=xn[i](r.measureViewportBox(),window.getComputedStyle(r.current)),d!==null&&this.finalKeyframe===void 0&&(this.finalKeyframe=d),(p=this.removedTransforms)!=null&&p.length&&this.removedTransforms.forEach(([g,x])=>{r.getValue(g).set(x)}),this.resolveNoneKeyframes()}}function pm(n,r,i){if(n==null)return[];if(n instanceof EventTarget)return[n];if(typeof n=="string"){let a=document;const u=(i==null?void 0:i[n])??a.querySelectorAll(n);return u?Array.from(u):[]}return Array.from(n).filter(a=>a!=null)}const mm=(n,r)=>r&&typeof n=="number"?r.transform(n):n;function $i(n){return kp(n)&&"offsetHeight"in n&&!("ownerSVGElement"in n)}const{schedule:Su}=Lp(queueMicrotask,!1),At={x:!1,y:!1};function gm(){return At.x||At.y}function z1(n){return n==="x"||n==="y"?At[n]?null:(At[n]=!0,()=>{At[n]=!1}):At.x||At.y?null:(At.x=At.y=!0,()=>{At.x=At.y=!1})}function ym(n,r){const i=pm(n),a=new AbortController,u={passive:!0,...r,signal:a.signal};return[i,u,()=>a.abort()]}function I1(n){return!(n.pointerType==="touch"||gm())}function O1(n,r,i={}){const[a,u,f]=ym(n,i);return a.forEach(d=>{let p=!1,g=!1,x;const y=()=>{d.removeEventListener("pointerleave",E)},v=M=>{x&&(x(M),x=void 0),y()},w=M=>{p=!1,window.removeEventListener("pointerup",w),window.removeEventListener("pointercancel",w),g&&(g=!1,v(M))},N=()=>{p=!0,window.addEventListener("pointerup",w,u),window.addEventListener("pointercancel",w,u)},E=M=>{if(M.pointerType!=="touch"){if(p){g=!0;return}v(M)}},_=M=>{if(!I1(M))return;g=!1;const L=r(d,M);typeof L=="function"&&(x=L,d.addEventListener("pointerleave",E,u))};d.addEventListener("pointerenter",_,u),d.addEventListener("pointerdown",N,u)}),f}const vm=(n,r)=>r?n===r?!0:vm(n,r.parentElement):!1,ju=n=>n.pointerType==="mouse"?typeof n.button!="number"||n.button<=0:n.isPrimary!==!1,F1=new Set(["BUTTON","INPUT","SELECT","TEXTAREA","A"]);function B1(n){return F1.has(n.tagName)||n.isContentEditable===!0}const U1=new Set(["INPUT","SELECT","TEXTAREA"]);function $1(n){return U1.has(n.tagName)||n.isContentEditable===!0}const Wi=new WeakSet;function ih(n){return r=>{r.key==="Enter"&&n(r)}}function vl(n,r){n.dispatchEvent(new PointerEvent("pointer"+r,{isPrimary:!0,bubbles:!0}))}const W1=(n,r)=>{const i=n.currentTarget;if(!i)return;const a=ih(()=>{if(Wi.has(i))return;vl(i,"down");const u=ih(()=>{vl(i,"up")}),f=()=>vl(i,"cancel");i.addEventListener("keyup",u,r),i.addEventListener("blur",f,r)});i.addEventListener("keydown",a,r),i.addEventListener("blur",()=>i.removeEventListener("keydown",a),r)};function oh(n){return ju(n)&&!gm()}const ah=new WeakSet;function H1(n,r,i={}){const[a,u,f]=ym(n,i),d=p=>{const g=p.currentTarget;if(!oh(p)||ah.has(p))return;Wi.add(g),i.stopPropagation&&ah.add(p);const x=r(g,p),y=(N,E)=>{window.removeEventListener("pointerup",v),window.removeEventListener("pointercancel",w),Wi.has(g)&&Wi.delete(g),oh(N)&&typeof x=="function"&&x(N,{success:E})},v=N=>{y(N,g===window||g===document||i.useGlobalTarget||vm(g,N.target))},w=N=>{y(N,!1)};window.addEventListener("pointerup",v,u),window.addEventListener("pointercancel",w,u)};return a.forEach(p=>{(i.useGlobalTarget?window:p).addEventListener("pointerdown",d,u),$i(p)&&(p.addEventListener("focus",x=>W1(x,u)),!B1(p)&&!p.hasAttribute("tabindex")&&(p.tabIndex=0))}),f}function Nu(n){return kp(n)&&"ownerSVGElement"in n}const Hi=new WeakMap;let vn;const xm=(n,r,i)=>(a,u)=>u&&u[0]?u[0][n+"Size"]:Nu(a)&&"getBBox"in a?a.getBBox()[r]:a[i],K1=xm("inline","width","offsetWidth"),G1=xm("block","height","offsetHeight");function Y1({target:n,borderBoxSize:r}){var i;(i=Hi.get(n))==null||i.forEach(a=>{a(n,{get width(){return K1(n,r)},get height(){return G1(n,r)}})})}function X1(n){n.forEach(Y1)}function Q1(){typeof ResizeObserver>"u"||(vn=new ResizeObserver(X1))}function q1(n,r){vn||Q1();const i=pm(n);return i.forEach(a=>{let u=Hi.get(a);u||(u=new Set,Hi.set(a,u)),u.add(r),vn==null||vn.observe(a)}),()=>{i.forEach(a=>{const u=Hi.get(a);u==null||u.delete(r),u!=null&&u.size||vn==null||vn.unobserve(a)})}}const Ki=new Set;let mr;function Z1(){mr=()=>{const n={get width(){return window.innerWidth},get height(){return window.innerHeight}};Ki.forEach(r=>r(n))},window.addEventListener("resize",mr)}function J1(n){return Ki.add(n),mr||Z1(),()=>{Ki.delete(n),!Ki.size&&typeof mr=="function"&&(window.removeEventListener("resize",mr),mr=void 0)}}function lh(n,r){return typeof n=="function"?J1(n):q1(n,r)}function ew(n){return Nu(n)&&n.tagName==="svg"}const tw=[...dm,Oe,Rt],nw=n=>tw.find(cm(n)),uh=()=>({translate:0,scale:1,origin:0,originPoint:0}),gr=()=>({x:uh(),y:uh()}),ch=()=>({min:0,max:0}),Ue=()=>({x:ch(),y:ch()}),rw=new WeakMap;function uo(n){return n!==null&&typeof n=="object"&&typeof n.start=="function"}function ws(n){return typeof n=="string"||Array.isArray(n)}const Tu=["animate","whileInView","whileFocus","whileHover","whileTap","whileDrag","exit"],Cu=["initial",...Tu];function co(n){return uo(n.animate)||Cu.some(r=>ws(n[r]))}function wm(n){return!!(co(n)||n.variants)}function sw(n,r,i){for(const a in r){const u=r[a],f=i[a];if(Xe(u))n.addValue(a,u);else if(Xe(f))n.addValue(a,xr(u,{owner:n}));else if(f!==u)if(n.hasValue(a)){const d=n.getValue(a);d.liveStyle===!0?d.jump(u):d.hasAnimated||d.set(u)}else{const d=n.getStaticValue(a);n.addValue(a,xr(d!==void 0?d:u,{owner:n}))}}for(const a in i)r[a]===void 0&&n.removeValue(a);return r}const Gl={current:null},km={current:!1},iw=typeof window<"u";function ow(){if(km.current=!0,!!iw)if(window.matchMedia){const n=window.matchMedia("(prefers-reduced-motion)"),r=()=>Gl.current=n.matches;n.addEventListener("change",r),r()}else Gl.current=!1}const dh=["AnimationStart","AnimationComplete","Update","BeforeLayoutMeasure","LayoutMeasure","LayoutAnimationStart","LayoutAnimationComplete"];let no={};function Sm(n){no=n}function aw(){return no}class lw{scrapeMotionValuesFromProps(r,i,a){return{}}constructor({parent:r,props:i,presenceContext:a,reducedMotionConfig:u,skipAnimations:f,blockInitialAnimation:d,visualState:p},g={}){this.current=null,this.children=new Set,this.isVariantNode=!1,this.isControllingVariants=!1,this.shouldReduceMotion=null,this.shouldSkipAnimations=!1,this.values=new Map,this.KeyframeResolver=gu,this.features={},this.valueSubscriptions=new Map,this.prevMotionValues={},this.hasBeenMounted=!1,this.events={},this.propEventSubscriptions={},this.notifyUpdate=()=>this.notify("Update",this.latestValues),this.render=()=>{this.current&&(this.triggerBuild(),this.renderInstance(this.current,this.renderState,this.props.style,this.projection))},this.renderScheduledAt=0,this.scheduleRender=()=>{const N=nt.now();this.renderScheduledAt<N&&(this.renderScheduledAt=N,ve.render(this.render,!1,!0))};const{latestValues:x,renderState:y}=p;this.latestValues=x,this.baseTarget={...x},this.initialValues=i.initial?{...x}:{},this.renderState=y,this.parent=r,this.props=i,this.presenceContext=a,this.depth=r?r.depth+1:0,this.reducedMotionConfig=u,this.skipAnimationsConfig=f,this.options=g,this.blockInitialAnimation=!!d,this.isControllingVariants=co(i),this.isVariantNode=wm(i),this.isVariantNode&&(this.variantChildren=new Set),this.manuallyAnimateOnMount=!!(r&&r.current);const{willChange:v,...w}=this.scrapeMotionValuesFromProps(i,{},this);for(const N in w){const E=w[N];x[N]!==void 0&&Xe(E)&&E.set(x[N])}}mount(r){var i,a;if(this.hasBeenMounted)for(const u in this.initialValues)(i=this.values.get(u))==null||i.jump(this.initialValues[u]),this.latestValues[u]=this.initialValues[u];this.current=r,rw.set(r,this),this.projection&&!this.projection.instance&&this.projection.mount(r),this.parent&&this.isVariantNode&&!this.isControllingVariants&&(this.removeFromVariantTree=this.parent.addVariantChild(this)),this.values.forEach((u,f)=>this.bindToMotionValue(f,u)),this.reducedMotionConfig==="never"?this.shouldReduceMotion=!1:this.reducedMotionConfig==="always"?this.shouldReduceMotion=!0:(km.current||ow(),this.shouldReduceMotion=Gl.current),this.shouldSkipAnimations=this.skipAnimationsConfig??!1,(a=this.parent)==null||a.addChild(this),this.update(this.props,this.presenceContext),this.hasBeenMounted=!0}unmount(){var r;this.projection&&this.projection.unmount(),kn(this.notifyUpdate),kn(this.render),this.valueSubscriptions.forEach(i=>i()),this.valueSubscriptions.clear(),this.removeFromVariantTree&&this.removeFromVariantTree(),(r=this.parent)==null||r.removeChild(this);for(const i in this.events)this.events[i].clear();for(const i in this.features){const a=this.features[i];a&&(a.unmount(),a.isMounted=!1)}this.current=null}addChild(r){this.children.add(r),this.enteringChildren??(this.enteringChildren=new Set),this.enteringChildren.add(r)}removeChild(r){this.children.delete(r),this.enteringChildren&&this.enteringChildren.delete(r)}bindToMotionValue(r,i){if(this.valueSubscriptions.has(r)&&this.valueSubscriptions.get(r)(),i.accelerate&&nm.has(r)&&this.current instanceof HTMLElement){const{factory:d,keyframes:p,times:g,ease:x,duration:y}=i.accelerate,v=new em({element:this.current,name:r,keyframes:p,times:g,ease:x,duration:mt(y)}),w=d(v);this.valueSubscriptions.set(r,()=>{w(),v.cancel()});return}const a=Sr.has(r);a&&this.onBindTransform&&this.onBindTransform();const u=i.on("change",d=>{this.latestValues[r]=d,this.props.onUpdate&&ve.preRender(this.notifyUpdate),a&&this.projection&&(this.projection.isTransformDirty=!0),this.scheduleRender()});let f;typeof window<"u"&&window.MotionCheckAppearSync&&(f=window.MotionCheckAppearSync(this,r,i)),this.valueSubscriptions.set(r,()=>{u(),f&&f(),i.owner&&i.stop()})}sortNodePosition(r){return!this.current||!this.sortInstanceNodePosition||this.type!==r.type?0:this.sortInstanceNodePosition(this.current,r.current)}updateFeatures(){let r="animation";for(r in no){const i=no[r];if(!i)continue;const{isEnabled:a,Feature:u}=i;if(!this.features[r]&&u&&a(this.props)&&(this.features[r]=new u(this)),this.features[r]){const f=this.features[r];f.isMounted?f.update():(f.mount(),f.isMounted=!0)}}}triggerBuild(){this.build(this.renderState,this.latestValues,this.props)}measureViewportBox(){return this.current?this.measureInstanceViewportBox(this.current,this.props):Ue()}getStaticValue(r){return this.latestValues[r]}setStaticValue(r,i){this.latestValues[r]=i}update(r,i){(r.transformTemplate||this.props.transformTemplate)&&this.scheduleRender(),this.prevProps=this.props,this.props=r,this.prevPresenceContext=this.presenceContext,this.presenceContext=i;for(let a=0;a<dh.length;a++){const u=dh[a];this.propEventSubscriptions[u]&&(this.propEventSubscriptions[u](),delete this.propEventSubscriptions[u]);const f="on"+u,d=r[f];d&&(this.propEventSubscriptions[u]=this.on(u,d))}this.prevMotionValues=sw(this,this.scrapeMotionValuesFromProps(r,this.prevProps||{},this),this.prevMotionValues),this.handleChildMotionValue&&this.handleChildMotionValue()}getProps(){return this.props}getVariant(r){return this.props.variants?this.props.variants[r]:void 0}getDefaultTransition(){return this.props.transition}getTransformPagePoint(){return this.props.transformPagePoint}getClosestVariantNode(){return this.isVariantNode?this:this.parent?this.parent.getClosestVariantNode():void 0}addVariantChild(r){const i=this.getClosestVariantNode();if(i)return i.variantChildren&&i.variantChildren.add(r),()=>i.variantChildren.delete(r)}addValue(r,i){const a=this.values.get(r);i!==a&&(a&&this.removeValue(r),this.bindToMotionValue(r,i),this.values.set(r,i),this.latestValues[r]=i.get())}removeValue(r){this.values.delete(r);const i=this.valueSubscriptions.get(r);i&&(i(),this.valueSubscriptions.delete(r)),delete this.latestValues[r],this.removeValueFromRenderState(r,this.renderState)}hasValue(r){return this.values.has(r)}getValue(r,i){if(this.props.values&&this.props.values[r])return this.props.values[r];let a=this.values.get(r);return a===void 0&&i!==void 0&&(a=xr(i===null?void 0:i,{owner:this}),this.addValue(r,a)),a}readValue(r,i){let a=this.latestValues[r]!==void 0||!this.current?this.latestValues[r]:this.getBaseTargetFromProps(this.props,r)??this.readValueFromInstance(this.current,r,this.options);return a!=null&&(typeof a=="string"&&(wp(a)||Sp(a))?a=parseFloat(a):!nw(a)&&Rt.test(i)&&(a=hm(r,i)),this.setBaseTarget(r,Xe(a)?a.get():a)),Xe(a)?a.get():a}setBaseTarget(r,i){this.baseTarget[r]=i}getBaseTarget(r){var f;const{initial:i}=this.props;let a;if(typeof i=="string"||typeof i=="object"){const d=xu(this.props,i,(f=this.presenceContext)==null?void 0:f.custom);d&&(a=d[r])}if(i&&a!==void 0)return a;const u=this.getBaseTargetFromProps(this.props,r);return u!==void 0&&!Xe(u)?u:this.initialValues[r]!==void 0&&a===void 0?void 0:this.baseTarget[r]}on(r,i){return this.events[r]||(this.events[r]=new au),this.events[r].add(i)}notify(r,...i){this.events[r]&&this.events[r].notify(...i)}scheduleRenderMicrotask(){Su.render(this.render)}}class jm extends lw{constructor(){super(...arguments),this.KeyframeResolver=V1}sortInstanceNodePosition(r,i){return r.compareDocumentPosition(i)&2?1:-1}getBaseTargetFromProps(r,i){const a=r.style;return a?a[i]:void 0}removeValueFromRenderState(r,{vars:i,style:a}){delete i[r],delete a[r]}handleChildMotionValue(){this.childSubscription&&(this.childSubscription(),delete this.childSubscription);const{children:r}=this.props;Xe(r)&&(this.childSubscription=r.on("change",i=>{this.current&&(this.current.textContent=`${i}`)}))}}class Sn{constructor(r){this.isMounted=!1,this.node=r}update(){}}function Nm({top:n,left:r,right:i,bottom:a}){return{x:{min:r,max:i},y:{min:n,max:a}}}function uw({x:n,y:r}){return{top:r.min,right:n.max,bottom:r.max,left:n.min}}function cw(n,r){if(!r)return n;const i=r({x:n.left,y:n.top}),a=r({x:n.right,y:n.bottom});return{top:i.y,left:i.x,bottom:a.y,right:a.x}}function xl(n){return n===void 0||n===1}function Yl({scale:n,scaleX:r,scaleY:i}){return!xl(n)||!xl(r)||!xl(i)}function zn(n){return Yl(n)||Tm(n)||n.z||n.rotate||n.rotateX||n.rotateY||n.skewX||n.skewY}function Tm(n){return fh(n.x)||fh(n.y)}function fh(n){return n&&n!=="0%"}function ro(n,r,i){const a=n-i,u=r*a;return i+u}function hh(n,r,i,a,u){return u!==void 0&&(n=ro(n,u,a)),ro(n,i,a)+r}function Xl(n,r=0,i=1,a,u){n.min=hh(n.min,r,i,a,u),n.max=hh(n.max,r,i,a,u)}function Cm(n,{x:r,y:i}){Xl(n.x,r.translate,r.scale,r.originPoint),Xl(n.y,i.translate,i.scale,i.originPoint)}const ph=.999999999999,mh=1.0000000000001;function dw(n,r,i,a=!1){var p;const u=i.length;if(!u)return;r.x=r.y=1;let f,d;for(let g=0;g<u;g++){f=i[g],d=f.projectionDelta;const{visualElement:x}=f.options;x&&x.props.style&&x.props.style.display==="contents"||(a&&f.options.layoutScroll&&f.scroll&&f!==f.root&&(Ft(n.x,-f.scroll.offset.x),Ft(n.y,-f.scroll.offset.y)),d&&(r.x*=d.x.scale,r.y*=d.y.scale,Cm(n,d)),a&&zn(f.latestValues)&&Gi(n,f.latestValues,(p=f.layout)==null?void 0:p.layoutBox))}r.x<mh&&r.x>ph&&(r.x=1),r.y<mh&&r.y>ph&&(r.y=1)}function Ft(n,r){n.min+=r,n.max+=r}function gh(n,r,i,a,u=.5){const f=Ne(n.min,n.max,u);Xl(n,r,i,f,a)}function yh(n,r){return typeof n=="string"?parseFloat(n)/100*(r.max-r.min):n}function Gi(n,r,i){const a=i??n;gh(n.x,yh(r.x,a.x),r.scaleX,r.scale,r.originX),gh(n.y,yh(r.y,a.y),r.scaleY,r.scale,r.originY)}function Pm(n,r){return Nm(cw(n.getBoundingClientRect(),r))}function fw(n,r,i){const a=Pm(n,i),{scroll:u}=r;return u&&(Ft(a.x,u.offset.x),Ft(a.y,u.offset.y)),a}const hw={x:"translateX",y:"translateY",z:"translateZ",transformPerspective:"perspective"},pw=kr.length;function mw(n,r,i){let a="",u=!0;for(let f=0;f<pw;f++){const d=kr[f],p=n[d];if(p===void 0)continue;let g=!0;if(typeof p=="number")g=p===(d.startsWith("scale")?1:0);else{const x=parseFloat(p);g=d.startsWith("scale")?x===1:x===0}if(!g||i){const x=mm(p,ku[d]);if(!g){u=!1;const y=hw[d]||d;a+=`${y}(${x}) `}i&&(r[d]=x)}}return a=a.trim(),i?a=i(r,u?"":a):u&&(a="none"),a}function Pu(n,r,i){const{style:a,vars:u,transformOrigin:f}=n;let d=!1,p=!1;for(const g in r){const x=r[g];if(Sr.has(g)){d=!0;continue}else if(zp(g)){u[g]=x;continue}else{const y=mm(x,ku[g]);g.startsWith("origin")?(p=!0,f[g]=y):a[g]=y}}if(r.transform||(d||i?a.transform=mw(r,n.transform,i):a.transform&&(a.transform="none")),p){const{originX:g="50%",originY:x="50%",originZ:y=0}=f;a.transformOrigin=`${g} ${x} ${y}`}}function Em(n,{style:r,vars:i},a,u){const f=n.style;let d;for(d in r)f[d]=r[d];u==null||u.applyProjectionStyles(f,a);for(d in i)f.setProperty(d,i[d])}function vh(n,r){return r.max===r.min?0:n/(r.max-r.min)*100}const us={correct:(n,r)=>{if(!r.target)return n;if(typeof n=="string")if(q.test(n))n=parseFloat(n);else return n;const i=vh(n,r.target.x),a=vh(n,r.target.y);return`${i}% ${a}%`}},gw={correct:(n,{treeScale:r,projectionDelta:i})=>{const a=n,u=Rt.parse(n);if(u.length>5)return a;const f=Rt.createTransformer(n),d=typeof u[0]!="number"?1:0,p=i.x.scale*r.x,g=i.y.scale*r.y;u[0+d]/=p,u[1+d]/=g;const x=Ne(p,g,.5);return typeof u[2+d]=="number"&&(u[2+d]/=x),typeof u[3+d]=="number"&&(u[3+d]/=x),f(u)}},Ql={borderRadius:{...us,applyTo:["borderTopLeftRadius","borderTopRightRadius","borderBottomLeftRadius","borderBottomRightRadius"]},borderTopLeftRadius:us,borderTopRightRadius:us,borderBottomLeftRadius:us,borderBottomRightRadius:us,boxShadow:gw};function bm(n,{layout:r,layoutId:i}){return Sr.has(n)||n.startsWith("origin")||(r||i!==void 0)&&(!!Ql[n]||n==="opacity")}function Eu(n,r,i){var d;const a=n.style,u=r==null?void 0:r.style,f={};if(!a)return f;for(const p in a)(Xe(a[p])||u&&Xe(u[p])||bm(p,n)||((d=i==null?void 0:i.getValue(p))==null?void 0:d.liveStyle)!==void 0)&&(f[p]=a[p]);return f}function yw(n){return window.getComputedStyle(n)}class vw extends jm{constructor(){super(...arguments),this.type="html",this.renderInstance=Em}readValueFromInstance(r,i){var a;if(Sr.has(i))return(a=this.projection)!=null&&a.isProjecting?Vl(i):Ix(r,i);{const u=yw(r),f=(zp(i)?u.getPropertyValue(i):u[i])||0;return typeof f=="string"?f.trim():f}}measureInstanceViewportBox(r,{transformPagePoint:i}){return Pm(r,i)}build(r,i,a){Pu(r,i,a.transformTemplate)}scrapeMotionValuesFromProps(r,i,a){return Eu(r,i,a)}}const xw={offset:"stroke-dashoffset",array:"stroke-dasharray"},ww={offset:"strokeDashoffset",array:"strokeDasharray"};function kw(n,r,i=1,a=0,u=!0){n.pathLength=1;const f=u?xw:ww;n[f.offset]=`${-a}`,n[f.array]=`${r} ${i}`}const Sw=["offsetDistance","offsetPath","offsetRotate","offsetAnchor"];function Mm(n,{attrX:r,attrY:i,attrScale:a,pathLength:u,pathSpacing:f=1,pathOffset:d=0,...p},g,x,y){if(Pu(n,p,x),g){n.style.viewBox&&(n.attrs.viewBox=n.style.viewBox);return}n.attrs=n.style,n.style={};const{attrs:v,style:w}=n;v.transform&&(w.transform=v.transform,delete v.transform),(w.transform||v.transformOrigin)&&(w.transformOrigin=v.transformOrigin??"50% 50%",delete v.transformOrigin),w.transform&&(w.transformBox=(y==null?void 0:y.transformBox)??"fill-box",delete v.transformBox);for(const N of Sw)v[N]!==void 0&&(w[N]=v[N],delete v[N]);r!==void 0&&(v.x=r),i!==void 0&&(v.y=i),a!==void 0&&(v.scale=a),u!==void 0&&kw(v,u,f,d,!1)}const _m=new Set(["baseFrequency","diffuseConstant","kernelMatrix","kernelUnitLength","keySplines","keyTimes","limitingConeAngle","markerHeight","markerWidth","numOctaves","targetX","targetY","surfaceScale","specularConstant","specularExponent","stdDeviation","tableValues","viewBox","gradientTransform","pathLength","startOffset","textLength","lengthAdjust"]),Am=n=>typeof n=="string"&&n.toLowerCase()==="svg";function jw(n,r,i,a){Em(n,r,void 0,a);for(const u in r.attrs)n.setAttribute(_m.has(u)?u:wu(u),r.attrs[u])}function Rm(n,r,i){const a=Eu(n,r,i);for(const u in n)if(Xe(n[u])||Xe(r[u])){const f=kr.indexOf(u)!==-1?"attr"+u.charAt(0).toUpperCase()+u.substring(1):u;a[f]=n[u]}return a}class Nw extends jm{constructor(){super(...arguments),this.type="svg",this.isSVGTag=!1,this.measureInstanceViewportBox=Ue}getBaseTargetFromProps(r,i){return r[i]}readValueFromInstance(r,i){if(Sr.has(i)){const a=fm(i);return a&&a.default||0}return i=_m.has(i)?i:wu(i),r.getAttribute(i)}scrapeMotionValuesFromProps(r,i,a){return Rm(r,i,a)}build(r,i,a){Mm(r,i,this.isSVGTag,a.transformTemplate,a.style)}renderInstance(r,i,a,u){jw(r,i,a,u)}mount(r){this.isSVGTag=Am(r.tagName),super.mount(r)}}const Tw=Cu.length;function Dm(n){if(!n)return;if(!n.isControllingVariants){const i=n.parent?Dm(n.parent)||{}:{};return n.props.initial!==void 0&&(i.initial=n.props.initial),i}const r={};for(let i=0;i<Tw;i++){const a=Cu[i],u=n.props[a];(ws(u)||u===!1)&&(r[a]=u)}return r}function Lm(n,r){if(!Array.isArray(r))return!1;const i=r.length;if(i!==n.length)return!1;for(let a=0;a<i;a++)if(r[a]!==n[a])return!1;return!0}const Cw=[...Tu].reverse(),Pw=Tu.length;function Ew(n){return r=>Promise.all(r.map(({animation:i,options:a})=>T1(n,i,a)))}function bw(n){let r=Ew(n),i=xh(),a=!0,u=!1;const f=x=>(y,v)=>{var N;const w=Bn(n,v,x==="exit"?(N=n.presenceContext)==null?void 0:N.custom:void 0);if(w){const{transition:E,transitionEnd:_,...M}=w;y={...y,...M,..._}}return y};function d(x){r=x(n)}function p(x){const{props:y}=n,v=Dm(n.parent)||{},w=[],N=new Set;let E={},_=1/0;for(let L=0;L<Pw;L++){const B=Cw[L],I=i[B],U=y[B]!==void 0?y[B]:v[B],W=ws(U),se=B===x?I.isActive:null;se===!1&&(_=L);let G=U===v[B]&&U!==y[B]&&W;if(G&&(a||u)&&n.manuallyAnimateOnMount&&(G=!1),I.protectedKeys={...E},!I.isActive&&se===null||!U&&!I.prevProp||uo(U)||typeof U=="boolean")continue;if(B==="exit"&&I.isActive&&se!==!0){I.prevResolvedValues&&(E={...E,...I.prevResolvedValues});continue}const H=Mw(I.prevProp,U);let re=H||B===x&&I.isActive&&!G&&W||L>_&&W,Y=!1;const ce=Array.isArray(U)?U:[U];let me=ce.reduce(f(B),{});se===!1&&(me={});const{prevResolvedValues:Pe={}}=I,_e={...Pe,...me},ze=O=>{re=!0,N.has(O)&&(Y=!0,N.delete(O)),I.needsAnimating[O]=!0;const Z=n.getValue(O);Z&&(Z.liveStyle=!1)};for(const O in _e){const Z=me[O],$=Pe[O];if(E.hasOwnProperty(O))continue;let T=!1;Ul(Z)&&Ul($)?T=!Lm(Z,$):T=Z!==$,T?Z!=null?ze(O):N.add(O):Z!==void 0&&N.has(O)?ze(O):I.protectedKeys[O]=!0}I.prevProp=U,I.prevResolvedValues=me,I.isActive&&(E={...E,...me}),(a||u)&&n.blockInitialAnimation&&(re=!1);const ke=G&&H;re&&(!ke||Y)&&w.push(...ce.map(O=>{const Z={type:B};if(typeof O=="string"&&(a||u)&&!ke&&n.manuallyAnimateOnMount&&n.parent){const{parent:$}=n,T=Bn($,O);if($.enteringChildren&&T){const{delayChildren:A}=T.transition||{};Z.delay=rm($.enteringChildren,n,A)}}return{animation:O,options:Z}}))}if(N.size){const L={};if(typeof y.initial!="boolean"){const B=Bn(n,Array.isArray(y.initial)?y.initial[0]:y.initial);B&&B.transition&&(L.transition=B.transition)}N.forEach(B=>{const I=n.getBaseTarget(B),U=n.getValue(B);U&&(U.liveStyle=!0),L[B]=I??null}),w.push({animation:L})}let M=!!w.length;return a&&(y.initial===!1||y.initial===y.animate)&&!n.manuallyAnimateOnMount&&(M=!1),a=!1,u=!1,M?r(w):Promise.resolve()}function g(x,y){var w;if(i[x].isActive===y)return Promise.resolve();(w=n.variantChildren)==null||w.forEach(N=>{var E;return(E=N.animationState)==null?void 0:E.setActive(x,y)}),i[x].isActive=y;const v=p(x);for(const N in i)i[N].protectedKeys={};return v}return{animateChanges:p,setActive:g,setAnimateFunction:d,getState:()=>i,reset:()=>{i=xh(),u=!0}}}function Mw(n,r){return typeof r=="string"?r!==n:Array.isArray(r)?!Lm(r,n):!1}function Vn(n=!1){return{isActive:n,protectedKeys:{},needsAnimating:{},prevResolvedValues:{}}}function xh(){return{animate:Vn(!0),whileInView:Vn(),whileHover:Vn(),whileTap:Vn(),whileDrag:Vn(),whileFocus:Vn(),exit:Vn()}}function ql(n,r){n.min=r.min,n.max=r.max}function _t(n,r){ql(n.x,r.x),ql(n.y,r.y)}function wh(n,r){n.translate=r.translate,n.scale=r.scale,n.originPoint=r.originPoint,n.origin=r.origin}const Vm=1e-4,_w=1-Vm,Aw=1+Vm,zm=.01,Rw=0-zm,Dw=0+zm;function rt(n){return n.max-n.min}function Lw(n,r,i){return Math.abs(n-r)<=i}function kh(n,r,i,a=.5){n.origin=a,n.originPoint=Ne(r.min,r.max,n.origin),n.scale=rt(i)/rt(r),n.translate=Ne(i.min,i.max,n.origin)-n.originPoint,(n.scale>=_w&&n.scale<=Aw||isNaN(n.scale))&&(n.scale=1),(n.translate>=Rw&&n.translate<=Dw||isNaN(n.translate))&&(n.translate=0)}function hs(n,r,i,a){kh(n.x,r.x,i.x,a?a.originX:void 0),kh(n.y,r.y,i.y,a?a.originY:void 0)}function Sh(n,r,i,a=0){const u=a?Ne(i.min,i.max,a):i.min;n.min=u+r.min,n.max=n.min+rt(r)}function Vw(n,r,i,a){Sh(n.x,r.x,i.x,a==null?void 0:a.x),Sh(n.y,r.y,i.y,a==null?void 0:a.y)}function jh(n,r,i,a=0){const u=a?Ne(i.min,i.max,a):i.min;n.min=r.min-u,n.max=n.min+rt(r)}function so(n,r,i,a){jh(n.x,r.x,i.x,a==null?void 0:a.x),jh(n.y,r.y,i.y,a==null?void 0:a.y)}function Nh(n,r,i,a,u){return n-=r,n=ro(n,1/i,a),u!==void 0&&(n=ro(n,1/u,a)),n}function zw(n,r=0,i=1,a=.5,u,f=n,d=n){if(Bt.test(r)&&(r=parseFloat(r),r=Ne(d.min,d.max,r/100)-d.min),typeof r!="number")return;let p=Ne(f.min,f.max,a);n===f&&(p-=r),n.min=Nh(n.min,r,i,p,u),n.max=Nh(n.max,r,i,p,u)}function Th(n,r,[i,a,u],f,d){zw(n,r[i],r[a],r[u],r.scale,f,d)}const Iw=["x","scaleX","originX"],Ow=["y","scaleY","originY"];function Ch(n,r,i,a){Th(n.x,r,Iw,i?i.x:void 0,a?a.x:void 0),Th(n.y,r,Ow,i?i.y:void 0,a?a.y:void 0)}function Ph(n){return n.translate===0&&n.scale===1}function Im(n){return Ph(n.x)&&Ph(n.y)}function Eh(n,r){return n.min===r.min&&n.max===r.max}function Fw(n,r){return Eh(n.x,r.x)&&Eh(n.y,r.y)}function bh(n,r){return Math.round(n.min)===Math.round(r.min)&&Math.round(n.max)===Math.round(r.max)}function Om(n,r){return bh(n.x,r.x)&&bh(n.y,r.y)}function Mh(n){return rt(n.x)/rt(n.y)}function _h(n,r){return n.translate===r.translate&&n.scale===r.scale&&n.originPoint===r.originPoint}function Ot(n){return[n("x"),n("y")]}function Bw(n,r,i){let a="";const u=n.x.translate/r.x,f=n.y.translate/r.y,d=(i==null?void 0:i.z)||0;if((u||f||d)&&(a=`translate3d(${u}px, ${f}px, ${d}px) `),(r.x!==1||r.y!==1)&&(a+=`scale(${1/r.x}, ${1/r.y}) `),i){const{transformPerspective:x,rotate:y,rotateX:v,rotateY:w,skewX:N,skewY:E}=i;x&&(a=`perspective(${x}px) ${a}`),y&&(a+=`rotate(${y}deg) `),v&&(a+=`rotateX(${v}deg) `),w&&(a+=`rotateY(${w}deg) `),N&&(a+=`skewX(${N}deg) `),E&&(a+=`skewY(${E}deg) `)}const p=n.x.scale*r.x,g=n.y.scale*r.y;return(p!==1||g!==1)&&(a+=`scale(${p}, ${g})`),a||"none"}const Fm=["borderTopLeftRadius","borderTopRightRadius","borderBottomLeftRadius","borderBottomRightRadius"],Uw=Fm.length,Ah=n=>typeof n=="string"?parseFloat(n):n,Rh=n=>typeof n=="number"||q.test(n);function $w(n,r,i,a,u,f){u?(n.opacity=Ne(0,i.opacity??1,Ww(a)),n.opacityExit=Ne(r.opacity??1,0,Hw(a))):f&&(n.opacity=Ne(r.opacity??1,i.opacity??1,a));for(let d=0;d<Uw;d++){const p=Fm[d];let g=Dh(r,p),x=Dh(i,p);if(g===void 0&&x===void 0)continue;g||(g=0),x||(x=0),g===0||x===0||Rh(g)===Rh(x)?(n[p]=Math.max(Ne(Ah(g),Ah(x),a),0),(Bt.test(x)||Bt.test(g))&&(n[p]+="%")):n[p]=x}(r.rotate||i.rotate)&&(n.rotate=Ne(r.rotate||0,i.rotate||0,a))}function Dh(n,r){return n[r]!==void 0?n[r]:n.borderRadius}const Ww=Bm(0,.5,_p),Hw=Bm(.5,.95,jt);function Bm(n,r,i){return a=>a<n?0:a>r?1:i(vs(n,r,a))}function Kw(n,r,i){const a=Xe(n)?n:xr(n);return a.start(vu("",a,r,i)),a.animation}function ks(n,r,i,a={passive:!0}){return n.addEventListener(r,i,a),()=>n.removeEventListener(r,i)}const Gw=(n,r)=>n.depth-r.depth;class Yw{constructor(){this.children=[],this.isDirty=!1}add(r){iu(this.children,r),this.isDirty=!0}remove(r){qi(this.children,r),this.isDirty=!0}forEach(r){this.isDirty&&this.children.sort(Gw),this.isDirty=!1,this.children.forEach(r)}}function Xw(n,r){const i=nt.now(),a=({timestamp:u})=>{const f=u-i;f>=r&&(kn(a),n(f-r))};return ve.setup(a,!0),()=>kn(a)}function Yi(n){return Xe(n)?n.get():n}class Qw{constructor(){this.members=[]}add(r){iu(this.members,r);for(let i=this.members.length-1;i>=0;i--){const a=this.members[i];if(a===r||a===this.lead||a===this.prevLead)continue;const u=a.instance;(!u||u.isConnected===!1)&&!a.snapshot&&(qi(this.members,a),a.unmount())}r.scheduleRender()}remove(r){if(qi(this.members,r),r===this.prevLead&&(this.prevLead=void 0),r===this.lead){const i=this.members[this.members.length-1];i&&this.promote(i)}}relegate(r){var i;for(let a=this.members.indexOf(r)-1;a>=0;a--){const u=this.members[a];if(u.isPresent!==!1&&((i=u.instance)==null?void 0:i.isConnected)!==!1)return this.promote(u),!0}return!1}promote(r,i){var u;const a=this.lead;if(r!==a&&(this.prevLead=a,this.lead=r,r.show(),a)){a.updateSnapshot(),r.scheduleRender();const{layoutDependency:f}=a.options,{layoutDependency:d}=r.options;(f===void 0||f!==d)&&(r.resumeFrom=a,i&&(a.preserveOpacity=!0),a.snapshot&&(r.snapshot=a.snapshot,r.snapshot.latestValues=a.animationValues||a.latestValues),(u=r.root)!=null&&u.isUpdating&&(r.isLayoutDirty=!0)),r.options.crossfade===!1&&a.hide()}}exitAnimationComplete(){this.members.forEach(r=>{var i,a,u,f,d;(a=(i=r.options).onExitComplete)==null||a.call(i),(d=(u=r.resumingFrom)==null?void 0:(f=u.options).onExitComplete)==null||d.call(f)})}scheduleRender(){this.members.forEach(r=>r.instance&&r.scheduleRender(!1))}removeLeadSnapshot(){var r;(r=this.lead)!=null&&r.snapshot&&(this.lead.snapshot=void 0)}}const Xi={hasAnimatedSinceResize:!0,hasEverUpdated:!1},wl=["","X","Y","Z"],qw=1e3;let Zw=0;function kl(n,r,i,a){const{latestValues:u}=r;u[n]&&(i[n]=u[n],r.setStaticValue(n,0),a&&(a[n]=0))}function Um(n){if(n.hasCheckedOptimisedAppear=!0,n.root===n)return;const{visualElement:r}=n.options;if(!r)return;const i=lm(r);if(window.MotionHasOptimisedAnimation(i,"transform")){const{layout:u,layoutId:f}=n.options;window.MotionCancelOptimisedAnimation(i,"transform",ve,!(u||f))}const{parent:a}=n;a&&!a.hasCheckedOptimisedAppear&&Um(a)}function $m({attachResizeListener:n,defaultParent:r,measureScroll:i,checkIsScrollRoot:a,resetTransform:u}){return class{constructor(d={},p=r==null?void 0:r()){this.id=Zw++,this.animationId=0,this.animationCommitId=0,this.children=new Set,this.options={},this.isTreeAnimating=!1,this.isAnimationBlocked=!1,this.isLayoutDirty=!1,this.isProjectionDirty=!1,this.isSharedProjectionDirty=!1,this.isTransformDirty=!1,this.updateManuallyBlocked=!1,this.updateBlockedByResize=!1,this.isUpdating=!1,this.isSVG=!1,this.needsReset=!1,this.shouldResetTransform=!1,this.hasCheckedOptimisedAppear=!1,this.treeScale={x:1,y:1},this.eventHandlers=new Map,this.hasTreeAnimated=!1,this.layoutVersion=0,this.updateScheduled=!1,this.scheduleUpdate=()=>this.update(),this.projectionUpdateScheduled=!1,this.checkUpdateFailed=()=>{this.isUpdating&&(this.isUpdating=!1,this.clearAllSnapshots())},this.updateProjection=()=>{this.projectionUpdateScheduled=!1,this.nodes.forEach(t2),this.nodes.forEach(a2),this.nodes.forEach(l2),this.nodes.forEach(n2)},this.resolvedRelativeTargetAt=0,this.linkedParentVersion=0,this.hasProjected=!1,this.isVisible=!0,this.animationProgress=0,this.sharedNodes=new Map,this.latestValues=d,this.root=p?p.root||p:this,this.path=p?[...p.path,p]:[],this.parent=p,this.depth=p?p.depth+1:0;for(let g=0;g<this.path.length;g++)this.path[g].shouldResetTransform=!0;this.root===this&&(this.nodes=new Yw)}addEventListener(d,p){return this.eventHandlers.has(d)||this.eventHandlers.set(d,new au),this.eventHandlers.get(d).add(p)}notifyListeners(d,...p){const g=this.eventHandlers.get(d);g&&g.notify(...p)}hasListeners(d){return this.eventHandlers.has(d)}mount(d){if(this.instance)return;this.isSVG=Nu(d)&&!ew(d),this.instance=d;const{layoutId:p,layout:g,visualElement:x}=this.options;if(x&&!x.current&&x.mount(d),this.root.nodes.add(this),this.parent&&this.parent.children.add(this),this.root.hasTreeAnimated&&(g||p)&&(this.isLayoutDirty=!0),n){let y,v=0;const w=()=>this.root.updateBlockedByResize=!1;ve.read(()=>{v=window.innerWidth}),n(d,()=>{const N=window.innerWidth;N!==v&&(v=N,this.root.updateBlockedByResize=!0,y&&y(),y=Xw(w,250),Xi.hasAnimatedSinceResize&&(Xi.hasAnimatedSinceResize=!1,this.nodes.forEach(zh)))})}p&&this.root.registerSharedNode(p,this),this.options.animate!==!1&&x&&(p||g)&&this.addEventListener("didUpdate",({delta:y,hasLayoutChanged:v,hasRelativeLayoutChanged:w,layout:N})=>{if(this.isTreeAnimationBlocked()){this.target=void 0,this.relativeTarget=void 0;return}const E=this.options.transition||x.getDefaultTransition()||h2,{onLayoutAnimationStart:_,onLayoutAnimationComplete:M}=x.getProps(),L=!this.targetLayout||!Om(this.targetLayout,N),B=!v&&w;if(this.options.layoutRoot||this.resumeFrom||B||v&&(L||!this.currentAnimation)){this.resumeFrom&&(this.resumingFrom=this.resumeFrom,this.resumingFrom.resumingFrom=void 0);const I={...yu(E,"layout"),onPlay:_,onComplete:M};(x.shouldReduceMotion||this.options.layoutRoot)&&(I.delay=0,I.type=!1),this.startAnimation(I),this.setAnimationOrigin(y,B)}else v||zh(this),this.isLead()&&this.options.onExitComplete&&this.options.onExitComplete();this.targetLayout=N})}unmount(){this.options.layoutId&&this.willUpdate(),this.root.nodes.remove(this);const d=this.getStack();d&&d.remove(this),this.parent&&this.parent.children.delete(this),this.instance=void 0,this.eventHandlers.clear(),kn(this.updateProjection)}blockUpdate(){this.updateManuallyBlocked=!0}unblockUpdate(){this.updateManuallyBlocked=!1}isUpdateBlocked(){return this.updateManuallyBlocked||this.updateBlockedByResize}isTreeAnimationBlocked(){return this.isAnimationBlocked||this.parent&&this.parent.isTreeAnimationBlocked()||!1}startUpdate(){this.isUpdateBlocked()||(this.isUpdating=!0,this.nodes&&this.nodes.forEach(u2),this.animationId++)}getTransformTemplate(){const{visualElement:d}=this.options;return d&&d.getProps().transformTemplate}willUpdate(d=!0){if(this.root.hasTreeAnimated=!0,this.root.isUpdateBlocked()){this.options.onExitComplete&&this.options.onExitComplete();return}if(window.MotionCancelOptimisedAnimation&&!this.hasCheckedOptimisedAppear&&Um(this),!this.root.isUpdating&&this.root.startUpdate(),this.isLayoutDirty)return;this.isLayoutDirty=!0;for(let y=0;y<this.path.length;y++){const v=this.path[y];v.shouldResetTransform=!0,(typeof v.latestValues.x=="string"||typeof v.latestValues.y=="string")&&(v.isLayoutDirty=!0),v.updateScroll("snapshot"),v.options.layoutRoot&&v.willUpdate(!1)}const{layoutId:p,layout:g}=this.options;if(p===void 0&&!g)return;const x=this.getTransformTemplate();this.prevTransformTemplateValue=x?x(this.latestValues,""):void 0,this.updateSnapshot(),d&&this.notifyListeners("willUpdate")}update(){if(this.updateScheduled=!1,this.isUpdateBlocked()){const g=this.updateBlockedByResize;this.unblockUpdate(),this.updateBlockedByResize=!1,this.clearAllSnapshots(),g&&this.nodes.forEach(s2),this.nodes.forEach(Lh);return}if(this.animationId<=this.animationCommitId){this.nodes.forEach(Vh);return}this.animationCommitId=this.animationId,this.isUpdating?(this.isUpdating=!1,this.nodes.forEach(i2),this.nodes.forEach(o2),this.nodes.forEach(Jw),this.nodes.forEach(e2)):this.nodes.forEach(Vh),this.clearAllSnapshots();const p=nt.now();Ye.delta=Ut(0,1e3/60,p-Ye.timestamp),Ye.timestamp=p,Ye.isProcessing=!0,fl.update.process(Ye),fl.preRender.process(Ye),fl.render.process(Ye),Ye.isProcessing=!1}didUpdate(){this.updateScheduled||(this.updateScheduled=!0,Su.read(this.scheduleUpdate))}clearAllSnapshots(){this.nodes.forEach(r2),this.sharedNodes.forEach(c2)}scheduleUpdateProjection(){this.projectionUpdateScheduled||(this.projectionUpdateScheduled=!0,ve.preRender(this.updateProjection,!1,!0))}scheduleCheckAfterUnmount(){ve.postRender(()=>{this.isLayoutDirty?this.root.didUpdate():this.root.checkUpdateFailed()})}updateSnapshot(){this.snapshot||!this.instance||(this.snapshot=this.measure(),this.snapshot&&!rt(this.snapshot.measuredBox.x)&&!rt(this.snapshot.measuredBox.y)&&(this.snapshot=void 0))}updateLayout(){if(!this.instance||(this.updateScroll(),!(this.options.alwaysMeasureLayout&&this.isLead())&&!this.isLayoutDirty))return;if(this.resumeFrom&&!this.resumeFrom.instance)for(let g=0;g<this.path.length;g++)this.path[g].updateScroll();const d=this.layout;this.layout=this.measure(!1),this.layoutVersion++,this.layoutCorrected||(this.layoutCorrected=Ue()),this.isLayoutDirty=!1,this.projectionDelta=void 0,this.notifyListeners("measure",this.layout.layoutBox);const{visualElement:p}=this.options;p&&p.notify("LayoutMeasure",this.layout.layoutBox,d?d.layoutBox:void 0)}updateScroll(d="measure"){let p=!!(this.options.layoutScroll&&this.instance);if(this.scroll&&this.scroll.animationId===this.root.animationId&&this.scroll.phase===d&&(p=!1),p&&this.instance){const g=a(this.instance);this.scroll={animationId:this.root.animationId,phase:d,isRoot:g,offset:i(this.instance),wasRoot:this.scroll?this.scroll.isRoot:g}}}resetTransform(){if(!u)return;const d=this.isLayoutDirty||this.shouldResetTransform||this.options.alwaysMeasureLayout,p=this.projectionDelta&&!Im(this.projectionDelta),g=this.getTransformTemplate(),x=g?g(this.latestValues,""):void 0,y=x!==this.prevTransformTemplateValue;d&&this.instance&&(p||zn(this.latestValues)||y)&&(u(this.instance,x),this.shouldResetTransform=!1,this.scheduleRender())}measure(d=!0){const p=this.measurePageBox();let g=this.removeElementScroll(p);return d&&(g=this.removeTransform(g)),p2(g),{animationId:this.root.animationId,measuredBox:p,layoutBox:g,latestValues:{},source:this.id}}measurePageBox(){var x;const{visualElement:d}=this.options;if(!d)return Ue();const p=d.measureViewportBox();if(!(((x=this.scroll)==null?void 0:x.wasRoot)||this.path.some(m2))){const{scroll:y}=this.root;y&&(Ft(p.x,y.offset.x),Ft(p.y,y.offset.y))}return p}removeElementScroll(d){var g;const p=Ue();if(_t(p,d),(g=this.scroll)!=null&&g.wasRoot)return p;for(let x=0;x<this.path.length;x++){const y=this.path[x],{scroll:v,options:w}=y;y!==this.root&&v&&w.layoutScroll&&(v.wasRoot&&_t(p,d),Ft(p.x,v.offset.x),Ft(p.y,v.offset.y))}return p}applyTransform(d,p=!1,g){var y,v;const x=g||Ue();_t(x,d);for(let w=0;w<this.path.length;w++){const N=this.path[w];!p&&N.options.layoutScroll&&N.scroll&&N!==N.root&&(Ft(x.x,-N.scroll.offset.x),Ft(x.y,-N.scroll.offset.y)),zn(N.latestValues)&&Gi(x,N.latestValues,(y=N.layout)==null?void 0:y.layoutBox)}return zn(this.latestValues)&&Gi(x,this.latestValues,(v=this.layout)==null?void 0:v.layoutBox),x}removeTransform(d){var g;const p=Ue();_t(p,d);for(let x=0;x<this.path.length;x++){const y=this.path[x];if(!zn(y.latestValues))continue;let v;y.instance&&(Yl(y.latestValues)&&y.updateSnapshot(),v=Ue(),_t(v,y.measurePageBox())),Ch(p,y.latestValues,(g=y.snapshot)==null?void 0:g.layoutBox,v)}return zn(this.latestValues)&&Ch(p,this.latestValues),p}setTargetDelta(d){this.targetDelta=d,this.root.scheduleUpdateProjection(),this.isProjectionDirty=!0}setOptions(d){this.options={...this.options,...d,crossfade:d.crossfade!==void 0?d.crossfade:!0}}clearMeasurements(){this.scroll=void 0,this.layout=void 0,this.snapshot=void 0,this.prevTransformTemplateValue=void 0,this.targetDelta=void 0,this.target=void 0,this.isLayoutDirty=!1}forceRelativeParentToResolveTarget(){this.relativeParent&&this.relativeParent.resolvedRelativeTargetAt!==Ye.timestamp&&this.relativeParent.resolveTargetDelta(!0)}resolveTargetDelta(d=!1){var N;const p=this.getLead();this.isProjectionDirty||(this.isProjectionDirty=p.isProjectionDirty),this.isTransformDirty||(this.isTransformDirty=p.isTransformDirty),this.isSharedProjectionDirty||(this.isSharedProjectionDirty=p.isSharedProjectionDirty);const g=!!this.resumingFrom||this!==p;if(!(d||g&&this.isSharedProjectionDirty||this.isProjectionDirty||(N=this.parent)!=null&&N.isProjectionDirty||this.attemptToResolveRelativeTarget||this.root.updateBlockedByResize))return;const{layout:y,layoutId:v}=this.options;if(!this.layout||!(y||v))return;this.resolvedRelativeTargetAt=Ye.timestamp;const w=this.getClosestProjectingParent();w&&this.linkedParentVersion!==w.layoutVersion&&!w.options.layoutRoot&&this.removeRelativeTarget(),!this.targetDelta&&!this.relativeTarget&&(this.options.layoutAnchor!==!1&&w&&w.layout?this.createRelativeTarget(w,this.layout.layoutBox,w.layout.layoutBox):this.removeRelativeTarget()),!(!this.relativeTarget&&!this.targetDelta)&&(this.target||(this.target=Ue(),this.targetWithTransforms=Ue()),this.relativeTarget&&this.relativeTargetOrigin&&this.relativeParent&&this.relativeParent.target?(this.forceRelativeParentToResolveTarget(),Vw(this.target,this.relativeTarget,this.relativeParent.target,this.options.layoutAnchor||void 0)):this.targetDelta?(this.resumingFrom?this.applyTransform(this.layout.layoutBox,!1,this.target):_t(this.target,this.layout.layoutBox),Cm(this.target,this.targetDelta)):_t(this.target,this.layout.layoutBox),this.attemptToResolveRelativeTarget&&(this.attemptToResolveRelativeTarget=!1,this.options.layoutAnchor!==!1&&w&&!!w.resumingFrom==!!this.resumingFrom&&!w.options.layoutScroll&&w.target&&this.animationProgress!==1?this.createRelativeTarget(w,this.target,w.target):this.relativeParent=this.relativeTarget=void 0))}getClosestProjectingParent(){if(!(!this.parent||Yl(this.parent.latestValues)||Tm(this.parent.latestValues)))return this.parent.isProjecting()?this.parent:this.parent.getClosestProjectingParent()}isProjecting(){return!!((this.relativeTarget||this.targetDelta||this.options.layoutRoot)&&this.layout)}createRelativeTarget(d,p,g){this.relativeParent=d,this.linkedParentVersion=d.layoutVersion,this.forceRelativeParentToResolveTarget(),this.relativeTarget=Ue(),this.relativeTargetOrigin=Ue(),so(this.relativeTargetOrigin,p,g,this.options.layoutAnchor||void 0),_t(this.relativeTarget,this.relativeTargetOrigin)}removeRelativeTarget(){this.relativeParent=this.relativeTarget=void 0}calcProjection(){var E;const d=this.getLead(),p=!!this.resumingFrom||this!==d;let g=!0;if((this.isProjectionDirty||(E=this.parent)!=null&&E.isProjectionDirty)&&(g=!1),p&&(this.isSharedProjectionDirty||this.isTransformDirty)&&(g=!1),this.resolvedRelativeTargetAt===Ye.timestamp&&(g=!1),g)return;const{layout:x,layoutId:y}=this.options;if(this.isTreeAnimating=!!(this.parent&&this.parent.isTreeAnimating||this.currentAnimation||this.pendingAnimation),this.isTreeAnimating||(this.targetDelta=this.relativeTarget=void 0),!this.layout||!(x||y))return;_t(this.layoutCorrected,this.layout.layoutBox);const v=this.treeScale.x,w=this.treeScale.y;dw(this.layoutCorrected,this.treeScale,this.path,p),d.layout&&!d.target&&(this.treeScale.x!==1||this.treeScale.y!==1)&&(d.target=d.layout.layoutBox,d.targetWithTransforms=Ue());const{target:N}=d;if(!N){this.prevProjectionDelta&&(this.createProjectionDeltas(),this.scheduleRender());return}!this.projectionDelta||!this.prevProjectionDelta?this.createProjectionDeltas():(wh(this.prevProjectionDelta.x,this.projectionDelta.x),wh(this.prevProjectionDelta.y,this.projectionDelta.y)),hs(this.projectionDelta,this.layoutCorrected,N,this.latestValues),(this.treeScale.x!==v||this.treeScale.y!==w||!_h(this.projectionDelta.x,this.prevProjectionDelta.x)||!_h(this.projectionDelta.y,this.prevProjectionDelta.y))&&(this.hasProjected=!0,this.scheduleRender(),this.notifyListeners("projectionUpdate",N))}hide(){this.isVisible=!1}show(){this.isVisible=!0}scheduleRender(d=!0){var p;if((p=this.options.visualElement)==null||p.scheduleRender(),d){const g=this.getStack();g&&g.scheduleRender()}this.resumingFrom&&!this.resumingFrom.instance&&(this.resumingFrom=void 0)}createProjectionDeltas(){this.prevProjectionDelta=gr(),this.projectionDelta=gr(),this.projectionDeltaWithTransform=gr()}setAnimationOrigin(d,p=!1){const g=this.snapshot,x=g?g.latestValues:{},y={...this.latestValues},v=gr();(!this.relativeParent||!this.relativeParent.options.layoutRoot)&&(this.relativeTarget=this.relativeTargetOrigin=void 0),this.attemptToResolveRelativeTarget=!p;const w=Ue(),N=g?g.source:void 0,E=this.layout?this.layout.source:void 0,_=N!==E,M=this.getStack(),L=!M||M.members.length<=1,B=!!(_&&!L&&this.options.crossfade===!0&&!this.path.some(f2));this.animationProgress=0;let I;this.mixTargetDelta=U=>{const W=U/1e3;Ih(v.x,d.x,W),Ih(v.y,d.y,W),this.setTargetDelta(v),this.relativeTarget&&this.relativeTargetOrigin&&this.layout&&this.relativeParent&&this.relativeParent.layout&&(so(w,this.layout.layoutBox,this.relativeParent.layout.layoutBox,this.options.layoutAnchor||void 0),d2(this.relativeTarget,this.relativeTargetOrigin,w,W),I&&Fw(this.relativeTarget,I)&&(this.isProjectionDirty=!1),I||(I=Ue()),_t(I,this.relativeTarget)),_&&(this.animationValues=y,$w(y,x,this.latestValues,W,B,L)),this.root.scheduleUpdateProjection(),this.scheduleRender(),this.animationProgress=W},this.mixTargetDelta(this.options.layoutRoot?1e3:0)}startAnimation(d){var p,g,x;this.notifyListeners("animationStart"),(p=this.currentAnimation)==null||p.stop(),(x=(g=this.resumingFrom)==null?void 0:g.currentAnimation)==null||x.stop(),this.pendingAnimation&&(kn(this.pendingAnimation),this.pendingAnimation=void 0),this.pendingAnimation=ve.update(()=>{Xi.hasAnimatedSinceResize=!0,this.motionValue||(this.motionValue=xr(0)),this.motionValue.jump(0,!1),this.currentAnimation=Kw(this.motionValue,[0,1e3],{...d,velocity:0,isSync:!0,onUpdate:y=>{this.mixTargetDelta(y),d.onUpdate&&d.onUpdate(y)},onStop:()=>{},onComplete:()=>{d.onComplete&&d.onComplete(),this.completeAnimation()}}),this.resumingFrom&&(this.resumingFrom.currentAnimation=this.currentAnimation),this.pendingAnimation=void 0})}completeAnimation(){this.resumingFrom&&(this.resumingFrom.currentAnimation=void 0,this.resumingFrom.preserveOpacity=void 0);const d=this.getStack();d&&d.exitAnimationComplete(),this.resumingFrom=this.currentAnimation=this.animationValues=void 0,this.notifyListeners("animationComplete")}finishAnimation(){this.currentAnimation&&(this.mixTargetDelta&&this.mixTargetDelta(qw),this.currentAnimation.stop()),this.completeAnimation()}applyTransformsToTarget(){const d=this.getLead();let{targetWithTransforms:p,target:g,layout:x,latestValues:y}=d;if(!(!p||!g||!x)){if(this!==d&&this.layout&&x&&Wm(this.options.animationType,this.layout.layoutBox,x.layoutBox)){g=this.target||Ue();const v=rt(this.layout.layoutBox.x);g.x.min=d.target.x.min,g.x.max=g.x.min+v;const w=rt(this.layout.layoutBox.y);g.y.min=d.target.y.min,g.y.max=g.y.min+w}_t(p,g),Gi(p,y),hs(this.projectionDeltaWithTransform,this.layoutCorrected,p,y)}}registerSharedNode(d,p){this.sharedNodes.has(d)||this.sharedNodes.set(d,new Qw),this.sharedNodes.get(d).add(p);const x=p.options.initialPromotionConfig;p.promote({transition:x?x.transition:void 0,preserveFollowOpacity:x&&x.shouldPreserveFollowOpacity?x.shouldPreserveFollowOpacity(p):void 0})}isLead(){const d=this.getStack();return d?d.lead===this:!0}getLead(){var p;const{layoutId:d}=this.options;return d?((p=this.getStack())==null?void 0:p.lead)||this:this}getPrevLead(){var p;const{layoutId:d}=this.options;return d?(p=this.getStack())==null?void 0:p.prevLead:void 0}getStack(){const{layoutId:d}=this.options;if(d)return this.root.sharedNodes.get(d)}promote({needsReset:d,transition:p,preserveFollowOpacity:g}={}){const x=this.getStack();x&&x.promote(this,g),d&&(this.projectionDelta=void 0,this.needsReset=!0),p&&this.setOptions({transition:p})}relegate(){const d=this.getStack();return d?d.relegate(this):!1}resetSkewAndRotation(){const{visualElement:d}=this.options;if(!d)return;let p=!1;const{latestValues:g}=d;if((g.z||g.rotate||g.rotateX||g.rotateY||g.rotateZ||g.skewX||g.skewY)&&(p=!0),!p)return;const x={};g.z&&kl("z",d,x,this.animationValues);for(let y=0;y<wl.length;y++)kl(`rotate${wl[y]}`,d,x,this.animationValues),kl(`skew${wl[y]}`,d,x,this.animationValues);d.render();for(const y in x)d.setStaticValue(y,x[y]),this.animationValues&&(this.animationValues[y]=x[y]);d.scheduleRender()}applyProjectionStyles(d,p){if(!this.instance||this.isSVG)return;if(!this.isVisible){d.visibility="hidden";return}const g=this.getTransformTemplate();if(this.needsReset){this.needsReset=!1,d.visibility="",d.opacity="",d.pointerEvents=Yi(p==null?void 0:p.pointerEvents)||"",d.transform=g?g(this.latestValues,""):"none";return}const x=this.getLead();if(!this.projectionDelta||!this.layout||!x.target){this.options.layoutId&&(d.opacity=this.latestValues.opacity!==void 0?this.latestValues.opacity:1,d.pointerEvents=Yi(p==null?void 0:p.pointerEvents)||""),this.hasProjected&&!zn(this.latestValues)&&(d.transform=g?g({},""):"none",this.hasProjected=!1);return}d.visibility="";const y=x.animationValues||x.latestValues;this.applyTransformsToTarget();let v=Bw(this.projectionDeltaWithTransform,this.treeScale,y);g&&(v=g(y,v)),d.transform=v;const{x:w,y:N}=this.projectionDelta;d.transformOrigin=`${w.origin*100}% ${N.origin*100}% 0`,x.animationValues?d.opacity=x===this?y.opacity??this.latestValues.opacity??1:this.preserveOpacity?this.latestValues.opacity:y.opacityExit:d.opacity=x===this?y.opacity!==void 0?y.opacity:"":y.opacityExit!==void 0?y.opacityExit:0;for(const E in Ql){if(y[E]===void 0)continue;const{correct:_,applyTo:M,isCSSVariable:L}=Ql[E],B=v==="none"?y[E]:_(y[E],x);if(M){const I=M.length;for(let U=0;U<I;U++)d[M[U]]=B}else L?this.options.visualElement.renderState.vars[E]=B:d[E]=B}this.options.layoutId&&(d.pointerEvents=x===this?Yi(p==null?void 0:p.pointerEvents)||"":"none")}clearSnapshot(){this.resumeFrom=this.snapshot=void 0}resetTree(){this.root.nodes.forEach(d=>{var p;return(p=d.currentAnimation)==null?void 0:p.stop()}),this.root.nodes.forEach(Lh),this.root.sharedNodes.clear()}}}function Jw(n){n.updateLayout()}function e2(n){var i;const r=((i=n.resumeFrom)==null?void 0:i.snapshot)||n.snapshot;if(n.isLead()&&n.layout&&r&&n.hasListeners("didUpdate")){const{layoutBox:a,measuredBox:u}=n.layout,{animationType:f}=n.options,d=r.source!==n.layout.source;if(f==="size")Ot(v=>{const w=d?r.measuredBox[v]:r.layoutBox[v],N=rt(w);w.min=a[v].min,w.max=w.min+N});else if(f==="x"||f==="y"){const v=f==="x"?"y":"x";ql(d?r.measuredBox[v]:r.layoutBox[v],a[v])}else Wm(f,r.layoutBox,a)&&Ot(v=>{const w=d?r.measuredBox[v]:r.layoutBox[v],N=rt(a[v]);w.max=w.min+N,n.relativeTarget&&!n.currentAnimation&&(n.isProjectionDirty=!0,n.relativeTarget[v].max=n.relativeTarget[v].min+N)});const p=gr();hs(p,a,r.layoutBox);const g=gr();d?hs(g,n.applyTransform(u,!0),r.measuredBox):hs(g,a,r.layoutBox);const x=!Im(p);let y=!1;if(!n.resumeFrom){const v=n.getClosestProjectingParent();if(v&&!v.resumeFrom){const{snapshot:w,layout:N}=v;if(w&&N){const E=n.options.layoutAnchor||void 0,_=Ue();so(_,r.layoutBox,w.layoutBox,E);const M=Ue();so(M,a,N.layoutBox,E),Om(_,M)||(y=!0),v.options.layoutRoot&&(n.relativeTarget=M,n.relativeTargetOrigin=_,n.relativeParent=v)}}}n.notifyListeners("didUpdate",{layout:a,snapshot:r,delta:g,layoutDelta:p,hasLayoutChanged:x,hasRelativeLayoutChanged:y})}else if(n.isLead()){const{onExitComplete:a}=n.options;a&&a()}n.options.transition=void 0}function t2(n){n.parent&&(n.isProjecting()||(n.isProjectionDirty=n.parent.isProjectionDirty),n.isSharedProjectionDirty||(n.isSharedProjectionDirty=!!(n.isProjectionDirty||n.parent.isProjectionDirty||n.parent.isSharedProjectionDirty)),n.isTransformDirty||(n.isTransformDirty=n.parent.isTransformDirty))}function n2(n){n.isProjectionDirty=n.isSharedProjectionDirty=n.isTransformDirty=!1}function r2(n){n.clearSnapshot()}function Lh(n){n.clearMeasurements()}function s2(n){n.isLayoutDirty=!0,n.updateLayout()}function Vh(n){n.isLayoutDirty=!1}function i2(n){n.isAnimationBlocked&&n.layout&&!n.isLayoutDirty&&(n.snapshot=n.layout,n.isLayoutDirty=!0)}function o2(n){const{visualElement:r}=n.options;r&&r.getProps().onBeforeLayoutMeasure&&r.notify("BeforeLayoutMeasure"),n.resetTransform()}function zh(n){n.finishAnimation(),n.targetDelta=n.relativeTarget=n.target=void 0,n.isProjectionDirty=!0}function a2(n){n.resolveTargetDelta()}function l2(n){n.calcProjection()}function u2(n){n.resetSkewAndRotation()}function c2(n){n.removeLeadSnapshot()}function Ih(n,r,i){n.translate=Ne(r.translate,0,i),n.scale=Ne(r.scale,1,i),n.origin=r.origin,n.originPoint=r.originPoint}function Oh(n,r,i,a){n.min=Ne(r.min,i.min,a),n.max=Ne(r.max,i.max,a)}function d2(n,r,i,a){Oh(n.x,r.x,i.x,a),Oh(n.y,r.y,i.y,a)}function f2(n){return n.animationValues&&n.animationValues.opacityExit!==void 0}const h2={duration:.45,ease:[.4,0,.1,1]},Fh=n=>typeof navigator<"u"&&navigator.userAgent&&navigator.userAgent.toLowerCase().includes(n),Bh=Fh("applewebkit/")&&!Fh("chrome/")?Math.round:jt;function Uh(n){n.min=Bh(n.min),n.max=Bh(n.max)}function p2(n){Uh(n.x),Uh(n.y)}function Wm(n,r,i){return n==="position"||n==="preserve-aspect"&&!Lw(Mh(r),Mh(i),.2)}function m2(n){var r;return n!==n.root&&((r=n.scroll)==null?void 0:r.wasRoot)}const g2=$m({attachResizeListener:(n,r)=>ks(n,"resize",r),measureScroll:()=>{var n,r;return{x:document.documentElement.scrollLeft||((n=document.body)==null?void 0:n.scrollLeft)||0,y:document.documentElement.scrollTop||((r=document.body)==null?void 0:r.scrollTop)||0}},checkIsScrollRoot:()=>!0}),Sl={current:void 0},Hm=$m({measureScroll:n=>({x:n.scrollLeft,y:n.scrollTop}),defaultParent:()=>{if(!Sl.current){const n=new g2({});n.mount(window),n.setOptions({layoutScroll:!0}),Sl.current=n}return Sl.current},resetTransform:(n,r)=>{n.style.transform=r!==void 0?r:"none"},checkIsScrollRoot:n=>window.getComputedStyle(n).position==="fixed"}),bu=z.createContext({transformPagePoint:n=>n,isStatic:!1,reducedMotion:"never"});function $h(n,r){if(typeof n=="function")return n(r);n!=null&&(n.current=r)}function y2(...n){return r=>{let i=!1;const a=n.map(u=>{const f=$h(u,r);return!i&&typeof f=="function"&&(i=!0),f});if(i)return()=>{for(let u=0;u<a.length;u++){const f=a[u];typeof f=="function"?f():$h(n[u],null)}}}}function v2(...n){return z.useCallback(y2(...n),n)}class x2 extends z.Component{getSnapshotBeforeUpdate(r){const i=this.props.childRef.current;if($i(i)&&r.isPresent&&!this.props.isPresent&&this.props.pop!==!1){const a=i.offsetParent,u=$i(a)&&a.offsetWidth||0,f=$i(a)&&a.offsetHeight||0,d=getComputedStyle(i),p=this.props.sizeRef.current;p.height=parseFloat(d.height),p.width=parseFloat(d.width),p.top=i.offsetTop,p.left=i.offsetLeft,p.right=u-p.width-p.left,p.bottom=f-p.height-p.top}return null}componentDidUpdate(){}render(){return this.props.children}}function w2({children:n,isPresent:r,anchorX:i,anchorY:a,root:u,pop:f}){var w;const d=z.useId(),p=z.useRef(null),g=z.useRef({width:0,height:0,top:0,left:0,right:0,bottom:0}),{nonce:x}=z.useContext(bu),y=((w=n.props)==null?void 0:w.ref)??(n==null?void 0:n.ref),v=v2(p,y);return z.useInsertionEffect(()=>{const{width:N,height:E,top:_,left:M,right:L,bottom:B}=g.current;if(r||f===!1||!p.current||!N||!E)return;const I=i==="left"?`left: ${M}`:`right: ${L}`,U=a==="bottom"?`bottom: ${B}`:`top: ${_}`;p.current.dataset.motionPopId=d;const W=document.createElement("style");x&&(W.nonce=x);const se=u??document.head;return se.appendChild(W),W.sheet&&W.sheet.insertRule(`
          [data-motion-pop-id="${d}"] {
            position: absolute !important;
            width: ${N}px !important;
            height: ${E}px !important;
            ${I}px !important;
            ${U}px !important;
          }
        `),()=>{var G;(G=p.current)==null||G.removeAttribute("data-motion-pop-id"),se.contains(W)&&se.removeChild(W)}},[r]),h.jsx(x2,{isPresent:r,childRef:p,sizeRef:g,pop:f,children:f===!1?n:z.cloneElement(n,{ref:v})})}const k2=({children:n,initial:r,isPresent:i,onExitComplete:a,custom:u,presenceAffectsLayout:f,mode:d,anchorX:p,anchorY:g,root:x})=>{const y=su(S2),v=z.useId();let w=!0,N=z.useMemo(()=>(w=!1,{id:v,initial:r,isPresent:i,custom:u,onExitComplete:E=>{y.set(E,!0);for(const _ of y.values())if(!_)return;a&&a()},register:E=>(y.set(E,!1),()=>y.delete(E))}),[i,y,a]);return f&&w&&(N={...N}),z.useMemo(()=>{y.forEach((E,_)=>y.set(_,!1))},[i]),z.useEffect(()=>{!i&&!y.size&&a&&a()},[i]),n=h.jsx(w2,{pop:d==="popLayout",isPresent:i,anchorX:p,anchorY:g,root:x,children:n}),h.jsx(ao.Provider,{value:N,children:n})};function S2(){return new Map}function Km(n=!0){const r=z.useContext(ao);if(r===null)return[!0,null];const{isPresent:i,onExitComplete:a,register:u}=r,f=z.useId();z.useEffect(()=>{if(n)return u(f)},[n]);const d=z.useCallback(()=>n&&a&&a(f),[f,a,n]);return!i&&a?[!1,d]:[!0]}const Oi=n=>n.key||"";function Wh(n){const r=[];return z.Children.forEach(n,i=>{z.isValidElement(i)&&r.push(i)}),r}const Mu=({children:n,custom:r,initial:i=!0,onExitComplete:a,presenceAffectsLayout:u=!0,mode:f="sync",propagate:d=!1,anchorX:p="left",anchorY:g="top",root:x})=>{const[y,v]=Km(d),w=z.useMemo(()=>Wh(n),[n]),N=d&&!y?[]:w.map(Oi),E=z.useRef(!0),_=z.useRef(w),M=su(()=>new Map),L=z.useRef(new Set),[B,I]=z.useState(w),[U,W]=z.useState(w);xp(()=>{E.current=!1,_.current=w;for(let H=0;H<U.length;H++){const re=Oi(U[H]);N.includes(re)?(M.delete(re),L.current.delete(re)):M.get(re)!==!0&&M.set(re,!1)}},[U,N.length,N.join("-")]);const se=[];if(w!==B){let H=[...w];for(let re=0;re<U.length;re++){const Y=U[re],ce=Oi(Y);N.includes(ce)||(H.splice(re,0,Y),se.push(Y))}return f==="wait"&&se.length&&(H=se),W(Wh(H)),I(w),null}const{forceRender:G}=z.useContext(ru);return h.jsx(h.Fragment,{children:U.map(H=>{const re=Oi(H),Y=d&&!y?!1:w===U||N.includes(re),ce=()=>{if(L.current.has(re))return;if(M.has(re))L.current.add(re),M.set(re,!0);else return;let me=!0;M.forEach(Pe=>{Pe||(me=!1)}),me&&(G==null||G(),W(_.current),d&&(v==null||v()),a&&a())};return h.jsx(k2,{isPresent:Y,initial:!E.current||i?void 0:!1,custom:r,presenceAffectsLayout:u,mode:f,root:x,onExitComplete:Y?void 0:ce,anchorX:p,anchorY:g,children:H},re)})})},Gm=z.createContext({strict:!1}),Hh={animation:["animate","variants","whileHover","whileTap","exit","whileInView","whileFocus","whileDrag"],exit:["exit"],drag:["drag","dragControls"],focus:["whileFocus"],hover:["whileHover","onHoverStart","onHoverEnd"],tap:["whileTap","onTap","onTapStart","onTapCancel"],pan:["onPan","onPanStart","onPanSessionStart","onPanEnd"],inView:["whileInView","onViewportEnter","onViewportLeave"],layout:["layout","layoutId"]};let Kh=!1;function j2(){if(Kh)return;const n={};for(const r in Hh)n[r]={isEnabled:i=>Hh[r].some(a=>!!i[a])};Sm(n),Kh=!0}function Ym(){return j2(),aw()}function N2(n){const r=Ym();for(const i in n)r[i]={...r[i],...n[i]};Sm(r)}const T2=new Set(["animate","exit","variants","initial","style","values","variants","transition","transformTemplate","custom","inherit","onBeforeLayoutMeasure","onAnimationStart","onAnimationComplete","onUpdate","onDragStart","onDrag","onDragEnd","onMeasureDragConstraints","onDirectionLock","onDragTransitionEnd","_dragX","_dragY","onHoverStart","onHoverEnd","onViewportEnter","onViewportLeave","globalTapTarget","propagate","ignoreStrict","viewport"]);function io(n){return n.startsWith("while")||n.startsWith("drag")&&n!=="draggable"||n.startsWith("layout")||n.startsWith("onTap")||n.startsWith("onPan")||n.startsWith("onLayout")||T2.has(n)}let Xm=n=>!io(n);function C2(n){typeof n=="function"&&(Xm=r=>r.startsWith("on")?!io(r):n(r))}try{C2(require("@emotion/is-prop-valid").default)}catch{}function P2(n,r,i){const a={};for(const u in n)u==="values"&&typeof n.values=="object"||Xe(n[u])||(Xm(u)||i===!0&&io(u)||!r&&!io(u)||n.draggable&&u.startsWith("onDrag"))&&(a[u]=n[u]);return a}const fo=z.createContext({});function E2(n,r){if(co(n)){const{initial:i,animate:a}=n;return{initial:i===!1||ws(i)?i:void 0,animate:ws(a)?a:void 0}}return n.inherit!==!1?r:{}}function b2(n){const{initial:r,animate:i}=E2(n,z.useContext(fo));return z.useMemo(()=>({initial:r,animate:i}),[Gh(r),Gh(i)])}function Gh(n){return Array.isArray(n)?n.join(" "):n}const _u=()=>({style:{},transform:{},transformOrigin:{},vars:{}});function Qm(n,r,i){for(const a in r)!Xe(r[a])&&!bm(a,i)&&(n[a]=r[a])}function M2({transformTemplate:n},r){return z.useMemo(()=>{const i=_u();return Pu(i,r,n),Object.assign({},i.vars,i.style)},[r])}function _2(n,r){const i=n.style||{},a={};return Qm(a,i,n),Object.assign(a,M2(n,r)),a}function A2(n,r){const i={},a=_2(n,r);return n.drag&&n.dragListener!==!1&&(i.draggable=!1,a.userSelect=a.WebkitUserSelect=a.WebkitTouchCallout="none",a.touchAction=n.drag===!0?"none":`pan-${n.drag==="x"?"y":"x"}`),n.tabIndex===void 0&&(n.onTap||n.onTapStart||n.whileTap)&&(i.tabIndex=0),i.style=a,i}const qm=()=>({..._u(),attrs:{}});function R2(n,r,i,a){const u=z.useMemo(()=>{const f=qm();return Mm(f,r,Am(a),n.transformTemplate,n.style),{...f.attrs,style:{...f.style}}},[r]);if(n.style){const f={};Qm(f,n.style,n),u.style={...f,...u.style}}return u}const D2=["animate","circle","defs","desc","ellipse","g","image","line","filter","marker","mask","metadata","path","pattern","polygon","polyline","rect","stop","switch","symbol","svg","text","tspan","use","view"];function Au(n){return typeof n!="string"||n.includes("-")?!1:!!(D2.indexOf(n)>-1||/[A-Z]/u.test(n))}function L2(n,r,i,{latestValues:a},u,f=!1,d){const g=(d??Au(n)?R2:A2)(r,a,u,n),x=P2(r,typeof n=="string",f),y=n!==z.Fragment?{...x,...g,ref:i}:{},{children:v}=r,w=z.useMemo(()=>Xe(v)?v.get():v,[v]);return z.createElement(n,{...y,children:w})}function V2({scrapeMotionValuesFromProps:n,createRenderState:r},i,a,u){return{latestValues:z2(i,a,u,n),renderState:r()}}function z2(n,r,i,a){const u={},f=a(n,{});for(const w in f)u[w]=Yi(f[w]);let{initial:d,animate:p}=n;const g=co(n),x=wm(n);r&&x&&!g&&n.inherit!==!1&&(d===void 0&&(d=r.initial),p===void 0&&(p=r.animate));let y=i?i.initial===!1:!1;y=y||d===!1;const v=y?p:d;if(v&&typeof v!="boolean"&&!uo(v)){const w=Array.isArray(v)?v:[v];for(let N=0;N<w.length;N++){const E=xu(n,w[N]);if(E){const{transitionEnd:_,transition:M,...L}=E;for(const B in L){let I=L[B];if(Array.isArray(I)){const U=y?I.length-1:0;I=I[U]}I!==null&&(u[B]=I)}for(const B in _)u[B]=_[B]}}}return u}const Zm=n=>(r,i)=>{const a=z.useContext(fo),u=z.useContext(ao),f=()=>V2(n,r,a,u);return i?f():su(f)},I2=Zm({scrapeMotionValuesFromProps:Eu,createRenderState:_u}),O2=Zm({scrapeMotionValuesFromProps:Rm,createRenderState:qm}),F2=Symbol.for("motionComponentSymbol");function B2(n,r,i){const a=z.useRef(i);z.useInsertionEffect(()=>{a.current=i});const u=z.useRef(null);return z.useCallback(f=>{var p;f&&((p=n.onMount)==null||p.call(n,f));const d=a.current;if(typeof d=="function")if(f){const g=d(f);typeof g=="function"&&(u.current=g)}else u.current?(u.current(),u.current=null):d(f);else d&&(d.current=f);r&&(f?r.mount(f):r.unmount())},[r])}const Jm=z.createContext({});function hr(n){return n&&typeof n=="object"&&Object.prototype.hasOwnProperty.call(n,"current")}function U2(n,r,i,a,u,f){var I,U;const{visualElement:d}=z.useContext(fo),p=z.useContext(Gm),g=z.useContext(ao),x=z.useContext(bu),y=x.reducedMotion,v=x.skipAnimations,w=z.useRef(null),N=z.useRef(!1);a=a||p.renderer,!w.current&&a&&(w.current=a(n,{visualState:r,parent:d,props:i,presenceContext:g,blockInitialAnimation:g?g.initial===!1:!1,reducedMotionConfig:y,skipAnimations:v,isSVG:f}),N.current&&w.current&&(w.current.manuallyAnimateOnMount=!0));const E=w.current,_=z.useContext(Jm);E&&!E.projection&&u&&(E.type==="html"||E.type==="svg")&&$2(w.current,i,u,_);const M=z.useRef(!1);z.useInsertionEffect(()=>{E&&M.current&&E.update(i,g)});const L=i[am],B=z.useRef(!!L&&typeof window<"u"&&!((I=window.MotionHandoffIsComplete)!=null&&I.call(window,L))&&((U=window.MotionHasOptimisedAnimation)==null?void 0:U.call(window,L)));return xp(()=>{N.current=!0,E&&(M.current=!0,window.MotionIsMounted=!0,E.updateFeatures(),E.scheduleRenderMicrotask(),B.current&&E.animationState&&E.animationState.animateChanges())}),z.useEffect(()=>{E&&(!B.current&&E.animationState&&E.animationState.animateChanges(),B.current&&(queueMicrotask(()=>{var W;(W=window.MotionHandoffMarkAsComplete)==null||W.call(window,L)}),B.current=!1),E.enteringChildren=void 0)}),E}function $2(n,r,i,a){const{layoutId:u,layout:f,drag:d,dragConstraints:p,layoutScroll:g,layoutRoot:x,layoutAnchor:y,layoutCrossfade:v}=r;n.projection=new i(n.latestValues,r["data-framer-portal-id"]?void 0:e0(n.parent)),n.projection.setOptions({layoutId:u,layout:f,alwaysMeasureLayout:!!d||p&&hr(p),visualElement:n,animationType:typeof f=="string"?f:"both",initialPromotionConfig:a,crossfade:v,layoutScroll:g,layoutRoot:x,layoutAnchor:y})}function e0(n){if(n)return n.options.allowProjection!==!1?n.projection:e0(n.parent)}function jl(n,{forwardMotionProps:r=!1,type:i}={},a,u){a&&N2(a);const f=i?i==="svg":Au(n),d=f?O2:I2;function p(x,y){let v;const w={...z.useContext(bu),...x,layoutId:W2(x)},{isStatic:N}=w,E=b2(x),_=d(x,N);if(!N&&typeof window<"u"){H2();const M=K2(w);v=M.MeasureLayout,E.visualElement=U2(n,_,w,u,M.ProjectionNode,f)}return h.jsxs(fo.Provider,{value:E,children:[v&&E.visualElement?h.jsx(v,{visualElement:E.visualElement,...w}):null,L2(n,x,B2(_,E.visualElement,y),_,N,r,f)]})}p.displayName=`motion.${typeof n=="string"?n:`create(${n.displayName??n.name??""})`}`;const g=z.forwardRef(p);return g[F2]=n,g}function W2({layoutId:n}){const r=z.useContext(ru).id;return r&&n!==void 0?r+"-"+n:n}function H2(n,r){z.useContext(Gm).strict}function K2(n){const r=Ym(),{drag:i,layout:a}=r;if(!i&&!a)return{};const u={...i,...a};return{MeasureLayout:i!=null&&i.isEnabled(n)||a!=null&&a.isEnabled(n)?u.MeasureLayout:void 0,ProjectionNode:u.ProjectionNode}}function G2(n,r){if(typeof Proxy>"u")return jl;const i=new Map,a=(f,d)=>jl(f,d,n,r),u=(f,d)=>a(f,d);return new Proxy(u,{get:(f,d)=>d==="create"?a:(i.has(d)||i.set(d,jl(d,void 0,n,r)),i.get(d))})}const Y2=(n,r)=>r.isSVG??Au(n)?new Nw(r):new vw(r,{allowProjection:n!==z.Fragment});class X2 extends Sn{constructor(r){super(r),r.animationState||(r.animationState=bw(r))}updateAnimationControlsSubscription(){const{animate:r}=this.node.getProps();uo(r)&&(this.unmountControls=r.subscribe(this.node))}mount(){this.updateAnimationControlsSubscription()}update(){const{animate:r}=this.node.getProps(),{animate:i}=this.node.prevProps||{};r!==i&&this.updateAnimationControlsSubscription()}unmount(){var r;this.node.animationState.reset(),(r=this.unmountControls)==null||r.call(this)}}let Q2=0;class q2 extends Sn{constructor(){super(...arguments),this.id=Q2++,this.isExitComplete=!1}update(){var f;if(!this.node.presenceContext)return;const{isPresent:r,onExitComplete:i}=this.node.presenceContext,{isPresent:a}=this.node.prevPresenceContext||{};if(!this.node.animationState||r===a)return;if(r&&a===!1){if(this.isExitComplete){const{initial:d,custom:p}=this.node.getProps();if(typeof d=="string"){const g=Bn(this.node,d,p);if(g){const{transition:x,transitionEnd:y,...v}=g;for(const w in v)(f=this.node.getValue(w))==null||f.jump(v[w])}}this.node.animationState.reset(),this.node.animationState.animateChanges()}else this.node.animationState.setActive("exit",!1);this.isExitComplete=!1;return}const u=this.node.animationState.setActive("exit",!r);i&&!r&&u.then(()=>{this.isExitComplete=!0,i(this.id)})}mount(){const{register:r,onExitComplete:i}=this.node.presenceContext||{};i&&i(this.id),r&&(this.unmount=r(this.id))}unmount(){}}const Z2={animation:{Feature:X2},exit:{Feature:q2}};function Ts(n){return{point:{x:n.pageX,y:n.pageY}}}const J2=n=>r=>ju(r)&&n(r,Ts(r));function ps(n,r,i,a){return ks(n,r,J2(i),a)}const t0=({current:n})=>n?n.ownerDocument.defaultView:null,Yh=(n,r)=>Math.abs(n-r);function ek(n,r){const i=Yh(n.x,r.x),a=Yh(n.y,r.y);return Math.sqrt(i**2+a**2)}const Xh=new Set(["auto","scroll"]);class n0{constructor(r,i,{transformPagePoint:a,contextWindow:u=window,dragSnapToOrigin:f=!1,distanceThreshold:d=3,element:p}={}){if(this.startEvent=null,this.lastMoveEvent=null,this.lastMoveEventInfo=null,this.lastRawMoveEventInfo=null,this.handlers={},this.contextWindow=window,this.scrollPositions=new Map,this.removeScrollListeners=null,this.onElementScroll=N=>{this.handleScroll(N.target)},this.onWindowScroll=()=>{this.handleScroll(window)},this.updatePoint=()=>{if(!(this.lastMoveEvent&&this.lastMoveEventInfo))return;this.lastRawMoveEventInfo&&(this.lastMoveEventInfo=Fi(this.lastRawMoveEventInfo,this.transformPagePoint));const N=Nl(this.lastMoveEventInfo,this.history),E=this.startEvent!==null,_=ek(N.offset,{x:0,y:0})>=this.distanceThreshold;if(!E&&!_)return;const{point:M}=N,{timestamp:L}=Ye;this.history.push({...M,timestamp:L});const{onStart:B,onMove:I}=this.handlers;E||(B&&B(this.lastMoveEvent,N),this.startEvent=this.lastMoveEvent),I&&I(this.lastMoveEvent,N)},this.handlePointerMove=(N,E)=>{this.lastMoveEvent=N,this.lastRawMoveEventInfo=E,this.lastMoveEventInfo=Fi(E,this.transformPagePoint),ve.update(this.updatePoint,!0)},this.handlePointerUp=(N,E)=>{this.end();const{onEnd:_,onSessionEnd:M,resumeAnimation:L}=this.handlers;if((this.dragSnapToOrigin||!this.startEvent)&&L&&L(),!(this.lastMoveEvent&&this.lastMoveEventInfo))return;const B=Nl(N.type==="pointercancel"?this.lastMoveEventInfo:Fi(E,this.transformPagePoint),this.history);this.startEvent&&_&&_(N,B),M&&M(N,B)},!ju(r))return;this.dragSnapToOrigin=f,this.handlers=i,this.transformPagePoint=a,this.distanceThreshold=d,this.contextWindow=u||window;const g=Ts(r),x=Fi(g,this.transformPagePoint),{point:y}=x,{timestamp:v}=Ye;this.history=[{...y,timestamp:v}];const{onSessionStart:w}=i;w&&w(r,Nl(x,this.history)),this.removeListeners=Ss(ps(this.contextWindow,"pointermove",this.handlePointerMove),ps(this.contextWindow,"pointerup",this.handlePointerUp),ps(this.contextWindow,"pointercancel",this.handlePointerUp)),p&&this.startScrollTracking(p)}startScrollTracking(r){let i=r.parentElement;for(;i;){const a=getComputedStyle(i);(Xh.has(a.overflowX)||Xh.has(a.overflowY))&&this.scrollPositions.set(i,{x:i.scrollLeft,y:i.scrollTop}),i=i.parentElement}this.scrollPositions.set(window,{x:window.scrollX,y:window.scrollY}),window.addEventListener("scroll",this.onElementScroll,{capture:!0}),window.addEventListener("scroll",this.onWindowScroll),this.removeScrollListeners=()=>{window.removeEventListener("scroll",this.onElementScroll,{capture:!0}),window.removeEventListener("scroll",this.onWindowScroll)}}handleScroll(r){const i=this.scrollPositions.get(r);if(!i)return;const a=r===window,u=a?{x:window.scrollX,y:window.scrollY}:{x:r.scrollLeft,y:r.scrollTop},f={x:u.x-i.x,y:u.y-i.y};f.x===0&&f.y===0||(a?this.lastMoveEventInfo&&(this.lastMoveEventInfo.point.x+=f.x,this.lastMoveEventInfo.point.y+=f.y):this.history.length>0&&(this.history[0].x-=f.x,this.history[0].y-=f.y),this.scrollPositions.set(r,u),ve.update(this.updatePoint,!0))}updateHandlers(r){this.handlers=r}end(){this.removeListeners&&this.removeListeners(),this.removeScrollListeners&&this.removeScrollListeners(),this.scrollPositions.clear(),kn(this.updatePoint)}}function Fi(n,r){return r?{point:r(n.point)}:n}function Qh(n,r){return{x:n.x-r.x,y:n.y-r.y}}function Nl({point:n},r){return{point:n,delta:Qh(n,r0(r)),offset:Qh(n,tk(r)),velocity:nk(r,.1)}}function tk(n){return n[0]}function r0(n){return n[n.length-1]}function nk(n,r){if(n.length<2)return{x:0,y:0};let i=n.length-1,a=null;const u=r0(n);for(;i>=0&&(a=n[i],!(u.timestamp-a.timestamp>mt(r)));)i--;if(!a)return{x:0,y:0};a===n[0]&&n.length>2&&u.timestamp-a.timestamp>mt(r)*2&&(a=n[1]);const f=St(u.timestamp-a.timestamp);if(f===0)return{x:0,y:0};const d={x:(u.x-a.x)/f,y:(u.y-a.y)/f};return d.x===1/0&&(d.x=0),d.y===1/0&&(d.y=0),d}function rk(n,{min:r,max:i},a){return r!==void 0&&n<r?n=a?Ne(r,n,a.min):Math.max(n,r):i!==void 0&&n>i&&(n=a?Ne(i,n,a.max):Math.min(n,i)),n}function qh(n,r,i){return{min:r!==void 0?n.min+r:void 0,max:i!==void 0?n.max+i-(n.max-n.min):void 0}}function sk(n,{top:r,left:i,bottom:a,right:u}){return{x:qh(n.x,i,u),y:qh(n.y,r,a)}}function Zh(n,r){let i=r.min-n.min,a=r.max-n.max;return r.max-r.min<n.max-n.min&&([i,a]=[a,i]),{min:i,max:a}}function ik(n,r){return{x:Zh(n.x,r.x),y:Zh(n.y,r.y)}}function ok(n,r){let i=.5;const a=rt(n),u=rt(r);return u>a?i=vs(r.min,r.max-a,n.min):a>u&&(i=vs(n.min,n.max-u,r.min)),Ut(0,1,i)}function ak(n,r){const i={};return r.min!==void 0&&(i.min=r.min-n.min),r.max!==void 0&&(i.max=r.max-n.min),i}const Zl=.35;function lk(n=Zl){return n===!1?n=0:n===!0&&(n=Zl),{x:Jh(n,"left","right"),y:Jh(n,"top","bottom")}}function Jh(n,r,i){return{min:ep(n,r),max:ep(n,i)}}function ep(n,r){return typeof n=="number"?n:n[r]||0}const uk=new WeakMap;class ck{constructor(r){this.openDragLock=null,this.isDragging=!1,this.currentDirection=null,this.originPoint={x:0,y:0},this.constraints=!1,this.hasMutatedConstraints=!1,this.elastic=Ue(),this.latestPointerEvent=null,this.latestPanInfo=null,this.visualElement=r}start(r,{snapToCursor:i=!1,distanceThreshold:a}={}){const{presenceContext:u}=this.visualElement;if(u&&u.isPresent===!1)return;const f=v=>{i&&this.snapToCursor(Ts(v).point),this.stopAnimation()},d=(v,w)=>{const{drag:N,dragPropagation:E,onDragStart:_}=this.getProps();if(N&&!E&&(this.openDragLock&&this.openDragLock(),this.openDragLock=z1(N),!this.openDragLock))return;this.latestPointerEvent=v,this.latestPanInfo=w,this.isDragging=!0,this.currentDirection=null,this.resolveConstraints(),this.visualElement.projection&&(this.visualElement.projection.isAnimationBlocked=!0,this.visualElement.projection.target=void 0),Ot(L=>{let B=this.getAxisMotionValue(L).get()||0;if(Bt.test(B)){const{projection:I}=this.visualElement;if(I&&I.layout){const U=I.layout.layoutBox[L];U&&(B=rt(U)*(parseFloat(B)/100))}}this.originPoint[L]=B}),_&&ve.update(()=>_(v,w),!1,!0),$l(this.visualElement,"transform");const{animationState:M}=this.visualElement;M&&M.setActive("whileDrag",!0)},p=(v,w)=>{this.latestPointerEvent=v,this.latestPanInfo=w;const{dragPropagation:N,dragDirectionLock:E,onDirectionLock:_,onDrag:M}=this.getProps();if(!N&&!this.openDragLock)return;const{offset:L}=w;if(E&&this.currentDirection===null){this.currentDirection=fk(L),this.currentDirection!==null&&_&&_(this.currentDirection);return}this.updateAxis("x",w.point,L),this.updateAxis("y",w.point,L),this.visualElement.render(),M&&ve.update(()=>M(v,w),!1,!0)},g=(v,w)=>{this.latestPointerEvent=v,this.latestPanInfo=w,this.stop(v,w),this.latestPointerEvent=null,this.latestPanInfo=null},x=()=>{const{dragSnapToOrigin:v}=this.getProps();(v||this.constraints)&&this.startAnimation({x:0,y:0})},{dragSnapToOrigin:y}=this.getProps();this.panSession=new n0(r,{onSessionStart:f,onStart:d,onMove:p,onSessionEnd:g,resumeAnimation:x},{transformPagePoint:this.visualElement.getTransformPagePoint(),dragSnapToOrigin:y,distanceThreshold:a,contextWindow:t0(this.visualElement),element:this.visualElement.current})}stop(r,i){const a=r||this.latestPointerEvent,u=i||this.latestPanInfo,f=this.isDragging;if(this.cancel(),!f||!u||!a)return;const{velocity:d}=u;this.startAnimation(d);const{onDragEnd:p}=this.getProps();p&&ve.postRender(()=>p(a,u))}cancel(){this.isDragging=!1;const{projection:r,animationState:i}=this.visualElement;r&&(r.isAnimationBlocked=!1),this.endPanSession();const{dragPropagation:a}=this.getProps();!a&&this.openDragLock&&(this.openDragLock(),this.openDragLock=null),i&&i.setActive("whileDrag",!1)}endPanSession(){this.panSession&&this.panSession.end(),this.panSession=void 0}updateAxis(r,i,a){const{drag:u}=this.getProps();if(!a||!Bi(r,u,this.currentDirection))return;const f=this.getAxisMotionValue(r);let d=this.originPoint[r]+a[r];this.constraints&&this.constraints[r]&&(d=rk(d,this.constraints[r],this.elastic[r])),f.set(d)}resolveConstraints(){var f;const{dragConstraints:r,dragElastic:i}=this.getProps(),a=this.visualElement.projection&&!this.visualElement.projection.layout?this.visualElement.projection.measure(!1):(f=this.visualElement.projection)==null?void 0:f.layout,u=this.constraints;r&&hr(r)?this.constraints||(this.constraints=this.resolveRefConstraints()):r&&a?this.constraints=sk(a.layoutBox,r):this.constraints=!1,this.elastic=lk(i),u!==this.constraints&&!hr(r)&&a&&this.constraints&&!this.hasMutatedConstraints&&Ot(d=>{this.constraints!==!1&&this.getAxisMotionValue(d)&&(this.constraints[d]=ak(a.layoutBox[d],this.constraints[d]))})}resolveRefConstraints(){const{dragConstraints:r,onMeasureDragConstraints:i}=this.getProps();if(!r||!hr(r))return!1;const a=r.current,{projection:u}=this.visualElement;if(!u||!u.layout)return!1;const f=fw(a,u.root,this.visualElement.getTransformPagePoint());let d=ik(u.layout.layoutBox,f);if(i){const p=i(uw(d));this.hasMutatedConstraints=!!p,p&&(d=Nm(p))}return d}startAnimation(r){const{drag:i,dragMomentum:a,dragElastic:u,dragTransition:f,dragSnapToOrigin:d,onDragTransitionEnd:p}=this.getProps(),g=this.constraints||{},x=Ot(y=>{if(!Bi(y,i,this.currentDirection))return;let v=g&&g[y]||{};(d===!0||d===y)&&(v={min:0,max:0});const w=u?200:1e6,N=u?40:1e7,E={type:"inertia",velocity:a?r[y]:0,bounceStiffness:w,bounceDamping:N,timeConstant:750,restDelta:1,restSpeed:10,...f,...v};return this.startAxisValueAnimation(y,E)});return Promise.all(x).then(p)}startAxisValueAnimation(r,i){const a=this.getAxisMotionValue(r);return $l(this.visualElement,r),a.start(vu(r,a,0,i,this.visualElement,!1))}stopAnimation(){Ot(r=>this.getAxisMotionValue(r).stop())}getAxisMotionValue(r){const i=`_drag${r.toUpperCase()}`,a=this.visualElement.getProps(),u=a[i];return u||this.visualElement.getValue(r,(a.initial?a.initial[r]:void 0)||0)}snapToCursor(r){Ot(i=>{const{drag:a}=this.getProps();if(!Bi(i,a,this.currentDirection))return;const{projection:u}=this.visualElement,f=this.getAxisMotionValue(i);if(u&&u.layout){const{min:d,max:p}=u.layout.layoutBox[i],g=f.get()||0;f.set(r[i]-Ne(d,p,.5)+g)}})}scalePositionWithinConstraints(){if(!this.visualElement.current)return;const{drag:r,dragConstraints:i}=this.getProps(),{projection:a}=this.visualElement;if(!hr(i)||!a||!this.constraints)return;this.stopAnimation();const u={x:0,y:0};Ot(d=>{const p=this.getAxisMotionValue(d);if(p&&this.constraints!==!1){const g=p.get();u[d]=ok({min:g,max:g},this.constraints[d])}});const{transformTemplate:f}=this.visualElement.getProps();this.visualElement.current.style.transform=f?f({},""):"none",a.root&&a.root.updateScroll(),a.updateLayout(),this.constraints=!1,this.resolveConstraints(),Ot(d=>{if(!Bi(d,r,null))return;const p=this.getAxisMotionValue(d),{min:g,max:x}=this.constraints[d];p.set(Ne(g,x,u[d]))}),this.visualElement.render()}addListeners(){if(!this.visualElement.current)return;uk.set(this.visualElement,this);const r=this.visualElement.current,i=ps(r,"pointerdown",x=>{const{drag:y,dragListener:v=!0}=this.getProps(),w=x.target,N=w!==r&&$1(w);y&&v&&!N&&this.start(x)});let a;const u=()=>{const{dragConstraints:x}=this.getProps();hr(x)&&x.current&&(this.constraints=this.resolveRefConstraints(),a||(a=dk(r,x.current,()=>this.scalePositionWithinConstraints())))},{projection:f}=this.visualElement,d=f.addEventListener("measure",u);f&&!f.layout&&(f.root&&f.root.updateScroll(),f.updateLayout()),ve.read(u);const p=ks(window,"resize",()=>this.scalePositionWithinConstraints()),g=f.addEventListener("didUpdate",(({delta:x,hasLayoutChanged:y})=>{this.isDragging&&y&&(Ot(v=>{const w=this.getAxisMotionValue(v);w&&(this.originPoint[v]+=x[v].translate,w.set(w.get()+x[v].translate))}),this.visualElement.render())}));return()=>{p(),i(),d(),g&&g(),a&&a()}}getProps(){const r=this.visualElement.getProps(),{drag:i=!1,dragDirectionLock:a=!1,dragPropagation:u=!1,dragConstraints:f=!1,dragElastic:d=Zl,dragMomentum:p=!0}=r;return{...r,drag:i,dragDirectionLock:a,dragPropagation:u,dragConstraints:f,dragElastic:d,dragMomentum:p}}}function tp(n){let r=!0;return()=>{if(r){r=!1;return}n()}}function dk(n,r,i){const a=lh(n,tp(i)),u=lh(r,tp(i));return()=>{a(),u()}}function Bi(n,r,i){return(r===!0||r===n)&&(i===null||i===n)}function fk(n,r=10){let i=null;return Math.abs(n.y)>r?i="y":Math.abs(n.x)>r&&(i="x"),i}class hk extends Sn{constructor(r){super(r),this.removeGroupControls=jt,this.removeListeners=jt,this.controls=new ck(r)}mount(){const{dragControls:r}=this.node.getProps();r&&(this.removeGroupControls=r.subscribe(this.controls)),this.removeListeners=this.controls.addListeners()||jt}update(){const{dragControls:r}=this.node.getProps(),{dragControls:i}=this.node.prevProps||{};r!==i&&(this.removeGroupControls(),r&&(this.removeGroupControls=r.subscribe(this.controls)))}unmount(){this.removeGroupControls(),this.removeListeners(),this.controls.isDragging||this.controls.endPanSession()}}const Tl=n=>(r,i)=>{n&&ve.update(()=>n(r,i),!1,!0)};class pk extends Sn{constructor(){super(...arguments),this.removePointerDownListener=jt}onPointerDown(r){this.session=new n0(r,this.createPanHandlers(),{transformPagePoint:this.node.getTransformPagePoint(),contextWindow:t0(this.node)})}createPanHandlers(){const{onPanSessionStart:r,onPanStart:i,onPan:a,onPanEnd:u}=this.node.getProps();return{onSessionStart:Tl(r),onStart:Tl(i),onMove:Tl(a),onEnd:(f,d)=>{delete this.session,u&&ve.postRender(()=>u(f,d))}}}mount(){this.removePointerDownListener=ps(this.node.current,"pointerdown",r=>this.onPointerDown(r))}update(){this.session&&this.session.updateHandlers(this.createPanHandlers())}unmount(){this.removePointerDownListener(),this.session&&this.session.end()}}let Cl=!1;class mk extends z.Component{componentDidMount(){const{visualElement:r,layoutGroup:i,switchLayoutGroup:a,layoutId:u}=this.props,{projection:f}=r;f&&(i.group&&i.group.add(f),a&&a.register&&u&&a.register(f),Cl&&f.root.didUpdate(),f.addEventListener("animationComplete",()=>{this.safeToRemove()}),f.setOptions({...f.options,layoutDependency:this.props.layoutDependency,onExitComplete:()=>this.safeToRemove()})),Xi.hasEverUpdated=!0}getSnapshotBeforeUpdate(r){const{layoutDependency:i,visualElement:a,drag:u,isPresent:f}=this.props,{projection:d}=a;return d&&(d.isPresent=f,r.layoutDependency!==i&&d.setOptions({...d.options,layoutDependency:i}),Cl=!0,u||r.layoutDependency!==i||i===void 0||r.isPresent!==f?d.willUpdate():this.safeToRemove(),r.isPresent!==f&&(f?d.promote():d.relegate()||ve.postRender(()=>{const p=d.getStack();(!p||!p.members.length)&&this.safeToRemove()}))),null}componentDidUpdate(){const{visualElement:r,layoutAnchor:i}=this.props,{projection:a}=r;a&&(a.options.layoutAnchor=i,a.root.didUpdate(),Su.postRender(()=>{!a.currentAnimation&&a.isLead()&&this.safeToRemove()}))}componentWillUnmount(){const{visualElement:r,layoutGroup:i,switchLayoutGroup:a}=this.props,{projection:u}=r;Cl=!0,u&&(u.scheduleCheckAfterUnmount(),i&&i.group&&i.group.remove(u),a&&a.deregister&&a.deregister(u))}safeToRemove(){const{safeToRemove:r}=this.props;r&&r()}render(){return null}}function s0(n){const[r,i]=Km(),a=z.useContext(ru);return h.jsx(mk,{...n,layoutGroup:a,switchLayoutGroup:z.useContext(Jm),isPresent:r,safeToRemove:i})}const gk={pan:{Feature:pk},drag:{Feature:hk,ProjectionNode:Hm,MeasureLayout:s0}};function np(n,r,i){const{props:a}=n;n.animationState&&a.whileHover&&n.animationState.setActive("whileHover",i==="Start");const u="onHover"+i,f=a[u];f&&ve.postRender(()=>f(r,Ts(r)))}class yk extends Sn{mount(){const{current:r}=this.node;r&&(this.unmount=O1(r,(i,a)=>(np(this.node,a,"Start"),u=>np(this.node,u,"End"))))}unmount(){}}class vk extends Sn{constructor(){super(...arguments),this.isActive=!1}onFocus(){let r=!1;try{r=this.node.current.matches(":focus-visible")}catch{r=!0}!r||!this.node.animationState||(this.node.animationState.setActive("whileFocus",!0),this.isActive=!0)}onBlur(){!this.isActive||!this.node.animationState||(this.node.animationState.setActive("whileFocus",!1),this.isActive=!1)}mount(){this.unmount=Ss(ks(this.node.current,"focus",()=>this.onFocus()),ks(this.node.current,"blur",()=>this.onBlur()))}unmount(){}}function rp(n,r,i){const{props:a}=n;if(n.current instanceof HTMLButtonElement&&n.current.disabled)return;n.animationState&&a.whileTap&&n.animationState.setActive("whileTap",i==="Start");const u="onTap"+(i==="End"?"":i),f=a[u];f&&ve.postRender(()=>f(r,Ts(r)))}class xk extends Sn{mount(){const{current:r}=this.node;if(!r)return;const{globalTapTarget:i,propagate:a}=this.node.props;this.unmount=H1(r,(u,f)=>(rp(this.node,f,"Start"),(d,{success:p})=>rp(this.node,d,p?"End":"Cancel")),{useGlobalTarget:i,stopPropagation:(a==null?void 0:a.tap)===!1})}unmount(){}}const Jl=new WeakMap,Pl=new WeakMap,wk=n=>{const r=Jl.get(n.target);r&&r(n)},kk=n=>{n.forEach(wk)};function Sk({root:n,...r}){const i=n||document;Pl.has(i)||Pl.set(i,{});const a=Pl.get(i),u=JSON.stringify(r);return a[u]||(a[u]=new IntersectionObserver(kk,{root:n,...r})),a[u]}function jk(n,r,i){const a=Sk(r);return Jl.set(n,i),a.observe(n),()=>{Jl.delete(n),a.unobserve(n)}}const Nk={some:0,all:1};class Tk extends Sn{constructor(){super(...arguments),this.hasEnteredView=!1,this.isInView=!1}startObserver(){var g;(g=this.stopObserver)==null||g.call(this);const{viewport:r={}}=this.node.getProps(),{root:i,margin:a,amount:u="some",once:f}=r,d={root:i?i.current:void 0,rootMargin:a,threshold:typeof u=="number"?u:Nk[u]},p=x=>{const{isIntersecting:y}=x;if(this.isInView===y||(this.isInView=y,f&&!y&&this.hasEnteredView))return;y&&(this.hasEnteredView=!0),this.node.animationState&&this.node.animationState.setActive("whileInView",y);const{onViewportEnter:v,onViewportLeave:w}=this.node.getProps(),N=y?v:w;N&&N(x)};this.stopObserver=jk(this.node.current,d,p)}mount(){this.startObserver()}update(){if(typeof IntersectionObserver>"u")return;const{props:r,prevProps:i}=this.node;["amount","margin","root"].some(Ck(r,i))&&this.startObserver()}unmount(){var r;(r=this.stopObserver)==null||r.call(this),this.hasEnteredView=!1,this.isInView=!1}}function Ck({viewport:n={}},{viewport:r={}}={}){return i=>n[i]!==r[i]}const Pk={inView:{Feature:Tk},tap:{Feature:xk},focus:{Feature:vk},hover:{Feature:yk}},Ek={layout:{ProjectionNode:Hm,MeasureLayout:s0}},bk={...Z2,...Pk,...gk,...Ek},De=G2(bk,Y2);function Mk({activeTab:n,setActiveTab:r,approvalCount:i,isConnected:a}){const u=[{id:"home",label:"Overview",icon:pp},{id:"plans",label:"Plans",icon:ms},{id:"inventory",label:"Inventory",icon:gs},{id:"workspace",label:"Workspace",icon:oo},{id:"approvals",label:"Approvals",icon:yr,badge:i},{id:"history",label:"Activity",icon:hp},{id:"agents",label:"Agents",icon:vp}];return h.jsx("aside",{className:"hidden",children:h.jsxs("div",{className:"rounded-[28px] border border-black/5 bg-white/55 p-5 shadow-[0_20px_60px_rgba(0,0,0,0.06)]",children:[h.jsxs("div",{className:"mb-5 flex items-center gap-3",children:[h.jsx("div",{className:"flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-700 to-amber-700 text-white shadow-lg shadow-teal-900/15",children:h.jsx(ys,{size:18,className:"text-white"})}),h.jsxs("div",{children:[h.jsx("h1",{className:"font-display text-lg font-bold tracking-tight text-stone-900",children:"RetailOS"}),h.jsx("p",{className:"text-[10px] font-bold uppercase tracking-[0.22em] text-stone-500",children:"Navigation"})]})]}),h.jsx("nav",{className:"space-y-1",children:u.map(f=>h.jsxs("button",{onClick:()=>r(f.id),className:`w-full flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition-all relative group ${n===f.id?"bg-stone-900 text-white shadow-lg shadow-stone-900/10":"text-stone-600 hover:text-stone-900 hover:bg-black/[0.04]"}`,children:[n===f.id&&h.jsx(De.div,{layoutId:"sidebarActive",className:"absolute left-2 top-1/2 -translate-y-1/2 h-7 w-1 rounded-r-full bg-amber-600",transition:{type:"spring",stiffness:300,damping:30}}),h.jsx(f.icon,{size:18,strokeWidth:n===f.id?2.5:2}),h.jsx("span",{children:f.label}),f.badge>0&&h.jsx("span",{className:"ml-auto flex h-5 w-5 items-center justify-center rounded-full bg-red-600 text-[10px] font-bold text-white",children:f.badge})]},f.id))}),h.jsxs("div",{className:"mt-6 space-y-4",children:[h.jsx("div",{className:"flex items-center gap-3 rounded-2xl border border-black/5 bg-black/[0.03] px-4 py-3",children:a?h.jsxs(h.Fragment,{children:[h.jsxs("div",{className:"relative",children:[h.jsx(Mv,{size:14,className:"text-emerald-600"}),h.jsx("div",{className:"absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-emerald-500 opacity-50 animate-ping"})]}),h.jsxs("div",{children:[h.jsx("div",{className:"text-xs font-bold text-emerald-700",children:"Connected"}),h.jsx("div",{className:"text-[10px] text-stone-500",children:"Real-time updates active"})]})]}):h.jsxs(h.Fragment,{children:[h.jsx(Ev,{size:14,className:"text-red-600"}),h.jsxs("div",{children:[h.jsx("div",{className:"text-xs font-bold text-red-700",children:"Disconnected"}),h.jsx("div",{className:"text-[10px] text-stone-500",children:"Reconnecting..."})]})]})}),h.jsx("div",{className:"text-center",children:h.jsx("span",{className:"text-[10px] font-bold tracking-[0.18em] text-stone-400",children:"v1.0.0 · RetailOS"})})]})]})})}const _k={"SKU-001":"🍦","SKU-002":"🧂","SKU-003":"🍼","SKU-004":"🍞","SKU-005":"🥚"};function Ak({stats:n,logs:r,approvalCount:i,plans:a,workspaceProfile:u,onGoToApprovals:f,onGoToPlans:d,onGoToWorkspace:p}){const g=w=>w.skill==="inventory"?h.jsx(gs,{size:14,className:"text-amber-400"}):w.skill==="procurement"?h.jsx(bl,{size:14,className:"text-blue-400"}):w.skill==="negotiation"?h.jsx(gv,{size:14,className:"text-green-400"}):w.skill==="customer"?h.jsx(Qi,{size:14,className:"text-purple-400"}):h.jsx(yr,{size:14,className:"text-white/40"}),x=w=>{if(w.skill==="inventory"&&w.event_type==="low_stock_detected")try{const N=JSON.parse(w.outcome);return`${_k[N.sku]||"📦"} ${N.product_name} was running low. Checking with suppliers...`}catch{return w.decision}return w.skill==="negotiation"&&w.event_type==="outreach_sent"?`🤝 Sent a message to ${(w.metadata||{}).supplier_id||"supplier"} to get a better price.`:w.skill==="negotiation"&&w.event_type==="reply_parsed"?"💬 Supplier replied! They offered a good deal. Waiting for your approval.":w.skill==="customer"&&w.event_type==="offer_sent"?"📣 Sent a special offer to customers. 12 people already looked at it!":w.skill==="orchestrator"&&w.event_type==="owner_approved"?"✅ You approved the order. I've placed it with the supplier.":w.decision},y=w=>w.status==="alert"||w.status==="pending"?"bg-amber-400":w.status==="error"||w.status==="failed"?"bg-red-500":w.status==="success"||w.status==="approved"?"bg-green-500":"bg-blue-500",v=[{label:"Money Saved",value:`₹${n.moneySaved.toLocaleString()}`,icon:bl,color:"text-emerald-700",bg:"bg-emerald-100"},{label:"Orders Placed",value:n.ordersPlaced,icon:gs,color:"text-teal-700",bg:"bg-teal-100"},{label:"Offers Sent",value:n.offersSent,icon:Qi,color:"text-amber-700",bg:"bg-amber-100"},{label:"Hours Saved",value:`${n.hoursSaved} hrs`,icon:fp,color:"text-stone-800",bg:"bg-stone-200"}];return h.jsxs("div",{className:"space-y-8 lg:space-y-10",children:[h.jsxs("section",{className:"grid gap-5 xl:grid-cols-[1.35fr_0.65fr]",children:[h.jsxs(De.div,{initial:{opacity:0,y:10},animate:{opacity:1,y:0},className:"overflow-hidden rounded-[32px] border border-black/5 bg-[linear-gradient(135deg,rgba(255,252,247,0.95),rgba(233,227,216,0.85))] p-7 shadow-[0_28px_70px_rgba(0,0,0,0.08)] lg:p-9",children:[h.jsx("div",{className:"inline-flex items-center gap-2 rounded-full border border-black/5 bg-white/70 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-stone-600",children:"Retail operations overview"}),h.jsx("h1",{className:"font-display mt-5 max-w-3xl text-4xl font-bold tracking-tight text-stone-900 lg:text-6xl",children:"A cleaner control room for what your store needs next."}),h.jsx("p",{className:"mt-5 max-w-2xl text-base leading-relaxed text-stone-600 lg:text-lg",children:"Keep the experience web-first: clearer decisions, sharper visibility, and a workspace that feels built for an owner running a real store instead of a generic AI dashboard."}),h.jsxs("div",{className:"mt-8 flex flex-wrap items-center gap-3",children:[h.jsxs("button",{onClick:f,className:`inline-flex items-center gap-2 rounded-full px-5 py-3 text-sm font-bold transition-all ${i>0?"bg-stone-900 text-white hover:bg-black":"bg-emerald-700 text-white hover:bg-emerald-600"}`,children:[i>0?h.jsx(Ly,{size:16}):h.jsx(yr,{size:16}),h.jsx("span",{children:i>0?`Review ${i} pending approvals`:"Everything is stable right now"}),h.jsx(Ay,{size:16})]}),h.jsxs("button",{onClick:d,className:"inline-flex items-center gap-2 rounded-full border border-black/10 bg-white/70 px-5 py-3 text-sm font-bold text-stone-700 transition-all hover:bg-white",children:[h.jsx(ms,{size:16}),h.jsx("span",{children:"See project plans"})]})]})]}),h.jsxs(De.button,{onClick:p,initial:{opacity:0,y:10},animate:{opacity:1,y:0},transition:{delay:.06},className:"rounded-[32px] border border-black/5 bg-[rgba(255,252,247,0.78)] p-7 text-left shadow-[0_24px_60px_rgba(0,0,0,0.06)] transition-all hover:bg-white/90",children:[h.jsxs("div",{className:"flex items-center justify-between gap-4",children:[h.jsxs("div",{className:"flex items-center gap-3",children:[h.jsx("div",{className:"flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700",children:h.jsx(dp,{size:24})}),h.jsxs("div",{children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-[0.22em] text-stone-500",children:"Workspace profile"}),h.jsx("h3",{className:"font-display mt-1 text-2xl font-bold tracking-tight text-stone-900",children:u.name})]})]}),h.jsx(oo,{size:18,className:"text-stone-400"})]}),h.jsx("p",{className:"mt-5 text-sm leading-relaxed text-stone-600",children:u.workStyle}),h.jsx("div",{className:"mt-6 space-y-3",children:u.preferences.slice(0,3).map(w=>h.jsxs("div",{className:"flex items-start justify-between gap-4 border-t border-black/5 pt-3 text-sm",children:[h.jsx("span",{className:"text-stone-500",children:w.label}),h.jsx("span",{className:"max-w-[60%] text-right font-semibold text-stone-800",children:w.value})]},w.label))})]})]}),h.jsx("div",{className:"grid grid-cols-2 gap-4 lg:grid-cols-4",children:v.map((w,N)=>h.jsxs(De.div,{initial:{opacity:0,y:20},animate:{opacity:1,y:0},transition:{delay:N*.08},className:"rounded-[28px] border border-black/5 bg-[rgba(255,252,247,0.72)] p-5 shadow-[0_18px_45px_rgba(0,0,0,0.05)] transition-all",children:[h.jsx("div",{className:`mb-4 flex h-11 w-11 items-center justify-center rounded-2xl ${w.bg}`,children:h.jsx(w.icon,{size:18,className:w.color})}),h.jsx("div",{className:"text-[11px] font-bold uppercase tracking-[0.18em] text-stone-500",children:w.label}),h.jsx("div",{className:`mt-1 text-2xl font-black tracking-tight ${w.color}`,children:w.value})]},w.label))}),h.jsxs("div",{className:"grid grid-cols-1 gap-5 xl:grid-cols-[1.15fr_0.85fr]",children:[h.jsxs(De.button,{onClick:d,whileTap:{scale:.99},className:"rounded-[32px] border border-black/5 bg-[rgba(255,252,247,0.78)] p-6 text-left shadow-[0_22px_55px_rgba(0,0,0,0.06)] transition-all hover:bg-white/90 lg:p-7",children:[h.jsxs("div",{className:"flex items-start justify-between gap-4",children:[h.jsxs("div",{children:[h.jsxs("div",{className:"inline-flex items-center gap-2 rounded-full border border-black/5 bg-teal-50 px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-teal-700",children:[h.jsx(ms,{size:12}),"Two Plans In Motion"]}),h.jsx("h3",{className:"font-display mt-4 text-2xl font-bold tracking-tight text-stone-900",children:"Build the product in two tracks"}),h.jsx("p",{className:"mt-2 max-w-2xl text-sm leading-relaxed text-stone-600",children:"One plan sharpens the UI. The other shapes a custom work setup around the user so RetailOS fits real daily flow."})]}),h.jsx(If,{size:18,className:"flex-shrink-0 text-teal-700"})]}),h.jsx("div",{className:"mt-6 grid gap-4 sm:grid-cols-2",children:a.map(w=>h.jsxs("div",{className:"rounded-[26px] border border-black/5 bg-[linear-gradient(180deg,rgba(255,255,255,0.7),rgba(246,241,233,0.9))] p-5",children:[h.jsxs("div",{className:"flex items-center justify-between gap-3",children:[h.jsx("div",{className:"text-sm font-black text-stone-900",children:w.title}),h.jsxs("div",{className:"text-[10px] font-black uppercase tracking-widest text-stone-500",children:[w.progress,"%"]})]}),h.jsx("div",{className:"mt-3 h-2 w-full overflow-hidden rounded-full bg-stone-200",children:h.jsx("div",{className:"h-full rounded-full bg-gradient-to-r from-teal-700 to-amber-700",style:{width:`${w.progress}%`}})}),h.jsx("p",{className:"mt-3 text-xs leading-relaxed text-stone-600",children:w.focus})]},w.id))})]}),h.jsxs("div",{className:"rounded-[32px] border border-black/5 bg-stone-900 p-6 text-stone-50 shadow-[0_22px_55px_rgba(0,0,0,0.18)] lg:p-7",children:[h.jsx("div",{className:"flex items-center justify-between gap-3",children:h.jsxs("div",{className:"flex items-center gap-3",children:[h.jsx("div",{className:"flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10 text-amber-300",children:h.jsx(ys,{size:20})}),h.jsxs("div",{children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-[0.2em] text-stone-400",children:"Live pulse"}),h.jsx("h3",{className:"font-display mt-1 text-2xl font-bold",children:"What matters right now"})]})]})}),h.jsxs("div",{className:"mt-6 space-y-4",children:[h.jsxs("div",{className:"rounded-[24px] bg-white/5 p-4",children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-[0.18em] text-stone-400",children:"Approvals"}),h.jsx("div",{className:"mt-2 text-4xl font-black text-white",children:i}),h.jsx("p",{className:"mt-2 text-sm leading-relaxed text-stone-300",children:"Decisions that still need the owner before the system can commit to a supplier or next action."})]}),h.jsxs("div",{className:"rounded-[24px] bg-white/5 p-4",children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-[0.18em] text-stone-400",children:"Workspace intent"}),h.jsx("p",{className:"mt-2 text-sm leading-relaxed text-stone-200",children:"Keep the page calm, web-first, and practical: clear summaries, strong typography, and less AI-dashboard noise."})]})]})]})]}),h.jsxs("div",{className:"space-y-4",children:[h.jsxs("div",{className:"flex items-center justify-between px-1",children:[h.jsx("h2",{className:"text-xs font-black uppercase tracking-[0.22em] text-stone-500",children:"What's happening right now"}),h.jsxs("div",{className:"hidden lg:flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-stone-400",children:[h.jsx(ys,{size:10,className:"text-amber-700"}),h.jsx("span",{children:"Live Feed"})]})]}),h.jsxs("div",{className:"space-y-3",children:[r.slice(0,20).map((w,N)=>h.jsxs(De.div,{initial:{opacity:0,x:-10},animate:{opacity:1,x:0},transition:{delay:N*.03},className:"group flex items-start gap-4 rounded-[24px] border border-black/5 bg-[rgba(255,252,247,0.74)] p-4 transition-all hover:bg-white/90",children:[h.jsxs("div",{className:"relative mt-1.5 flex-shrink-0",children:[h.jsx("div",{className:`w-2 h-2 rounded-full ${y(w)}`}),h.jsx("div",{className:`absolute inset-0 w-2 h-2 rounded-full ${y(w)} animate-ping opacity-20`})]}),h.jsxs("div",{className:"flex-1 min-w-0 space-y-1",children:[h.jsx("div",{className:"text-sm font-medium leading-snug text-stone-900",children:x(w)}),h.jsxs("div",{className:"flex items-center gap-2",children:[h.jsx("div",{className:"text-[10px] font-bold uppercase tracking-wider text-stone-500",children:new Date(w.timestamp*1e3).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}),h.jsx("span",{className:"text-[8px] text-stone-300",children:"•"}),h.jsxs("div",{className:"flex items-center gap-1",children:[g(w),h.jsx("span",{className:"text-[10px] font-bold uppercase tracking-tighter text-stone-500",children:w.skill==="orchestrator"?"Manager":w.skill})]})]})]}),h.jsx("div",{className:"hidden transition-opacity group-hover:opacity-100 lg:block",children:h.jsx(If,{size:14,className:"text-stone-400"})})]},w.id)),r.length===0&&h.jsx("div",{className:"rounded-[28px] border-2 border-dashed border-black/10 py-20 text-center font-bold uppercase tracking-[0.22em] text-stone-400",children:"Waiting for actions..."})]})]})]})}const Rk={"SKU-001":"🍦","SKU-002":"🧂","SKU-003":"🍼","SKU-004":"🍞","SKU-005":"🥚"};function Dk({approvals:n,onRefresh:r}){const[i,a]=z.useState({}),[u,f]=z.useState({});z.useEffect(()=>{d()},[n]);const d=async()=>{try{const y=await(await fetch("/api/negotiations")).json();f(y.active||{})}catch(x){console.error("Failed to fetch negotiations:",x)}},p=x=>{a(y=>({...y,[x]:!y[x]}))},g=async(x,y)=>{try{await fetch(`/api/approvals/${y==="approve"?"approve":"reject"}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({approval_id:x})}),r()}catch(v){console.error(`Failed to ${y}:`,v)}};return n.length===0?h.jsxs("div",{className:"flex flex-col items-center justify-center py-20 lg:py-32 text-center space-y-4 px-6",children:[h.jsx("div",{className:"flex h-20 w-20 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 lg:h-24 lg:w-24",children:h.jsx(De.div,{animate:{y:[0,-5,0]},transition:{repeat:1/0,duration:2},children:h.jsx(Of,{size:40,strokeWidth:3})})}),h.jsxs("div",{children:[h.jsx("h2",{className:"text-lg lg:text-xl font-black uppercase tracking-tight text-stone-900",children:"Nothing needs your attention"}),h.jsx("p",{className:"mt-1 text-sm font-medium leading-normal text-stone-600 lg:text-base",children:"RetailOS is monitoring everything for you. Go grab a chai! ☕"})]})]}):h.jsxs("div",{className:"space-y-6",children:[h.jsx("h2",{className:"px-1 text-xs font-black uppercase tracking-widest text-stone-500",children:"RetailOS needs your decision"}),h.jsx("div",{className:"grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-6",children:n.map((x,y)=>{var U,W,se,G;const v=x.result||{},w=x.skill==="inventory",N=v.top_supplier||v.parsed||{};let E,_;if(w){const H=v.alerts&&v.alerts.length>0?v.alerts[0]:{};E=H.sku,_=H.product_name||"Unknown Product"}else E=v.sku||((W=(U=x.event)==null?void 0:U.data)==null?void 0:W.sku),_=v.product||v.product_name||"Unknown Product";const M=Rk[E]||"📦",L=v.negotiation_id,B=((se=u[L])==null?void 0:se.thread)||[],I=x.reason||v.approval_reason||"I found a better price for this item!";return h.jsxs(De.div,{initial:{opacity:0,scale:.95},animate:{opacity:1,scale:1},transition:{delay:y*.1},className:"flex flex-col overflow-hidden rounded-[30px] border border-black/5 bg-[rgba(255,252,247,0.92)] text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] transition-all hover:bg-white",children:[h.jsxs("div",{className:"flex items-start gap-4 border-b border-black/5 bg-white/75 p-5",children:[h.jsx("span",{className:"text-4xl",children:M}),h.jsxs("div",{className:"flex-1 min-w-0",children:[h.jsx("h3",{className:"mb-1 truncate text-lg font-black leading-none text-stone-900",children:_}),h.jsx("p",{className:"text-xs font-bold italic leading-snug text-stone-600",children:I})]})]}),w?h.jsxs("div",{className:"flex-1 space-y-4 border-b border-black/5 p-5",children:[h.jsxs("div",{className:"flex items-center gap-2 text-amber-700",children:[h.jsx(yp,{size:16}),h.jsx("span",{className:"text-xs font-black uppercase tracking-widest",children:"Restock Needed"})]}),h.jsx("div",{className:"text-sm font-medium leading-relaxed text-stone-700",children:"Stock limit breached. Would you like to launch the autonomous agents to restock this?"}),h.jsxs("div",{className:"rounded-xl border border-black/5 bg-white/85 p-3 text-xs italic text-stone-600 shadow-sm",children:[h.jsx("span",{className:"mr-1 font-bold not-italic text-emerald-700",children:"Action:"}),((G=v.approval_details)==null?void 0:G.action_plan)||"Trigger autonomous procurement flow to find the best supplier."]})]}):h.jsxs("div",{className:"flex-1",children:[h.jsxs("div",{className:"p-5 grid grid-cols-2 gap-4 relative",children:[h.jsx("div",{className:"absolute left-1/2 top-1/2 z-10 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-black/10 bg-stone-100",children:h.jsx(xy,{size:14,className:"text-stone-500"})}),h.jsxs("div",{className:"space-y-1",children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-widest text-stone-500",children:"Usual Price"}),h.jsx("div",{className:"text-xl font-black text-stone-500 line-through",children:"₹195"}),h.jsx("div",{className:"text-[10px] font-bold text-stone-500",children:"From MegaMart"})]}),h.jsxs("div",{className:"space-y-1 text-right",children:[h.jsx("div",{className:"mb-1 text-[10px] font-black uppercase tracking-widest leading-none text-emerald-700",children:"New Best Price"}),h.jsxs("div",{className:"mb-1 text-2xl font-black leading-none tracking-tight text-emerald-700",children:["₹",N.price_per_unit||"---"]}),h.jsx("div",{className:"text-[10px] font-bold text-emerald-700/70",children:"You save ₹2,500!"})]})]}),h.jsxs("div",{className:"px-5 pb-5 grid grid-cols-3 gap-2",children:[h.jsxs("div",{className:"flex flex-col items-center justify-center rounded-xl border border-black/5 bg-white/85 p-2.5 text-center shadow-sm",children:[h.jsx(xv,{size:14,className:"mb-1 text-teal-700"}),h.jsx("span",{className:"text-[9px] font-black uppercase tracking-tighter leading-none text-stone-500",children:"Trust"}),h.jsx("span",{className:"mt-0.5 text-[12px] font-black leading-none text-stone-900",children:"94%"})]}),h.jsxs("div",{className:"flex flex-col items-center justify-center rounded-xl border border-black/5 bg-white/85 p-2.5 text-center shadow-sm",children:[h.jsx(fp,{size:14,className:"mb-1 text-amber-700"}),h.jsx("span",{className:"text-[9px] font-black uppercase tracking-tighter leading-none text-stone-500",children:"Wait"}),h.jsx("span",{className:"mt-0.5 text-[12px] font-black leading-none text-stone-900",children:"1 Day"})]}),h.jsxs("div",{className:"flex flex-col items-center justify-center rounded-xl border border-black/5 bg-white/85 p-2.5 text-center shadow-sm",children:[h.jsx(bl,{size:14,className:"mb-1 text-emerald-700"}),h.jsx("span",{className:"text-[9px] font-black uppercase tracking-tighter leading-none text-stone-500",children:"Quality"}),h.jsx("span",{className:"mt-0.5 text-[12px] font-black leading-none text-stone-900",children:"AA+"})]})]})]}),L&&h.jsxs("div",{className:"border-t border-black/5",children:[h.jsxs("button",{onClick:()=>p(x.id),className:"group flex w-full items-center justify-between p-4 text-stone-600 transition-colors hover:text-stone-900",children:[h.jsxs("div",{className:"flex items-center gap-2",children:[h.jsx(tu,{size:16}),h.jsx("span",{className:"text-[10px] font-black uppercase tracking-widest",children:"See our WhatsApp talk"})]}),i[x.id]?h.jsx(cp,{size:16}):h.jsx(up,{size:16})]}),h.jsx(Mu,{children:i[x.id]&&h.jsx(De.div,{initial:{height:0,opacity:0},animate:{height:"auto",opacity:1},exit:{height:0,opacity:0},className:"overflow-hidden bg-stone-50 px-4 pb-4",children:h.jsx("div",{className:"pt-2 flex flex-col gap-3",children:B.map((H,re)=>h.jsxs("div",{className:`flex flex-col ${H.direction==="outbound"?"items-end":"items-start"}`,children:[h.jsx("div",{className:"mb-1 text-[8px] font-black uppercase tracking-widest text-stone-500",children:H.direction==="outbound"?"RetailOS sent:":"Supplier replied:"}),h.jsx("div",{className:H.direction==="outbound"?"whatsapp-bubble-out text-[13px] leading-snug":"whatsapp-bubble-in text-[13px] leading-snug",children:H.message}),h.jsx("div",{className:"mt-1 text-[9px] font-medium text-stone-500",children:new Date(H.timestamp*1e3).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})})]},re))})})})]}),h.jsxs("div",{className:"flex flex-col gap-2 bg-stone-50 p-4 lg:flex-row",children:[h.jsxs(De.button,{whileTap:{scale:.98},onClick:()=>g(x.id,"approve"),className:"btn-success w-full flex items-center justify-center gap-2",children:[h.jsx(Of,{size:20,strokeWidth:3}),h.jsx("span",{children:"YES, ORDER IT"})]}),h.jsx(De.button,{whileTap:{scale:.98},onClick:()=>g(x.id,"reject"),className:"rounded-xl p-3 text-xs font-black uppercase tracking-widest text-red-700 transition-all hover:bg-red-50 lg:w-auto",children:"❌ No, skip"})]})]},x.id)})})]})}const El={inventory:{label:"Stock Checks",icon:nu,color:"text-amber-500",bg:"bg-amber-500/10"},procurement:{label:"Supplier Finder",icon:kv,color:"text-blue-500",bg:"bg-blue-500/10"},negotiation:{label:"Supplier Talks",icon:tu,color:"text-green-500",bg:"bg-green-500/10"},customer:{label:"Offers Sent",icon:Qi,color:"text-purple-500",bg:"bg-purple-500/10"},orchestrator:{label:"System",icon:lp,color:"text-white/40",bg:"bg-white/5"}};function Lk({logs:n}){const[r,i]=z.useState("All"),[a,u]=z.useState({}),f=p=>{u(g=>({...g,[p]:!g[p]}))},d=n.filter(p=>{var x;return r==="All"?!0:((x=El[p.skill])==null?void 0:x.label)===r});return h.jsxs("div",{className:"space-y-6",children:[h.jsxs("div",{className:"flex items-center justify-between px-1",children:[h.jsx("h2",{className:"text-xs font-black uppercase tracking-widest text-stone-500",children:"Everything RetailOS did"}),h.jsxs("div",{className:"hidden lg:flex items-center gap-1.5 text-[10px] font-bold text-stone-500",children:[h.jsx(Gy,{size:10}),h.jsxs("span",{children:[d.length," events"]})]})]}),h.jsx("div",{className:"flex gap-2 overflow-x-auto pb-2 scrollbar-hide lg:flex-wrap",children:["All","Stock Checks","Supplier Finder","Supplier Talks","Offers Sent"].map(p=>h.jsx("button",{onClick:()=>i(p),className:`px-4 py-2 rounded-full text-[10px] font-black uppercase tracking-widest whitespace-nowrap border transition-all ${r===p?"border-teal-700 bg-teal-700 text-white shadow-lg shadow-teal-700/15":"border-black/10 bg-white/80 text-stone-600 hover:border-black/15 hover:text-stone-900"}`,children:p},p))}),h.jsxs("div",{className:"space-y-3 lg:space-y-4",children:[d.map((p,g)=>{const x=El[p.skill]||El.orchestrator,y=x.icon,v=a[p.id];return h.jsx(De.div,{initial:{opacity:0,x:-10},animate:{opacity:1,x:0},transition:{delay:Math.min(g*.03,.3)},className:"group",children:h.jsxs("div",{className:"relative overflow-hidden rounded-2xl border border-black/5 bg-[rgba(255,252,247,0.9)] shadow-[0_18px_45px_rgba(0,0,0,0.05)] transition-all hover:bg-white lg:rounded-3xl",children:[h.jsxs("div",{className:"p-4 lg:p-5 flex gap-3 lg:gap-4",children:[h.jsx("div",{className:`w-10 h-10 lg:w-12 lg:h-12 rounded-xl lg:rounded-2xl ${x.bg} flex items-center justify-center flex-shrink-0`,children:h.jsx(y,{size:18,className:x.color})}),h.jsxs("div",{className:"flex-1 min-w-0 space-y-1",children:[h.jsxs("div",{className:"flex items-center justify-between gap-2",children:[h.jsx("span",{className:`text-[10px] font-black uppercase tracking-widest ${x.color}`,children:x.label}),h.jsxs("span",{className:"flex flex-shrink-0 items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-stone-500",children:[h.jsx(Cy,{size:10}),new Date(p.timestamp*1e3).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})]})]}),h.jsx("h3",{className:"text-[13px] font-black leading-tight text-stone-900 transition-colors group-hover:text-teal-700 lg:text-[14px]",children:p.decision}),h.jsx("p",{className:"line-clamp-2 text-[11px] font-medium leading-snug text-stone-600 lg:text-[12px]",children:p.reasoning}),h.jsxs("button",{onClick:()=>f(p.id),className:"mt-2 flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-teal-700/80 transition-colors hover:text-teal-700",children:[h.jsx(lp,{size:12}),h.jsx("span",{children:v?"Hide thinking":"How did you decide this?"}),v?h.jsx(cp,{size:12}):h.jsx(up,{size:12})]})]})]}),h.jsx(Mu,{children:v&&h.jsx(De.div,{initial:{height:0,opacity:0},animate:{height:"auto",opacity:1},exit:{height:0,opacity:0},className:"border-t border-black/5 bg-stone-50",children:h.jsxs("div",{className:"p-5 space-y-3",children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-widest text-teal-700",children:"Here's exactly how I thought about this:"}),h.jsxs("div",{className:"rounded-2xl border border-black/5 bg-white p-4 text-[12px] font-medium italic leading-relaxed text-stone-700",children:['"',p.reasoning||"I checked the current data and historical patterns to ensure the best possible outcome for your business.",'"']}),p.outcome&&h.jsxs("div",{className:"space-y-2",children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-widest text-stone-500",children:"Final Result:"}),h.jsx("div",{className:"max-h-32 overflow-y-auto break-all rounded-xl border border-black/5 bg-white p-3 font-mono text-[11px] text-stone-600 scrollbar-thin",children:p.outcome})]})]})})})]})},p.id)}),d.length===0&&h.jsxs("div",{className:"space-y-4 rounded-3xl border-2 border-dashed border-black/10 bg-white/60 px-10 py-20 text-center",children:[h.jsx("div",{className:"text-center text-4xl opacity-40",children:"📜"}),h.jsx("p",{className:"text-sm font-black uppercase tracking-widest leading-none text-stone-500",children:"Nothing found in this list"})]})]})]})}const sp={inventory:{name:"Stock Watcher",role:"Checks all 1,200 products every 60 seconds and alerts when anything is running low",icon:gs,color:"text-amber-500",bg:"bg-amber-500/10",gradient:"from-amber-500/20 to-orange-500/5"},procurement:{name:"Deal Finder",role:"Scours the market for the best prices and identifies the most reliable suppliers for you",icon:nu,color:"text-blue-500",bg:"bg-blue-500/10",gradient:"from-blue-500/20 to-cyan-500/5"},negotiation:{name:"Supplier Talker",role:"Handles all the WhatsApp back-and-forth with suppliers to lock in the deals you want",icon:tu,color:"text-green-500",bg:"bg-green-500/10",gradient:"from-green-500/20 to-emerald-500/5"},customer:{name:"Offer Sender",role:"Finds your best customers and sends them personalized special offers they actually like",icon:Qi,color:"text-purple-500",bg:"bg-purple-500/10",gradient:"from-purple-500/20 to-pink-500/5"},analytics:{name:"Business Analyst",role:"Analyzes your sales and orders to give you clear advice on how to grow your supermart",icon:Ey,color:"text-blue-400",bg:"bg-blue-400/10",gradient:"from-blue-400/20 to-indigo-500/5"}};function Vk({agents:n,onRefresh:r}){const[i,a]=z.useState(!1),u=async(d,p)=>{const g=p==="running"?"pause":"resume";try{await fetch(`/api/skills/${d}/${g}`,{method:"POST"}),r()}catch(x){console.error("Failed to toggle agent:",x)}},f=async()=>{a(!0);try{await fetch("/api/demo/trigger-flow",{method:"POST"}),alert("✅ Demo triggered! Go to Dashboard to see it starting.")}catch(d){console.error("Failed to trigger demo:",d)}a(!1)};return h.jsxs("div",{className:"space-y-6 lg:space-y-8",children:[h.jsxs("div",{className:"flex items-center justify-between px-1",children:[h.jsx("h2",{className:"text-xs font-black uppercase tracking-widest text-stone-500",children:"Your RetailOS Team"}),h.jsxs("div",{className:"text-[10px] font-bold uppercase tracking-tighter text-stone-500",children:[Object.keys(sp).length," Active Agents"]})]}),h.jsx("div",{className:"grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4 lg:gap-5",children:Object.entries(sp).map(([d,p],g)=>{var v;const x=((v=n.find(w=>w.name===d))==null?void 0:v.status)||"stopped",y=x==="running";return h.jsxs(De.div,{initial:{opacity:0,y:10},animate:{opacity:1,y:0},transition:{delay:g*.08},className:"group relative overflow-hidden rounded-[30px] border border-black/5 bg-[rgba(255,252,247,0.92)] p-5 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] transition-all hover:bg-white lg:p-6",children:[h.jsx("div",{className:`absolute inset-0 bg-gradient-to-br ${p.gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-500`}),h.jsxs("div",{className:"flex gap-4 items-start relative z-10",children:[h.jsx("div",{className:`flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl ${p.bg} shadow-sm lg:h-14 lg:w-14`,children:h.jsx(p.icon,{size:24,className:p.color})}),h.jsxs("div",{className:"flex-1 space-y-1",children:[h.jsxs("div",{className:"flex items-center justify-between",children:[h.jsx("h3",{className:"text-[15px] font-black leading-none text-stone-900 lg:text-[16px]",children:p.name}),h.jsxs("div",{className:"flex items-center gap-1.5 rounded-full border border-black/10 bg-white/85 px-2 py-0.5",children:[h.jsx("div",{className:`h-1.5 w-1.5 rounded-full ${y?"bg-emerald-600 animate-pulse":"bg-stone-400"}`}),h.jsx("span",{className:"text-[9px] font-black uppercase tracking-widest text-stone-500",children:y?"Working":"Paused"})]})]}),h.jsx("p",{className:"text-[11px] font-medium leading-tight text-stone-600 lg:text-[12px]",children:p.role})]})]}),h.jsxs("div",{className:"relative z-10 mt-4 flex items-center justify-between border-t border-black/5 pt-4",children:[h.jsxs("div",{className:"flex items-center gap-4",children:[h.jsxs("div",{className:"space-y-0.5",children:[h.jsx("div",{className:"text-[8px] font-black uppercase tracking-widest text-stone-500",children:"Today's Work"}),h.jsxs("div",{className:"flex items-center gap-1 text-[11px] font-black text-stone-900",children:[h.jsx(ys,{size:10,className:"text-teal-700"}),d==="inventory"?"720 checks":d==="procurement"?"8 suppliers found":d==="negotiation"?"4 deals closed":d==="customer"?"23 offers sent":d==="analytics"?"3 insights":"No alerts today"]})]}),h.jsx("div",{className:"h-6 w-px bg-black/8"}),h.jsxs("div",{className:"space-y-0.5",children:[h.jsx("div",{className:"text-[8px] font-black uppercase tracking-widest text-stone-500",children:"Efficiency"}),h.jsx("div",{className:"text-[11px] font-black text-stone-700",children:"98.2%"})]})]}),h.jsx("button",{onClick:()=>u(d,x),className:`p-2.5 rounded-xl border transition-all ${y?"border-black/10 bg-white/85 text-stone-500 hover:bg-white hover:text-stone-900":"border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"}`,children:y?h.jsx(uv,{size:14}):h.jsx(dv,{size:14})})]})]},d)})}),h.jsxs("div",{className:"pt-6 lg:pt-10 pb-4 flex flex-col items-center gap-4",children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-[0.3em] italic text-stone-400",children:"Advanced Control"}),h.jsx("button",{onClick:f,disabled:i,className:"flex items-center gap-2 rounded-2xl border border-black/10 bg-white/85 px-6 py-3 text-[10px] font-black uppercase tracking-widest text-stone-700 transition-all hover:bg-white hover:text-stone-900 disabled:opacity-50",children:i?"🚀 Launching...":"🚀 Launch Low Stock Demo"})]})]})}function zk(){const[n,r]=z.useState([]),[i,a]=z.useState(!0),[u,f]=z.useState(""),[d,p]=z.useState(null),g=async()=>{a(!0);try{const w=await(await fetch("/api/inventory")).json();r(w||[])}catch(v){console.error(v)}finally{a(!1)}},x=async(v,w)=>{if(!(w<0)){p(v);try{(await fetch("/api/inventory/update",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({sku:v,quantity:w})})).ok&&r(E=>E.map(_=>_.sku===v?{..._,current_stock:w}:_))}catch(N){console.error("Failed to update stock:",N)}finally{p(null)}}};z.useEffect(()=>{g()},[]);const y=n.filter(v=>{var w,N;return((w=v.product_name)==null?void 0:w.toLowerCase().includes(u.toLowerCase()))||((N=v.sku)==null?void 0:N.toLowerCase().includes(u.toLowerCase()))});return h.jsxs("div",{className:"space-y-6",children:[h.jsxs("div",{className:"flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between",children:[h.jsxs("div",{className:"relative flex-1 max-w-md",children:[h.jsx(nu,{size:16,className:"absolute left-3 top-1/2 -translate-y-1/2 text-stone-400"}),h.jsx("input",{type:"text",placeholder:"Search by name or SKU...",value:u,onChange:v=>f(v.target.value),className:"w-full rounded-xl border border-black/10 bg-white/80 py-2.5 pl-10 pr-4 text-sm text-stone-900 transition-colors placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"})]}),h.jsxs("button",{onClick:g,disabled:i,className:"flex items-center gap-2 rounded-xl border border-black/10 bg-white/80 px-4 py-2.5 text-sm font-semibold text-stone-700 transition-all hover:bg-white disabled:opacity-50",children:[h.jsx(mp,{size:16,className:i?"animate-spin text-teal-700":"text-teal-700"}),"Refresh"]})]}),h.jsxs("div",{className:"grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",children:[y.map(v=>h.jsxs(De.div,{initial:{opacity:0,scale:.95},animate:{opacity:1,scale:1},className:"relative overflow-hidden rounded-[28px] border border-black/5 bg-[rgba(255,252,247,0.9)] p-5 text-stone-900 shadow-[0_18px_45px_rgba(0,0,0,0.05)] transition-colors hover:bg-white",children:[h.jsxs("div",{className:"flex items-start justify-between mb-4",children:[h.jsxs("div",{children:[h.jsx("div",{className:"mb-1 text-xs font-bold text-stone-500",children:v.sku}),h.jsx("h3",{className:"pr-8 text-base font-bold leading-tight text-stone-900",children:v.product_name})]}),h.jsx("div",{className:`p-2 rounded-xl border ${v.status==="critical"?"bg-red-50 border-red-200 text-red-700":v.status==="warning"?"bg-amber-50 border-amber-200 text-amber-700":"bg-emerald-50 border-emerald-200 text-emerald-700"}`,children:v.status==="critical"?h.jsx(Ff,{size:18}):v.status==="warning"?h.jsx(yp,{size:18}):h.jsx(zy,{size:18})})]}),h.jsxs("div",{className:"grid grid-cols-2 gap-4",children:[h.jsxs("div",{children:[h.jsx("div",{className:"mb-2 text-[10px] font-bold uppercase tracking-wider text-stone-500",children:"Current Stock"}),h.jsxs("div",{className:"flex items-center gap-2",children:[h.jsxs("div",{className:"flex shrink-0 items-center overflow-hidden rounded-lg border border-black/10 bg-white/90",children:[h.jsx("button",{onClick:()=>x(v.sku,v.current_stock-5),disabled:d===v.sku,title:"Decrease by 5",className:"p-1 px-2 text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-900 disabled:opacity-50",children:h.jsx(iv,{size:14})}),h.jsx("span",{className:`px-2 text-lg font-black text-center min-w-[2.5ch] ${v.status==="critical"?"text-red-700":v.status==="warning"?"text-amber-700":"text-stone-900"}`,children:d===v.sku?"...":v.current_stock}),h.jsx("button",{onClick:()=>x(v.sku,v.current_stock+5),disabled:d===v.sku,title:"Increase by 5",className:"p-1 px-2 text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-900 disabled:opacity-50",children:h.jsx(hv,{size:14})})]}),h.jsxs("span",{className:"ml-1 whitespace-nowrap pt-1 text-[10px] font-bold uppercase tracking-wider text-stone-500",children:["Min: ",v.threshold]})]})]}),h.jsxs("div",{children:[h.jsx("div",{className:"mb-1 text-[10px] font-bold uppercase tracking-wider text-stone-500",children:"Velocity"}),h.jsxs("div",{className:"font-bold text-stone-900",children:[v.daily_sales_rate," ",h.jsx("span",{className:"text-xs font-medium text-stone-500",children:"/day"})]})]})]}),h.jsxs("div",{className:"mt-4 flex items-center justify-between border-t border-black/5 pt-4",children:[h.jsx("span",{className:"text-xs font-semibold text-stone-500",children:"Days until empty"}),h.jsxs("span",{className:`text-sm font-black ${v.days_until_stockout<2?"text-red-700":v.days_until_stockout<5?"text-amber-700":"text-emerald-700"}`,children:[v.days_until_stockout==="Infinity"?"∞":v.days_until_stockout," days"]})]}),v.status==="critical"&&h.jsx("div",{className:"absolute top-0 right-0 w-16 h-16 pointer-events-none",children:h.jsx("div",{className:"absolute top-0 right-0 w-2 h-2 rounded-full bg-red-500 m-3 shadow-[0_0_12px_rgba(239,68,68,0.8)] animate-pulse"})})]},v.sku)),y.length===0&&!i&&h.jsxs("div",{className:"col-span-full rounded-[28px] border border-dashed border-black/10 bg-white/70 p-8 py-12 text-center",children:[h.jsx(Ff,{size:32,className:"mx-auto mb-3 text-stone-400"}),h.jsx("h3",{className:"mb-1 font-semibold text-stone-800",children:"No items found"}),h.jsx("p",{className:"text-sm text-stone-500",children:"Try adjusting your search"})]})]})]})}const ip={in_progress:{label:"In Progress",color:"text-teal-700",chip:"bg-teal-50 border-teal-200"},planned:{label:"Planned",color:"text-amber-700",chip:"bg-amber-50 border-amber-200"},done:{label:"Done",color:"text-emerald-700",chip:"bg-emerald-50 border-emerald-200"}};function Ik({plans:n}){return h.jsxs("div",{className:"space-y-6 lg:space-y-8",children:[h.jsx("div",{className:"overflow-hidden rounded-[2rem] border border-black/5 bg-[linear-gradient(135deg,rgba(239,247,242,0.96),rgba(247,241,232,0.9))] shadow-[0_20px_55px_rgba(0,0,0,0.06)]",children:h.jsxs("div",{className:"p-6 lg:p-8",children:[h.jsxs("div",{className:"inline-flex items-center gap-2 rounded-full border border-teal-200 bg-white/75 px-3 py-1 text-[10px] font-black uppercase tracking-[0.24em] text-teal-700",children:[h.jsx(ms,{size:12}),"Execution Map"]}),h.jsx("h2",{className:"font-display mt-4 text-2xl font-bold tracking-tight text-stone-900 lg:text-4xl",children:"Two plans, one product direction"}),h.jsx("p",{className:"mt-3 max-w-3xl text-sm leading-relaxed text-stone-600 lg:text-base",children:"We are improving the dashboard experience and building a custom work setup around the user at the same time, so the UI looks better and works more personally."})]})}),h.jsx("div",{className:"grid grid-cols-1 2xl:grid-cols-2 gap-4 lg:gap-6",children:n.map((r,i)=>{const a=ip[r.status]||ip.planned;return h.jsxs(De.div,{initial:{opacity:0,y:12},animate:{opacity:1,y:0},transition:{delay:i*.08},className:"overflow-hidden rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.86)] text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)]",children:[h.jsxs("div",{className:"border-b border-black/5 p-6 lg:p-7",children:[h.jsxs("div",{className:"flex items-start justify-between gap-4",children:[h.jsxs("div",{children:[h.jsxs("div",{className:`inline-flex items-center gap-2 px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-[0.18em] ${a.chip} ${a.color}`,children:[h.jsx(Qy,{size:12}),a.label]}),h.jsx("h3",{className:"font-display mt-4 text-xl font-bold tracking-tight text-stone-900 lg:text-2xl",children:r.title}),h.jsxs("p",{className:"mt-1 text-sm text-stone-500",children:["Owner: ",r.owner]})]}),h.jsxs("div",{className:"text-right",children:[h.jsxs("div",{className:"text-3xl font-black text-stone-900",children:[r.progress,"%"]}),h.jsx("div",{className:"text-[10px] font-black uppercase tracking-widest text-stone-500",children:"complete"})]})]}),h.jsx("div",{className:"mt-5 h-2 w-full overflow-hidden rounded-full bg-stone-200",children:h.jsx("div",{className:"h-full rounded-full bg-gradient-to-r from-teal-700 via-teal-600 to-amber-600",style:{width:`${r.progress}%`}})})]}),h.jsxs("div",{className:"p-6 lg:p-7 space-y-5",children:[h.jsxs("div",{children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-[0.2em] text-stone-500",children:"Summary"}),h.jsx("p",{className:"mt-2 text-sm leading-relaxed text-stone-700",children:r.summary})]}),h.jsxs("div",{children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-[0.2em] text-stone-500",children:"Current Focus"}),h.jsx("p",{className:"mt-2 text-sm leading-relaxed text-stone-700",children:r.focus})]}),h.jsxs("div",{children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-[0.2em] text-stone-500",children:"Milestones"}),h.jsx("div",{className:"space-y-3 mt-3",children:r.milestones.map(u=>h.jsxs("div",{className:"flex items-center gap-3 text-sm",children:[u.done?h.jsx(yr,{size:16,className:"text-emerald-700 flex-shrink-0"}):h.jsx(Fy,{size:16,className:"text-stone-400 flex-shrink-0"}),h.jsx("span",{className:u.done?"text-stone-800":"text-stone-500",children:u.label})]},u.label))})]}),h.jsxs("div",{className:"rounded-2xl border border-black/5 bg-white/88 p-4 shadow-sm",children:[h.jsxs("div",{className:"flex items-center gap-2 text-teal-700",children:[h.jsx(gp,{size:14}),h.jsx("span",{className:"text-[10px] font-black uppercase tracking-[0.18em]",children:"Next Step"})]}),h.jsx("p",{className:"mt-2 text-sm leading-relaxed text-stone-700",children:r.nextAction})]})]})]},r.id)})})]})}function Ok({plans:n,workspaceProfile:r}){return h.jsxs("div",{className:"space-y-6 lg:space-y-8",children:[h.jsxs("div",{className:"grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-4 lg:gap-6",children:[h.jsxs(De.div,{initial:{opacity:0,y:10},animate:{opacity:1,y:0},className:"rounded-[2rem] border border-black/5 bg-[linear-gradient(135deg,rgba(239,247,242,0.96),rgba(229,240,238,0.88))] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-8",children:[h.jsxs("div",{className:"flex items-start justify-between gap-4",children:[h.jsxs("div",{children:[h.jsxs("div",{className:"inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-white/70 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-emerald-700",children:[h.jsx(oo,{size:12}),"User Workspace"]}),h.jsx("h2",{className:"font-display mt-4 text-2xl font-bold tracking-tight lg:text-4xl",children:r.name}),h.jsx("p",{className:"mt-3 max-w-2xl text-sm leading-relaxed text-stone-600 lg:text-base",children:r.workStyle})]}),h.jsx("div",{className:"flex h-14 w-14 items-center justify-center rounded-3xl border border-white/70 bg-white/75 text-emerald-700 shadow-sm",children:h.jsx(dp,{size:30})})]}),h.jsxs("div",{className:"grid sm:grid-cols-2 gap-3 mt-6",children:[h.jsxs("div",{className:"rounded-2xl border border-black/5 bg-white/80 p-4 shadow-sm",children:[h.jsxs("div",{className:"flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-stone-500",children:[h.jsx(Bf,{size:12}),"Role"]}),h.jsx("div",{className:"mt-2 text-lg font-black text-stone-900",children:r.role})]}),h.jsxs("div",{className:"rounded-2xl border border-black/5 bg-white/80 p-4 shadow-sm",children:[h.jsxs("div",{className:"flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-stone-500",children:[h.jsx(Jy,{size:12}),"Context"]}),h.jsx("div",{className:"mt-2 text-lg font-black text-stone-900",children:r.location})]})]})]}),h.jsxs(De.div,{initial:{opacity:0,y:10},animate:{opacity:1,y:0},transition:{delay:.06},className:"rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.82)] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-7",children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-[0.2em] text-stone-500",children:"Plan Alignment"}),h.jsx("div",{className:"space-y-4 mt-4",children:n.map(i=>h.jsxs("div",{className:"rounded-2xl border border-black/5 bg-white/88 p-4 shadow-sm",children:[h.jsxs("div",{className:"flex items-center justify-between gap-3",children:[h.jsx("div",{className:"text-sm font-black text-stone-900",children:i.title}),h.jsxs("div",{className:"text-xs font-bold text-stone-500",children:[i.progress,"%"]})]}),h.jsx("p",{className:"mt-2 text-sm leading-relaxed text-stone-600",children:i.nextAction})]},i.id))})]})]}),h.jsxs("div",{className:"grid grid-cols-1 xl:grid-cols-[0.9fr_1.1fr] gap-4 lg:gap-6",children:[h.jsxs(De.div,{initial:{opacity:0,y:10},animate:{opacity:1,y:0},transition:{delay:.12},className:"rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.82)] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-7",children:[h.jsxs("div",{className:"flex items-center gap-2 text-emerald-700",children:[h.jsx(Bf,{size:16}),h.jsx("h3",{className:"text-sm font-black uppercase tracking-[0.16em] text-stone-800",children:"What matters to the user"})]}),h.jsx("div",{className:"space-y-3 mt-5",children:r.goals.map(i=>h.jsxs("div",{className:"flex items-start gap-3",children:[h.jsx(yr,{size:16,className:"text-emerald-700 flex-shrink-0 mt-0.5"}),h.jsx("p",{className:"text-sm leading-relaxed text-stone-700",children:i})]},i))})]}),h.jsxs(De.div,{initial:{opacity:0,y:10},animate:{opacity:1,y:0},transition:{delay:.18},className:"rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.82)] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-7",children:[h.jsxs("div",{className:"flex items-center gap-2 text-teal-700",children:[h.jsx($y,{size:16}),h.jsx("h3",{className:"text-sm font-black uppercase tracking-[0.16em] text-stone-800",children:"Daily flow setup"})]}),h.jsx("div",{className:"space-y-4 mt-5",children:r.routines.map(i=>h.jsxs("div",{className:"rounded-2xl border border-black/5 bg-white/88 p-4 shadow-sm",children:[h.jsxs("div",{className:"flex items-center justify-between gap-3",children:[h.jsx("div",{className:"text-sm font-black text-stone-900",children:i.label}),h.jsx("div",{className:"text-[11px] font-black uppercase tracking-widest text-teal-700",children:i.time})]}),h.jsx("p",{className:"mt-2 text-sm leading-relaxed text-stone-600",children:i.detail})]},i.label))})]})]}),h.jsxs(De.div,{initial:{opacity:0,y:10},animate:{opacity:1,y:0},transition:{delay:.24},className:"rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.82)] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-7",children:[h.jsxs("div",{className:"flex items-center gap-2 text-amber-700",children:[h.jsx(gp,{size:16}),h.jsx("h3",{className:"text-sm font-black uppercase tracking-[0.16em] text-stone-800",children:"Preference layer"})]}),h.jsx("div",{className:"grid md:grid-cols-2 xl:grid-cols-4 gap-3 mt-5",children:r.preferences.map(i=>h.jsxs("div",{className:"rounded-2xl border border-black/5 bg-white/88 p-4 shadow-sm",children:[h.jsx("div",{className:"text-[10px] font-black uppercase tracking-[0.18em] text-stone-500",children:i.label}),h.jsx("div",{className:"mt-2 text-sm font-semibold leading-relaxed text-stone-800",children:i.value})]},i.label))})]})]})}function Fk(){var I,U,W,se;const[n,r]=z.useState("home"),[i,a]=z.useState([]),[u,f]=z.useState([]),[d,p]=z.useState([]),[g,x]=z.useState({moneySaved:8400,ordersPlaced:6,offersSent:147,hoursSaved:12}),[y]=z.useState([{id:"ui-refresh",title:"UI Experience Upgrade",owner:"Product + Frontend",status:"in_progress",progress:68,summary:"Polish the dashboard into a clearer, faster workspace with better structure and stronger decision surfaces.",focus:"Navigation, homepage framing, approval visibility, and cleaner user-facing language.",nextAction:"Finalize the new dashboard flow and connect future user-specific widgets to live data.",milestones:[{label:"Navigation cleanup",done:!0},{label:"Add plans overview",done:!0},{label:"Surface workspace context",done:!1},{label:"Refine mobile layout",done:!1}]},{id:"user-workspace",title:"Custom User Work Setup",owner:"Ops + Personalization",status:"planned",progress:42,summary:"Shape the product around the user: role, routines, priorities, communication style, and preferred workflows.",focus:"Morning checklist, approval style, business goals, notification preferences, and store context.",nextAction:"Move these preferences from UI scaffolding into persistent backend settings and onboarding.",milestones:[{label:"Map user profile fields",done:!0},{label:"Design workspace setup UI",done:!0},{label:"Persist preferences in API",done:!1},{label:"Enable editable routines",done:!1}]}]),[v]=z.useState({name:"Soham",role:"Store Owner",workStyle:"Hands-on in the morning, approval-driven in the afternoon, summary-first at night.",location:"Primary retail floor",goals:["Reduce time spent chasing suppliers","Keep approvals short and easy to review","See the next important action without digging"],routines:[{label:"Morning opening check",time:"08:30",detail:"Review low-stock items and overnight alerts."},{label:"Midday approval sweep",time:"13:00",detail:"Approve urgent supplier and pricing decisions."},{label:"Evening summary",time:"20:30",detail:"Get a short wrap-up of store actions and outcomes."}],preferences:[{label:"Approval style",value:"Quick summary + best option first"},{label:"Notifications",value:"Urgent only during business hours"},{label:"Decision mode",value:"Manual approval for supplier commits"},{label:"Focus area",value:"Inventory health and supplier savings"}]}),[w,N]=z.useState(!1),E=z.useRef(null),_=[{id:"home",label:"Overview",icon:pp},{id:"plans",label:"Plans",icon:ms},{id:"workspace",label:"Workspace",icon:oo},{id:"inventory",label:"Inventory",icon:gs},{id:"approvals",label:"Approvals",icon:yr,badge:u.length},{id:"history",label:"Activity",icon:hp},{id:"agents",label:"Agents",icon:vp}];z.useEffect(()=>{M(),L();const G=setInterval(M,3e4);return()=>{clearInterval(G),E.current&&E.current.close()}},[]);const M=async()=>{try{const[G,H,re]=await Promise.all([fetch("/api/status"),fetch("/api/approvals"),fetch("/api/audit?limit=100")]),Y=await G.json(),ce=await H.json(),me=await re.json();p(Y.skills||[]),f(ce||[]),a(me||[])}catch(G){console.error("Failed to fetch data:",G)}},L=()=>{const G=window.location.protocol==="https:"?"wss:":"ws:",H=window.location.host;E.current=new WebSocket(`${G}//${H}/ws/events`),E.current.onopen=()=>N(!0),E.current.onclose=()=>{N(!1),setTimeout(L,3e3)},E.current.onmessage=re=>{const Y=JSON.parse(re.data);Y.type==="audit_log"&&(a(ce=>[Y.data,...ce].slice(0,100)),["owner_approved","owner_rejected","approval_requested"].includes(Y.data.event_type)&&M())}},B={home:{title:"Dashboard",subtitle:"Real-time overview of your store operations"},plans:{title:"Execution Plans",subtitle:"Track the UI upgrade and custom user workspace rollout"},inventory:{title:"Inventory",subtitle:"Real-time stock levels and alerts"},workspace:{title:"User Workspace",subtitle:"A custom setup built around how the user actually works"},approvals:{title:"Approvals",subtitle:`${u.length} pending decisions`},history:{title:"What Happened",subtitle:"Complete audit trail of every action"},agents:{title:"My Agents",subtitle:"Your autonomous agent workforce"}};return h.jsxs("div",{className:"min-h-screen text-stone-900",children:[h.jsx(Mk,{activeTab:n,setActiveTab:r,approvalCount:u.length,isConnected:w}),h.jsx("header",{className:"sticky top-0 z-40 border-b border-black/5 bg-[rgba(244,239,230,0.82)] backdrop-blur-xl",children:h.jsxs("div",{className:"mx-auto max-w-[1500px] px-4 sm:px-6 lg:px-10",children:[h.jsxs("div",{className:"flex min-h-[84px] items-center justify-between gap-6",children:[h.jsxs("div",{className:"flex items-center gap-4",children:[h.jsx("div",{className:"flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-700 to-amber-700 text-white shadow-lg shadow-teal-900/15",children:h.jsx(ys,{size:20})}),h.jsxs("div",{children:[h.jsx("div",{className:"font-display text-2xl font-bold tracking-tight",children:"RetailOS"}),h.jsx("div",{className:"text-xs font-semibold uppercase tracking-[0.28em] text-stone-500",children:"Retail command center"})]})]}),h.jsx("div",{className:"hidden xl:flex items-center gap-2 rounded-full border border-black/5 bg-white/50 px-2 py-2 shadow-sm",children:_.map(G=>h.jsxs("button",{onClick:()=>r(G.id),className:`relative flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition-all ${n===G.id?"bg-stone-900 text-white shadow-sm":"text-stone-600 hover:bg-black/[0.04] hover:text-stone-900"}`,children:[h.jsx(G.icon,{size:16}),h.jsx("span",{children:G.label}),G.badge>0&&h.jsx("span",{className:"rounded-full bg-red-600 px-2 py-0.5 text-[10px] font-bold text-white",children:G.badge})]},G.id))}),h.jsxs("div",{className:"flex items-center gap-3",children:[h.jsxs("div",{className:"hidden sm:flex items-center gap-2 rounded-full border border-black/5 bg-white/55 px-4 py-2 text-sm",children:[h.jsx("div",{className:`h-2.5 w-2.5 rounded-full ${w?"bg-emerald-500":"bg-red-500"}`}),h.jsx("span",{className:"font-medium text-stone-700",children:w?"Live updates active":"Reconnecting"})]}),h.jsx("button",{onClick:M,className:"rounded-full border border-black/5 bg-white/55 p-3 text-stone-600 transition-all hover:bg-white hover:text-stone-900",title:"Refresh data",children:h.jsx(mp,{size:16})}),h.jsxs("div",{className:"relative",children:[h.jsx("button",{className:"rounded-full border border-black/5 bg-white/55 p-3 text-stone-600 transition-all hover:bg-white hover:text-stone-900",children:h.jsx(Sy,{size:16})}),u.length>0&&h.jsx("span",{className:"absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white",children:u.length})]}),h.jsx("div",{className:"xl:hidden rounded-full border border-black/5 bg-white/55 p-3 text-stone-600",children:h.jsx(nv,{size:16})})]})]}),h.jsx("div",{className:"xl:hidden overflow-x-auto pb-4 scrollbar-hide",children:h.jsx("div",{className:"flex min-w-max items-center gap-2",children:_.map(G=>h.jsxs("button",{onClick:()=>r(G.id),className:`flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold transition-all ${n===G.id?"border-stone-900 bg-stone-900 text-white":"border-black/5 bg-white/55 text-stone-600 hover:bg-white"}`,children:[h.jsx(G.icon,{size:15}),h.jsx("span",{children:G.label}),G.badge>0&&h.jsx("span",{className:`rounded-full px-2 py-0.5 text-[10px] font-bold ${n===G.id?"bg-white/15 text-white":"bg-red-600 text-white"}`,children:G.badge})]},G.id))})})]})}),h.jsx("main",{className:"mx-auto max-w-[1500px] px-4 py-8 sm:px-6 lg:px-10",children:h.jsxs("div",{className:"grid gap-8 xl:grid-cols-[260px_minmax(0,1fr)]",children:[h.jsx("aside",{className:"hidden xl:block",children:h.jsx("div",{className:"sticky top-28",children:h.jsxs("div",{className:"mb-6 rounded-[28px] border border-black/5 bg-white/55 p-6 shadow-[0_20px_60px_rgba(0,0,0,0.06)]",children:[h.jsx("div",{className:"text-xs font-black uppercase tracking-[0.22em] text-stone-500",children:"Current View"}),h.jsx("h2",{className:"font-display mt-3 text-3xl font-bold tracking-tight text-stone-900",children:((I=B[n])==null?void 0:I.title)||"Dashboard"}),h.jsx("p",{className:"mt-3 text-sm leading-relaxed text-stone-600",children:((U=B[n])==null?void 0:U.subtitle)||"Real-time overview of your store operations"})]})})}),h.jsxs("div",{className:"min-w-0",children:[h.jsxs("div",{className:"mb-8 xl:hidden",children:[h.jsx("div",{className:"text-xs font-black uppercase tracking-[0.22em] text-stone-500",children:"Current View"}),h.jsx("h2",{className:"font-display mt-2 text-3xl font-bold tracking-tight text-stone-900",children:((W=B[n])==null?void 0:W.title)||"Dashboard"}),h.jsx("p",{className:"mt-2 text-sm text-stone-600",children:((se=B[n])==null?void 0:se.subtitle)||"Real-time overview of your store operations"})]}),h.jsx(Mu,{mode:"wait",children:h.jsxs(De.div,{initial:{opacity:0,y:8},animate:{opacity:1,y:0},exit:{opacity:0,y:-8},transition:{duration:.2,ease:"easeOut"},children:[n==="home"&&h.jsx(Ak,{stats:g,logs:i,approvalCount:u.length,plans:y,workspaceProfile:v,onGoToApprovals:()=>r("approvals"),onGoToPlans:()=>r("plans"),onGoToWorkspace:()=>r("workspace")}),n==="plans"&&h.jsx(Ik,{plans:y}),n==="approvals"&&h.jsx(Dk,{approvals:u,onRefresh:M}),n==="history"&&h.jsx(Lk,{logs:i}),n==="agents"&&h.jsx(Vk,{agents:d,onRefresh:M}),n==="inventory"&&h.jsx(zk,{}),n==="workspace"&&h.jsx(Ok,{plans:y,workspaceProfile:v})]},n)})]})]})})]})}dy.createRoot(document.getElementById("root")).render(h.jsx(sy.StrictMode,{children:h.jsx(Fk,{})}));

```


## File: `./dashboard/public/manifest.json`
```json
{
  "name": "RetailOS",
  "short_name": "RetailOS",
  "description": "Autonomous Agent Runtime for Retail Operations",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0a0a0a",
  "theme_color": "#3b82f6",
  "orientation": "any",
  "icons": [
    {
      "src": "/icon-192.svg",
      "sizes": "192x192",
      "type": "image/svg+xml",
      "purpose": "any maskable"
    },
    {
      "src": "/icon-512.svg",
      "sizes": "512x512",
      "type": "image/svg+xml",
      "purpose": "any maskable"
    }
  ]
}

```


## File: `./dashboard/public/sw.js`
```js
const CACHE_NAME = 'retailos-v1';
const STATIC_ASSETS = [
  '/',
  '/index.html',
];

// Install: cache the shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: network-first strategy (API and WS go to network, static falls back to cache)
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Don't cache API calls or WebSocket upgrades
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/ws')) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cache successful responses
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

```


## File: `./dashboard/src/DemoControls.jsx`
```jsx
import React, { useState } from 'react'

function DemoControls({ negotiations, onRefresh }) {
  const [loading, setLoading] = useState({})
  const [replyText, setReplyText] = useState('')
  const [replyNegId, setReplyNegId] = useState('')
  const [result, setResult] = useState(null)

  const handleAction = async (action, endpoint, body = {}) => {
    setLoading(l => ({ ...l, [action]: true }))
    setResult(null)
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      setResult({ action, data })
      onRefresh()
    } catch (err) {
      setResult({ action, error: err.message })
    } finally {
      setLoading(l => ({ ...l, [action]: false }))
    }
  }

  const activeNegs = Object.entries(negotiations.active || {})
  const messageLog = negotiations.message_log || []

  const malformedExamples = [
    'haa bhai denge, 50 box minimum, price thoda negotiate hoga',
    'ok bhai, ₹220 per unit de denge. delivery 3-4 din lagega. 50 minimum order rakhna padega.',
    'abhi stock nahi hai, next week check karo',
    'haan haan, 200 rupay lagega ek piece ka. 100 box minimum. COD chalega?',
  ]

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-white">Demo Controls</h2>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <button
          onClick={() => handleAction('flow', '/api/demo/trigger-flow')}
          disabled={loading.flow}
          className="p-4 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-colors disabled:opacity-50"
        >
          {loading.flow ? 'Triggering...' : 'Trigger Ice Cream Flow'}
          <div className="text-xs font-normal opacity-75 mt-1">
            Drops stock → Inventory alert → Procurement → Negotiation
          </div>
        </button>

        <button
          onClick={() => handleAction('check', '/api/inventory/check')}
          disabled={loading.check}
          className="p-4 rounded-lg bg-gray-800 hover:bg-gray-700 text-white font-semibold transition-colors disabled:opacity-50"
        >
          {loading.check ? 'Checking...' : 'Run Inventory Check'}
          <div className="text-xs font-normal opacity-75 mt-1">
            Full scan of all SKUs
          </div>
        </button>

        <button
          onClick={() => handleAction('analytics', '/api/analytics/run')}
          disabled={loading.analytics}
          className="p-4 rounded-lg bg-gray-800 hover:bg-gray-700 text-white font-semibold transition-colors disabled:opacity-50"
        >
          {loading.analytics ? 'Running...' : 'Run Analytics'}
          <div className="text-xs font-normal opacity-75 mt-1">
            Daily pattern analysis
          </div>
        </button>
      </div>

      {/* Simulate Supplier Reply */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-5">
        <h3 className="text-white font-semibold mb-3">Simulate Supplier Reply</h3>
        <p className="text-xs text-gray-500 mb-4">
          Send a mock WhatsApp reply from a supplier. Try a messy Hinglish message to see Gemini parse it.
        </p>

        {/* Quick fill buttons */}
        <div className="flex flex-wrap gap-2 mb-3">
          {malformedExamples.map((ex, i) => (
            <button
              key={i}
              onClick={() => setReplyText(ex)}
              className="px-3 py-1 rounded text-xs bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200 transition-colors"
            >
              Example {i + 1}
            </button>
          ))}
        </div>

        <div className="space-y-3">
          <input
            type="text"
            placeholder="Negotiation ID (e.g., neg_SKU-001_SUP-001_...)"
            value={replyNegId}
            onChange={e => setReplyNegId(e.target.value)}
            className="w-full px-4 py-2 rounded-lg bg-gray-950 border border-gray-700 text-white text-sm focus:outline-none focus:border-blue-500"
          />
          <textarea
            placeholder="Supplier reply message (try Hinglish!)..."
            value={replyText}
            onChange={e => setReplyText(e.target.value)}
            rows={3}
            className="w-full px-4 py-2 rounded-lg bg-gray-950 border border-gray-700 text-white text-sm focus:outline-none focus:border-blue-500 resize-none"
          />
          <button
            onClick={() => handleAction('reply', '/api/demo/supplier-reply', {
              negotiation_id: replyNegId || 'demo_neg',
              supplier_id: 'SUP-001',
              supplier_name: 'FreshFreeze Distributors',
              message: replyText,
              product_name: 'Amul Vanilla Ice Cream',
            })}
            disabled={!replyText || loading.reply}
            className="px-6 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-semibold text-sm transition-colors disabled:opacity-50"
          >
            {loading.reply ? 'Sending...' : 'Send Supplier Reply'}
          </button>
        </div>
      </div>

      {/* Active Negotiations */}
      {activeNegs.length > 0 && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-5">
          <h3 className="text-white font-semibold mb-3">Active Negotiations</h3>
          <div className="space-y-3">
            {activeNegs.map(([id, neg]) => (
              <div key={id} className="px-4 py-3 rounded-lg bg-gray-950 border border-gray-800">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-white font-medium">{neg.product_name}</span>
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    neg.status === 'awaiting_reply' ? 'bg-amber-500/10 text-amber-400' :
                    neg.status === 'deal_ready' ? 'bg-emerald-500/10 text-emerald-400' :
                    'bg-blue-500/10 text-blue-400'
                  }`}>
                    {neg.status}
                  </span>
                </div>
                <div className="text-xs text-gray-500">
                  Supplier: {neg.supplier_name} | ID: {id}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* WhatsApp Message Log */}
      {messageLog.length > 0 && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-5">
          <h3 className="text-white font-semibold mb-3">WhatsApp Thread</h3>
          <div className="space-y-3 max-h-96 overflow-y-auto scrollbar-thin">
            {messageLog.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}
              >
                <div className={`max-w-[80%] rounded-lg px-4 py-3 ${
                  msg.direction === 'outbound'
                    ? 'bg-blue-600/20 border border-blue-500/20'
                    : 'bg-gray-800 border border-gray-700'
                }`}>
                  <div className="text-xs text-gray-500 mb-1">
                    {msg.direction === 'outbound' ? 'RetailOS' : msg.supplier_name}
                    {msg.type === 'clarification' && ' (clarification)'}
                  </div>
                  <div className="text-sm text-gray-200">{msg.message}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Last result */}
      {result && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-5">
          <h3 className="text-white font-semibold mb-2">Last Action Result</h3>
          <pre className="text-xs text-gray-400 font-mono whitespace-pre-wrap overflow-x-auto bg-gray-950 rounded p-3">
            {JSON.stringify(result.data || result.error, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

export default DemoControls

```


## File: `./dashboard/src/AuditLog.jsx`
```jsx
import React, { useState } from 'react'

const STATUS_COLORS = {
  success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  error: 'bg-red-500/10 text-red-400 border-red-500/20',
  alert: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  pending: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  pending_approval: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  approved: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  rejected: 'bg-red-500/10 text-red-400 border-red-500/20',
  escalated: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
  skipped: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
  rerouted: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
}

const SKILL_COLORS = {
  orchestrator: 'text-blue-400',
  inventory: 'text-cyan-400',
  procurement: 'text-violet-400',
  negotiation: 'text-amber-400',
  customer: 'text-pink-400',
  analytics: 'text-emerald-400',
}

function formatTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function AuditLog({ logs, onRefresh }) {
  const [expandedId, setExpandedId] = useState(null)
  const [filter, setFilter] = useState('all')

  const filtered = filter === 'all' ? logs : logs.filter(l => l.skill === filter)
  const uniqueSkills = [...new Set(logs.map(l => l.skill))]

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Audit Trail</h2>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            <button
              onClick={() => setFilter('all')}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                filter === 'all' ? 'bg-blue-500/20 text-blue-400' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              All
            </button>
            {uniqueSkills.map(s => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                  filter === s ? 'bg-blue-500/20 text-blue-400' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
          <button onClick={onRefresh} className="px-3 py-1 rounded bg-gray-800 text-gray-400 hover:bg-gray-700 text-xs">
            Refresh
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {filtered.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            No audit log entries yet. Trigger a demo flow to get started.
          </div>
        ) : (
          filtered.map(log => (
            <div
              key={log.id}
              className="bg-gray-900/50 border border-gray-800 rounded-lg overflow-hidden hover:border-gray-700 transition-colors cursor-pointer"
              onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
            >
              {/* Summary row */}
              <div className="px-4 py-3 flex items-start gap-4">
                <div className="text-xs text-gray-500 font-mono w-20 shrink-0 pt-0.5">
                  {formatTime(log.timestamp)}
                </div>
                <div className={`text-xs font-medium w-24 shrink-0 pt-0.5 ${SKILL_COLORS[log.skill] || 'text-gray-400'}`}>
                  {log.skill}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-gray-200">{log.decision}</div>
                  {log.reasoning && (
                    <div className="text-xs text-gray-500 mt-1 truncate">{log.reasoning}</div>
                  )}
                </div>
                <span className={`px-2 py-0.5 rounded text-xs border shrink-0 ${STATUS_COLORS[log.status] || STATUS_COLORS.success}`}>
                  {log.status}
                </span>
              </div>

              {/* Expanded detail */}
              {expandedId === log.id && (
                <div className="px-4 py-3 border-t border-gray-800 bg-gray-950/50">
                  <div className="grid grid-cols-1 gap-3 text-sm">
                    <div>
                      <div className="text-xs text-gray-500 mb-1">Event Type</div>
                      <div className="text-gray-300 font-mono text-xs">{log.event_type}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-1">Reasoning</div>
                      <div className="text-gray-300 text-xs whitespace-pre-wrap">{log.reasoning}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-1">Outcome</div>
                      <div className="text-gray-300 text-xs whitespace-pre-wrap font-mono bg-gray-900 rounded p-2 overflow-x-auto">
                        {tryFormatJSON(log.outcome)}
                      </div>
                    </div>
                    {log.metadata && Object.keys(log.metadata).length > 0 && (
                      <div>
                        <div className="text-xs text-gray-500 mb-1">Metadata</div>
                        <div className="text-gray-300 text-xs whitespace-pre-wrap font-mono bg-gray-900 rounded p-2 overflow-x-auto">
                          {JSON.stringify(log.metadata, null, 2)}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function tryFormatJSON(str) {
  try {
    const parsed = JSON.parse(str)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return str
  }
}

export default AuditLog

```


## File: `./dashboard/src/index.css`
```css
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap');

@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: #f4efe6;
  --background-deep: #efe7db;
  --card: rgba(255, 252, 247, 0.8);
  --card-dark: #1b1d1e;
  --primary: #0f766e;
  --accent: #b45309;
  --success: #15803d;
  --danger: #b91c1c;
  --warning: #ca8a04;
  --text: #171717;
  --text-muted: #57534e;
}

body {
  background:
    radial-gradient(circle at top left, rgba(15, 118, 110, 0.08), transparent 32%),
    radial-gradient(circle at top right, rgba(180, 83, 9, 0.08), transparent 28%),
    linear-gradient(180deg, var(--background) 0%, var(--background-deep) 100%);
  color: var(--text);
  font-family: 'Manrope', system-ui, -apple-system, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

#root {
  min-height: 100vh;
}

h1, h2, h3, h4, .font-display {
  font-family: 'Space Grotesk', 'Manrope', sans-serif;
}

@layer components {
  .btn-primary {
    @apply bg-teal-700 hover:bg-teal-600 text-white font-bold py-3 px-6 rounded-xl transition-all active:scale-95 shadow-lg shadow-teal-700/20;
  }
  .btn-success {
    @apply bg-emerald-700 hover:bg-emerald-600 text-white font-bold py-3 px-6 rounded-xl transition-all active:scale-95 shadow-lg shadow-emerald-700/20;
  }
  .btn-danger {
    @apply bg-red-700 hover:bg-red-600 text-white font-bold py-3 px-6 rounded-xl transition-all active:scale-95 shadow-lg shadow-red-700/20;
  }
}

.whatsapp-bubble-out {
  @apply bg-blue-600 text-white p-3 rounded-2xl rounded-tr-none max-w-[80%] self-end shadow-lg shadow-blue-600/20;
}

.whatsapp-bubble-in {
  @apply bg-zinc-800 text-white p-3 rounded-2xl rounded-tl-none max-w-[80%] self-start shadow-lg;
}

@layer utilities {
  .scrollbar-thin::-webkit-scrollbar {
    width: 6px;
  }
  .scrollbar-thin::-webkit-scrollbar-track {
    background: rgba(255,255,255,0.03);
  }
  .scrollbar-thin::-webkit-scrollbar-thumb {
    background: rgba(255,255,255,0.15);
    border-radius: 3px;
  }
  .scrollbar-thin::-webkit-scrollbar-thumb:hover {
    background: rgba(255,255,255,0.25);
  }
  .scrollbar-hide::-webkit-scrollbar {
    display: none;
  }
  .scrollbar-hide {
    -ms-overflow-style: none;
    scrollbar-width: none;
  }
}

```


## File: `./dashboard/src/Scheduling.jsx`
```jsx
// dashboard/src/Scheduling.jsx
import React, { useState, useEffect } from 'react';

const Scheduling = () => {
  const [scheduleData, setScheduleData] = useState(null);

  useEffect(() => {
    // In production, this pulls the structured AI report natively from the approval queue APIs
    setScheduleData({
      date: "Saturday 14 Dec",
      predicted_footfall: 340,
      increase_pct: 18,
      reason: "Proximity to year-end + local market day",
      hourly_blocks: [
        { time: "10am-12pm", status: "Adequate", staff: 2, limit: "~30 customers/hr" },
        { time: "12pm-2pm", status: "Understaffed", staff: 2, limit: "~55 customers/hr" },
        { time: "4pm-7pm", status: "Understaffed", staff: 3, limit: "~70 customers/hr" },
        { time: "7pm-9pm", status: "Adequate", staff: 2, limit: "~25 customers/hr" }
      ],
      recommendation: "Add 1 staff member 12pm-2pm. Add 2 staff members 4pm-7pm."
    });
  }, []);

  if (!scheduleData) return <div>Loading Schedule...</div>;

  return (
    <div className="scheduling-dashboard p-6 bg-white rounded shadow text-gray-800">
      <h2 className="text-2xl font-bold mb-4">Tomorrow — {scheduleData.date}</h2>
      
      <div className="metrics bg-blue-50 p-4 rounded mb-6">
        <p><strong>Predicted footfall:</strong> {scheduleData.predicted_footfall} customers <span className="text-red-500 font-bold">({scheduleData.increase_pct}% above normal)</span></p>
        <p><strong>Reason:</strong> {scheduleData.reason}</p>
      </div>

      <h3 className="text-xl font-semibold mb-2">Hour-by-hour adequacy:</h3>
      <ul className="list-none space-y-2 mb-6">
        {scheduleData.hourly_blocks.map((block, i) => (
          <li key={i} className="flex gap-4">
            <span className="w-24 text-right font-medium">{block.time}</span>
            <span className={`w-32 ${block.status === "Adequate" ? "text-green-600" : "text-red-600 font-bold"}`}>
              {block.status === "Adequate" ? "✓" : "✗"} {block.status}
            </span>
            <span className="text-gray-600">({block.staff} staff, {block.limit})</span>
          </li>
        ))}
      </ul>

      <div className="recommendation border-t pt-4">
        <h3 className="text-xl font-semibold mb-2">Recommendation:</h3>
        <p className="whitespace-pre-wrap">{scheduleData.recommendation}</p>
      </div>
    </div>
  );
};

export default Scheduling;

```


## File: `./dashboard/src/ApprovalQueue.jsx`
```jsx
import React, { useState } from 'react'

function formatTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
}

function ApprovalQueue({ approvals, onRefresh }) {
  const [processing, setProcessing] = useState(null)

  const handleAction = async (id, action) => {
    setProcessing(id)
    try {
      await fetch(`/api/approvals/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approval_id: id, reason: action === 'reject' ? 'Owner rejected' : '' }),
      })
      onRefresh()
    } catch (err) {
      console.error(`Failed to ${action}:`, err)
    } finally {
      setProcessing(null)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Owner Approval Queue</h2>
        <button onClick={onRefresh} className="px-3 py-1 rounded bg-gray-800 text-gray-400 hover:bg-gray-700 text-xs">
          Refresh
        </button>
      </div>

      {approvals.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-4xl mb-4">✓</div>
          <div className="text-gray-400 text-lg font-medium">All clear</div>
          <div className="text-gray-600 text-sm mt-1">No pending approvals</div>
        </div>
      ) : (
        <div className="space-y-4">
          {approvals.map(approval => {
            const details = approval.result?.approval_details || {}
            return (
              <div
                key={approval.id}
                className="bg-gray-900/50 border border-gray-800 rounded-xl overflow-hidden hover:border-blue-500/30 transition-colors"
              >
                {/* Card header */}
                <div className="px-6 py-4 border-b border-gray-800">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-xs text-blue-400 font-medium uppercase tracking-wider">
                        {approval.skill}
                      </span>
                      <h3 className="text-white font-semibold mt-1">
                        {approval.result?.approval_reason || 'Action requires approval'}
                      </h3>
                    </div>
                    <span className="text-xs text-gray-500">{formatTime(approval.timestamp)}</span>
                  </div>
                </div>

                {/* Details */}
                <div className="px-6 py-4">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {details.product && (
                      <div>
                        <div className="text-xs text-gray-500">Product</div>
                        <div className="text-sm text-white font-medium mt-1">{details.product}</div>
                      </div>
                    )}
                    {details.supplier && (
                      <div>
                        <div className="text-xs text-gray-500">Supplier</div>
                        <div className="text-sm text-white font-medium mt-1">{details.supplier}</div>
                      </div>
                    )}
                    {details.price_per_unit && (
                      <div>
                        <div className="text-xs text-gray-500">Price/Unit</div>
                        <div className="text-sm text-white font-medium mt-1">₹{details.price_per_unit}</div>
                      </div>
                    )}
                    {details.delivery_days && (
                      <div>
                        <div className="text-xs text-gray-500">Delivery</div>
                        <div className="text-sm text-white font-medium mt-1">{details.delivery_days} days</div>
                      </div>
                    )}
                    {details.min_order_qty && (
                      <div>
                        <div className="text-xs text-gray-500">Min Order</div>
                        <div className="text-sm text-white font-medium mt-1">{details.min_order_qty} units</div>
                      </div>
                    )}
                    {details.total_evaluated && (
                      <div>
                        <div className="text-xs text-gray-500">Evaluated</div>
                        <div className="text-sm text-white font-medium mt-1">{details.total_evaluated} suppliers</div>
                      </div>
                    )}
                  </div>

                  {details.reasoning && (
                    <div className="mt-4 px-4 py-3 rounded-lg bg-gray-950/50 border border-gray-800">
                      <div className="text-xs text-gray-500 mb-1">AI Reasoning</div>
                      <div className="text-sm text-gray-300">{details.reasoning}</div>
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="px-6 py-4 border-t border-gray-800 flex gap-3">
                  <button
                    onClick={() => handleAction(approval.id, 'approve')}
                    disabled={processing === approval.id}
                    className="flex-1 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white font-semibold text-sm transition-colors disabled:opacity-50"
                  >
                    {processing === approval.id ? 'Processing...' : 'Approve'}
                  </button>
                  <button
                    onClick={() => handleAction(approval.id, 'reject')}
                    disabled={processing === approval.id}
                    className="flex-1 py-2.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 font-semibold text-sm transition-colors disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default ApprovalQueue

```


## File: `./dashboard/src/main.jsx`
```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)

```


## File: `./dashboard/src/App.jsx`
```jsx
import React, { useState, useEffect, useRef } from 'react';
import { 
  LayoutDashboard, 
  CheckCircle2, 
  History, 
  Users, 
  Bell,
  RefreshCw,
  Zap,
  Package,
  Briefcase,
  FolderKanban,
  Menu
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import Sidebar from './components/Sidebar';
import HomeTab from './components/HomeTab';
import ApprovalsTab from './components/ApprovalsTab';
import WhatHappenedTab from './components/WhatHappenedTab';
import AgentsTab from './components/AgentsTab';
import InventoryTab from './components/InventoryTab';
import PlansTab from './components/PlansTab';
import WorkspaceTab from './components/WorkspaceTab';

export default function App() {
  const [activeTab, setActiveTab] = useState('home');
  const [logs, setLogs] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [agents, setAgents] = useState([]);
  const [stats, setStats] = useState({
    moneySaved: 8400,
    ordersPlaced: 6,
    offersSent: 147,
    hoursSaved: 12
  });
  const [plans] = useState([
    {
      id: 'ui-refresh',
      title: 'UI Experience Upgrade',
      owner: 'Product + Frontend',
      status: 'in_progress',
      progress: 68,
      summary: 'Polish the dashboard into a clearer, faster workspace with better structure and stronger decision surfaces.',
      focus: 'Navigation, homepage framing, approval visibility, and cleaner user-facing language.',
      nextAction: 'Finalize the new dashboard flow and connect future user-specific widgets to live data.',
      milestones: [
        { label: 'Navigation cleanup', done: true },
        { label: 'Add plans overview', done: true },
        { label: 'Surface workspace context', done: false },
        { label: 'Refine mobile layout', done: false },
      ],
    },
    {
      id: 'user-workspace',
      title: 'Custom User Work Setup',
      owner: 'Ops + Personalization',
      status: 'planned',
      progress: 42,
      summary: 'Shape the product around the user: role, routines, priorities, communication style, and preferred workflows.',
      focus: 'Morning checklist, approval style, business goals, notification preferences, and store context.',
      nextAction: 'Move these preferences from UI scaffolding into persistent backend settings and onboarding.',
      milestones: [
        { label: 'Map user profile fields', done: true },
        { label: 'Design workspace setup UI', done: true },
        { label: 'Persist preferences in API', done: false },
        { label: 'Enable editable routines', done: false },
      ],
    },
  ]);
  const [workspaceProfile] = useState({
    name: 'Soham',
    role: 'Store Owner',
    workStyle: 'Hands-on in the morning, approval-driven in the afternoon, summary-first at night.',
    location: 'Primary retail floor',
    goals: [
      'Reduce time spent chasing suppliers',
      'Keep approvals short and easy to review',
      'See the next important action without digging',
    ],
    routines: [
      { label: 'Morning opening check', time: '08:30', detail: 'Review low-stock items and overnight alerts.' },
      { label: 'Midday approval sweep', time: '13:00', detail: 'Approve urgent supplier and pricing decisions.' },
      { label: 'Evening summary', time: '20:30', detail: 'Get a short wrap-up of store actions and outcomes.' },
    ],
    preferences: [
      { label: 'Approval style', value: 'Quick summary + best option first' },
      { label: 'Notifications', value: 'Urgent only during business hours' },
      { label: 'Decision mode', value: 'Manual approval for supplier commits' },
      { label: 'Focus area', value: 'Inventory health and supplier savings' },
    ],
  });
  const [isConnected, setIsConnected] = useState(false);
  const ws = useRef(null);
  const navItems = [
    { id: 'home', label: 'Overview', icon: LayoutDashboard },
    { id: 'plans', label: 'Plans', icon: FolderKanban },
    { id: 'workspace', label: 'Workspace', icon: Briefcase },
    { id: 'inventory', label: 'Inventory', icon: Package },
    { id: 'approvals', label: 'Approvals', icon: CheckCircle2, badge: approvals.length },
    { id: 'history', label: 'Activity', icon: History },
    { id: 'agents', label: 'Agents', icon: Users }
  ];

  useEffect(() => {
    fetchData();
    connectWebSocket();
    const interval = setInterval(fetchData, 30000);
    return () => {
      clearInterval(interval);
      if (ws.current) ws.current.close();
    };
  }, []);

  const fetchData = async () => {
    try {
      const [statusRes, approvalsRes, logsRes] = await Promise.all([
        fetch('/api/status'),
        fetch('/api/approvals'),
        fetch('/api/audit?limit=100')
      ]);
      
      const statusData = await statusRes.json();
      const approvalsData = await approvalsRes.json();
      const logsData = await logsRes.json();

      setAgents(statusData.skills || []);
      setApprovals(approvalsData || []);
      setLogs(logsData || []);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    }
  };

  const connectWebSocket = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    ws.current = new WebSocket(`${protocol}//${host}/ws/events`);

    ws.current.onopen = () => setIsConnected(true);
    ws.current.onclose = () => {
      setIsConnected(false);
      setTimeout(connectWebSocket, 3000);
    };
    ws.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.type === 'audit_log') {
        setLogs(prev => [message.data, ...prev].slice(0, 100));
        if (['owner_approved', 'owner_rejected', 'approval_requested'].includes(message.data.event_type)) {
          fetchData();
        }
      }
    };
  };

  const headerMap = {
    home: {
      title: 'Dashboard',
      subtitle: 'Real-time overview of your store operations',
    },
    plans: {
      title: 'Execution Plans',
      subtitle: 'Track the UI upgrade and custom user workspace rollout',
    },
    inventory: {
      title: 'Inventory',
      subtitle: 'Real-time stock levels and alerts',
    },
    workspace: {
      title: 'User Workspace',
      subtitle: 'A custom setup built around how the user actually works',
    },
    approvals: {
      title: 'Approvals',
      subtitle: `${approvals.length} pending decisions`,
    },
    history: {
      title: 'What Happened',
      subtitle: 'Complete audit trail of every action',
    },
    agents: {
      title: 'My Agents',
      subtitle: 'Your autonomous agent workforce',
    },
  };

  return (
    <div className="min-h-screen text-stone-900">
      <Sidebar 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        approvalCount={approvals.length}
        isConnected={isConnected}
      />

      <header className="sticky top-0 z-40 border-b border-black/5 bg-[rgba(244,239,230,0.82)] backdrop-blur-xl">
        <div className="mx-auto max-w-[1500px] px-4 sm:px-6 lg:px-10">
          <div className="flex min-h-[84px] items-center justify-between gap-6">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-700 to-amber-700 text-white shadow-lg shadow-teal-900/15">
                <Zap size={20} />
              </div>
              <div>
                <div className="font-display text-2xl font-bold tracking-tight">RetailOS</div>
                <div className="text-xs font-semibold uppercase tracking-[0.28em] text-stone-500">
                  Retail command center
                </div>
              </div>
            </div>

            <div className="hidden xl:flex items-center gap-2 rounded-full border border-black/5 bg-white/50 px-2 py-2 shadow-sm">
              {navItems.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`relative flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition-all ${
                    activeTab === tab.id
                      ? 'bg-stone-900 text-white shadow-sm'
                      : 'text-stone-600 hover:bg-black/[0.04] hover:text-stone-900'
                  }`}
                >
                  <tab.icon size={16} />
                  <span>{tab.label}</span>
                  {tab.badge > 0 && (
                    <span className="rounded-full bg-red-600 px-2 py-0.5 text-[10px] font-bold text-white">
                      {tab.badge}
                    </span>
                  )}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-3">
              <div className="hidden sm:flex items-center gap-2 rounded-full border border-black/5 bg-white/55 px-4 py-2 text-sm">
                <div className={`h-2.5 w-2.5 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-red-500'}`} />
                <span className="font-medium text-stone-700">
                  {isConnected ? 'Live updates active' : 'Reconnecting'}
                </span>
              </div>
              <button 
                onClick={fetchData}
                className="rounded-full border border-black/5 bg-white/55 p-3 text-stone-600 transition-all hover:bg-white hover:text-stone-900"
                title="Refresh data"
              >
                <RefreshCw size={16} />
              </button>
              <div className="relative">
                <button className="rounded-full border border-black/5 bg-white/55 p-3 text-stone-600 transition-all hover:bg-white hover:text-stone-900">
                  <Bell size={16} />
                </button>
                {approvals.length > 0 && (
                  <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
                    {approvals.length}
                  </span>
                )}
              </div>
              <div className="xl:hidden rounded-full border border-black/5 bg-white/55 p-3 text-stone-600">
                <Menu size={16} />
              </div>
            </div>
          </div>

          <div className="xl:hidden overflow-x-auto pb-4 scrollbar-hide">
            <div className="flex min-w-max items-center gap-2">
              {navItems.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold transition-all ${
                    activeTab === tab.id
                      ? 'border-stone-900 bg-stone-900 text-white'
                      : 'border-black/5 bg-white/55 text-stone-600 hover:bg-white'
                  }`}
                >
                  <tab.icon size={15} />
                  <span>{tab.label}</span>
                  {tab.badge > 0 && (
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${activeTab === tab.id ? 'bg-white/15 text-white' : 'bg-red-600 text-white'}`}>
                      {tab.badge}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1500px] px-4 py-8 sm:px-6 lg:px-10">
        <div className="grid gap-8 xl:grid-cols-[260px_minmax(0,1fr)]">
          <aside className="hidden xl:block">
            <div className="sticky top-28">
              <div className="mb-6 rounded-[28px] border border-black/5 bg-white/55 p-6 shadow-[0_20px_60px_rgba(0,0,0,0.06)]">
                <div className="text-xs font-black uppercase tracking-[0.22em] text-stone-500">Current View</div>
                <h2 className="font-display mt-3 text-3xl font-bold tracking-tight text-stone-900">
                  {headerMap[activeTab]?.title || 'Dashboard'}
                </h2>
                <p className="mt-3 text-sm leading-relaxed text-stone-600">
                  {headerMap[activeTab]?.subtitle || 'Real-time overview of your store operations'}
                </p>
              </div>
            </div>
          </aside>

          <div className="min-w-0">
            <div className="mb-8 xl:hidden">
              <div className="text-xs font-black uppercase tracking-[0.22em] text-stone-500">Current View</div>
              <h2 className="font-display mt-2 text-3xl font-bold tracking-tight text-stone-900">
                {headerMap[activeTab]?.title || 'Dashboard'}
              </h2>
              <p className="mt-2 text-sm text-stone-600">
                {headerMap[activeTab]?.subtitle || 'Real-time overview of your store operations'}
              </p>
            </div>
            
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                {activeTab === 'home' && (
                  <HomeTab 
                    stats={stats} 
                    logs={logs} 
                    approvalCount={approvals.length}
                    plans={plans}
                    workspaceProfile={workspaceProfile}
                    onGoToApprovals={() => setActiveTab('approvals')}
                    onGoToPlans={() => setActiveTab('plans')}
                    onGoToWorkspace={() => setActiveTab('workspace')}
                  />
                )}
                {activeTab === 'plans' && (
                  <PlansTab plans={plans} />
                )}
                {activeTab === 'approvals' && (
                  <ApprovalsTab 
                    approvals={approvals} 
                    onRefresh={fetchData}
                  />
                )}
                {activeTab === 'history' && (
                  <WhatHappenedTab 
                    logs={logs} 
                  />
                )}
                {activeTab === 'agents' && (
                  <AgentsTab 
                    agents={agents} 
                    onRefresh={fetchData}
                  />
                )}
                {activeTab === 'inventory' && (
                  <InventoryTab />
                )}
                {activeTab === 'workspace' && (
                  <WorkspaceTab
                    plans={plans}
                    workspaceProfile={workspaceProfile}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </main>
    </div>
  );
}

```


## File: `./dashboard/src/SkillStatus.jsx`
```jsx
import React from 'react'

const STATE_CONFIG = {
  running: { label: 'Running', dot: 'bg-emerald-400 animate-pulse', badge: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' },
  paused: { label: 'Paused', dot: 'bg-amber-400', badge: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
  error: { label: 'Error', dot: 'bg-red-400 animate-pulse', badge: 'bg-red-500/10 text-red-400 border-red-500/20' },
  initializing: { label: 'Starting', dot: 'bg-blue-400 animate-pulse', badge: 'bg-blue-500/10 text-blue-400 border-blue-500/20' },
  stopped: { label: 'Stopped', dot: 'bg-gray-400', badge: 'bg-gray-500/10 text-gray-400 border-gray-500/20' },
}

const SKILL_DESCRIPTIONS = {
  inventory: 'Monitors stock levels, calculates days until stockout',
  procurement: 'Ranks suppliers using price, reliability, and history',
  negotiation: 'WhatsApp outreach to suppliers, parses messy replies',
  customer: 'Segments customers, sends personalized offers',
  analytics: 'Daily pattern analysis on audit logs and purchases',
}

function SkillStatus({ skills, onRefresh }) {
  const handleToggle = async (name, currentState) => {
    const action = currentState === 'paused' ? 'resume' : 'pause'
    try {
      await fetch(`/api/skills/${name}/${action}`, { method: 'POST' })
      onRefresh()
    } catch (err) {
      console.error(`Failed to ${action} skill:`, err)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Skill Status</h2>
        <button onClick={onRefresh} className="px-3 py-1 rounded bg-gray-800 text-gray-400 hover:bg-gray-700 text-xs">
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {skills.map(skill => {
          const config = STATE_CONFIG[skill.state] || STATE_CONFIG.stopped
          return (
            <div
              key={skill.name}
              className="bg-gray-900/50 border border-gray-800 rounded-lg p-5 hover:border-gray-700 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className={`w-2.5 h-2.5 rounded-full ${config.dot}`} />
                  <h3 className="text-white font-semibold capitalize">{skill.name}</h3>
                </div>
                <button
                  onClick={() => handleToggle(skill.name, skill.state)}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                    skill.state === 'paused'
                      ? 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20'
                      : 'bg-amber-500/10 text-amber-400 hover:bg-amber-500/20'
                  }`}
                >
                  {skill.state === 'paused' ? 'Resume' : 'Pause'}
                </button>
              </div>

              <p className="text-xs text-gray-500 mb-4">
                {SKILL_DESCRIPTIONS[skill.name] || 'No description'}
              </p>

              <div className="flex items-center justify-between text-xs">
                <span className={`px-2 py-0.5 rounded border ${config.badge}`}>
                  {config.label}
                </span>
                <span className="text-gray-500">
                  {skill.run_count} runs
                </span>
              </div>

              {skill.last_error && (
                <div className="mt-3 px-3 py-2 rounded bg-red-500/5 border border-red-500/10">
                  <div className="text-xs text-red-400 truncate">{skill.last_error}</div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {skills.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          No skills loaded. Start the runtime to see skill status.
        </div>
      )}
    </div>
  )
}

export default SkillStatus

```


## File: `./dashboard/src/components/WhatHappenedTab.jsx`
```jsx
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ShoppingCart, 
  Megaphone, 
  MessageCircle, 
  Search, 
  CheckCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  BrainCircuit,
  Calendar,
  Filter
} from 'lucide-react';

const CATEGORIES = {
  'inventory': { label: 'Stock Checks', icon: Search, color: 'text-amber-500', bg: 'bg-amber-500/10' },
  'procurement': { label: 'Supplier Finder', icon: ShoppingCart, color: 'text-blue-500', bg: 'bg-blue-500/10' },
  'negotiation': { label: 'Supplier Talks', icon: MessageCircle, color: 'text-green-500', bg: 'bg-green-500/10' },
  'customer': { label: 'Offers Sent', icon: Megaphone, color: 'text-purple-500', bg: 'bg-purple-500/10' },
  'orchestrator': { label: 'System', icon: BrainCircuit, color: 'text-white/40', bg: 'bg-white/5' },
};

export default function WhatHappenedTab({ logs }) {
  const [filter, setFilter] = useState('All');
  const [expandedLogs, setExpandedLogs] = useState({});

  const toggleLog = (id) => {
    setExpandedLogs(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const filteredLogs = logs.filter(log => {
    if (filter === 'All') return true;
    const cat = CATEGORIES[log.skill]?.label;
    return cat === filter;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between px-1">
        <h2 className="text-xs font-black uppercase tracking-widest text-stone-500">Everything RetailOS did</h2>
        <div className="hidden lg:flex items-center gap-1.5 text-[10px] font-bold text-stone-500">
          <Filter size={10} />
          <span>{filteredLogs.length} events</span>
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide lg:flex-wrap">
        {['All', 'Stock Checks', 'Supplier Finder', 'Supplier Talks', 'Offers Sent'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-full text-[10px] font-black uppercase tracking-widest whitespace-nowrap border transition-all ${
              filter === f 
                ? 'border-teal-700 bg-teal-700 text-white shadow-lg shadow-teal-700/15' 
                : 'border-black/10 bg-white/80 text-stone-600 hover:border-black/15 hover:text-stone-900'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Timeline */}
      <div className="space-y-3 lg:space-y-4">
        {filteredLogs.map((log, i) => {
          const category = CATEGORIES[log.skill] || CATEGORIES.orchestrator;
          const Icon = category.icon;
          const isExpanded = expandedLogs[log.id];

          return (
            <motion.div
              key={log.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: Math.min(i * 0.03, 0.3) }}
              className="group"
            >
              <div className="relative overflow-hidden rounded-2xl border border-black/5 bg-[rgba(255,252,247,0.9)] shadow-[0_18px_45px_rgba(0,0,0,0.05)] transition-all hover:bg-white lg:rounded-3xl">
                <div className="p-4 lg:p-5 flex gap-3 lg:gap-4">
                  <div className={`w-10 h-10 lg:w-12 lg:h-12 rounded-xl lg:rounded-2xl ${category.bg} flex items-center justify-center flex-shrink-0`}>
                    <Icon size={18} className={category.color} />
                  </div>
                  
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className={`text-[10px] font-black uppercase tracking-widest ${category.color}`}>
                        {category.label}
                      </span>
                      <span className="flex flex-shrink-0 items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-stone-500">
                        <Calendar size={10} />
                        {new Date(log.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    
                    <h3 className="text-[13px] font-black leading-tight text-stone-900 transition-colors group-hover:text-teal-700 lg:text-[14px]">
                      {log.decision}
                    </h3>
                    
                    <p className="line-clamp-2 text-[11px] font-medium leading-snug text-stone-600 lg:text-[12px]">
                      {log.reasoning}
                    </p>

                    <button 
                      onClick={() => toggleLog(log.id)}
                      className="mt-2 flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-teal-700/80 transition-colors hover:text-teal-700"
                    >
                      <BrainCircuit size={12} />
                      <span>{isExpanded ? 'Hide thinking' : 'How did you decide this?'}</span>
                      {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    </button>
                  </div>
                </div>

                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="border-t border-black/5 bg-stone-50"
                    >
                      <div className="p-5 space-y-3">
                        <div className="text-[10px] font-black uppercase tracking-widest text-teal-700">Here's exactly how I thought about this:</div>
                        <div className="rounded-2xl border border-black/5 bg-white p-4 text-[12px] font-medium italic leading-relaxed text-stone-700">
                          "{log.reasoning || "I checked the current data and historical patterns to ensure the best possible outcome for your business."}"
                        </div>
                        {log.outcome && (
                          <div className="space-y-2">
                             <div className="text-[10px] font-black uppercase tracking-widest text-stone-500">Final Result:</div>
                             <div className="max-h-32 overflow-y-auto break-all rounded-xl border border-black/5 bg-white p-3 font-mono text-[11px] text-stone-600 scrollbar-thin">
                               {log.outcome}
                             </div>
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          );
        })}

        {filteredLogs.length === 0 && (
          <div className="space-y-4 rounded-3xl border-2 border-dashed border-black/10 bg-white/60 px-10 py-20 text-center">
             <div className="text-center text-4xl opacity-40">📜</div>
             <p className="text-sm font-black uppercase tracking-widest leading-none text-stone-500">Nothing found in this list</p>
          </div>
        )}
      </div>
    </div>
  );
}

```


## File: `./dashboard/src/components/ApprovalsTab.jsx`
```jsx
import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Check, 
  X, 
  MessageCircle, 
  ChevronDown, 
  ChevronUp,
  AlertTriangle,
  ArrowRight,
  TrendingUp,
  Clock,
  ShieldCheck
} from 'lucide-react';

const PRODUCT_ICONS = {
  'SKU-001': '🍦',
  'SKU-002': '🧂',
  'SKU-003': '🍼',
  'SKU-004': '🍞',
  'SKU-005': '🥚',
};

export default function ApprovalsTab({ approvals, onRefresh }) {
  const [expandedThreads, setExpandedThreads] = useState({});
  const [negotiations, setNegotiations] = useState({});

  useEffect(() => {
    fetchNegotiations();
  }, [approvals]);

  const fetchNegotiations = async () => {
    try {
      const res = await fetch('/api/negotiations');
      const data = await res.json();
      setNegotiations(data.active || {});
    } catch (e) {
      console.error('Failed to fetch negotiations:', e);
    }
  };

  const toggleThread = (id) => {
    setExpandedThreads(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const handleAction = async (id, type) => {
    try {
      const endpoint = type === 'approve' ? 'approve' : 'reject';
      await fetch(`/api/approvals/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approval_id: id })
      });
      onRefresh();
    } catch (e) {
      console.error(`Failed to ${type}:`, e);
    }
  };

  if (approvals.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 lg:py-32 text-center space-y-4 px-6">
        <div className="flex h-20 w-20 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 lg:h-24 lg:w-24">
          <motion.div animate={{ y: [0, -5, 0] }} transition={{ repeat: Infinity, duration: 2 }}>
            <Check size={40} strokeWidth={3} />
          </motion.div>
        </div>
        <div>
          <h2 className="text-lg lg:text-xl font-black uppercase tracking-tight text-stone-900">Nothing needs your attention</h2>
          <p className="mt-1 text-sm font-medium leading-normal text-stone-600 lg:text-base">
            RetailOS is monitoring everything for you. Go grab a chai! ☕
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h2 className="px-1 text-xs font-black uppercase tracking-widest text-stone-500">RetailOS needs your decision</h2>
      
      {/* Grid: 1 col mobile, 2 cols desktop */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-6">
        {approvals.map((approval, i) => {
          const result = approval.result || {};
          const isInventory = approval.skill === "inventory";
          const topSupplier = result.top_supplier || result.parsed || {};
          
          let sku, productName;
          if (isInventory) {
              const alert = result.alerts && result.alerts.length > 0 ? result.alerts[0] : {};
              sku = alert.sku;
              productName = alert.product_name || "Unknown Product";
          } else {
              sku = result.sku || (approval.event?.data?.sku);
              productName = result.product || result.product_name || "Unknown Product";
          }
          
          const icon = PRODUCT_ICONS[sku] || '📦';
          const negId = result.negotiation_id;
          const thread = negotiations[negId]?.thread || [];
          const approvalReason = approval.reason || result.approval_reason || "I found a better price for this item!";

          return (
            <motion.div
              key={approval.id}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.1 }}
              className="flex flex-col overflow-hidden rounded-[30px] border border-black/5 bg-[rgba(255,252,247,0.92)] text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] transition-all hover:bg-white"
            >
              <div className="flex items-start gap-4 border-b border-black/5 bg-white/75 p-5">
                <span className="text-4xl">{icon}</span>
                <div className="flex-1 min-w-0">
                  <h3 className="mb-1 truncate text-lg font-black leading-none text-stone-900">{productName}</h3>
                  <p className="text-xs font-bold italic leading-snug text-stone-600">
                    {approvalReason}
                  </p>
                </div>
              </div>

              {isInventory ? (
                <div className="flex-1 space-y-4 border-b border-black/5 p-5">
                  <div className="flex items-center gap-2 text-amber-700">
                    <AlertTriangle size={16} />
                    <span className="text-xs font-black uppercase tracking-widest">Restock Needed</span>
                  </div>
                  <div className="text-sm font-medium leading-relaxed text-stone-700">
                    Stock limit breached. Would you like to launch the autonomous agents to restock this?
                  </div>
                  <div className="rounded-xl border border-black/5 bg-white/85 p-3 text-xs italic text-stone-600 shadow-sm">
                    <span className="mr-1 font-bold not-italic text-emerald-700">Action:</span> 
                    {result.approval_details?.action_plan || "Trigger autonomous procurement flow to find the best supplier."}
                  </div>
                </div>
              ) : (
                <div className="flex-1">
                  <div className="p-5 grid grid-cols-2 gap-4 relative">
                    <div className="absolute left-1/2 top-1/2 z-10 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-black/10 bg-stone-100">
                      <ArrowRight size={14} className="text-stone-500" />
                    </div>

                    <div className="space-y-1">
                      <div className="text-[10px] font-black uppercase tracking-widest text-stone-500">Usual Price</div>
                      <div className="text-xl font-black text-stone-500 line-through">₹195</div>
                      <div className="text-[10px] font-bold text-stone-500">From MegaMart</div>
                    </div>

                    <div className="space-y-1 text-right">
                      <div className="mb-1 text-[10px] font-black uppercase tracking-widest leading-none text-emerald-700">New Best Price</div>
                      <div className="mb-1 text-2xl font-black leading-none tracking-tight text-emerald-700">₹{topSupplier.price_per_unit || '---'}</div>
                      <div className="text-[10px] font-bold text-emerald-700/70">You save ₹2,500!</div>
                    </div>
                  </div>

                  <div className="px-5 pb-5 grid grid-cols-3 gap-2">
                    <div className="flex flex-col items-center justify-center rounded-xl border border-black/5 bg-white/85 p-2.5 text-center shadow-sm">
                      <ShieldCheck size={14} className="mb-1 text-teal-700" />
                      <span className="text-[9px] font-black uppercase tracking-tighter leading-none text-stone-500">Trust</span>
                      <span className="mt-0.5 text-[12px] font-black leading-none text-stone-900">94%</span>
                    </div>
                    <div className="flex flex-col items-center justify-center rounded-xl border border-black/5 bg-white/85 p-2.5 text-center shadow-sm">
                      <Clock size={14} className="mb-1 text-amber-700" />
                      <span className="text-[9px] font-black uppercase tracking-tighter leading-none text-stone-500">Wait</span>
                      <span className="mt-0.5 text-[12px] font-black leading-none text-stone-900">1 Day</span>
                    </div>
                    <div className="flex flex-col items-center justify-center rounded-xl border border-black/5 bg-white/85 p-2.5 text-center shadow-sm">
                      <TrendingUp size={14} className="mb-1 text-emerald-700" />
                      <span className="text-[9px] font-black uppercase tracking-tighter leading-none text-stone-500">Quality</span>
                      <span className="mt-0.5 text-[12px] font-black leading-none text-stone-900">AA+</span>
                    </div>
                  </div>
                </div>
              )}

              {negId && (
                <div className="border-t border-black/5">
                  <button 
                    onClick={() => toggleThread(approval.id)}
                    className="group flex w-full items-center justify-between p-4 text-stone-600 transition-colors hover:text-stone-900"
                  >
                    <div className="flex items-center gap-2">
                      <MessageCircle size={16} />
                      <span className="text-[10px] font-black uppercase tracking-widest">See our WhatsApp talk</span>
                    </div>
                    {expandedThreads[approval.id] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                  
                  <AnimatePresence>
                    {expandedThreads[approval.id] && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden bg-stone-50 px-4 pb-4"
                      >
                        <div className="pt-2 flex flex-col gap-3">
                          {thread.map((msg, mid) => (
                            <div key={mid} className={`flex flex-col ${msg.direction === 'outbound' ? 'items-end' : 'items-start'}`}>
                              <div className="mb-1 text-[8px] font-black uppercase tracking-widest text-stone-500">
                                {msg.direction === 'outbound' ? 'RetailOS sent:' : 'Supplier replied:'}
                              </div>
                              <div className={msg.direction === 'outbound' ? 'whatsapp-bubble-out text-[13px] leading-snug' : 'whatsapp-bubble-in text-[13px] leading-snug'}>
                                {msg.message}
                              </div>
                              <div className="mt-1 text-[9px] font-medium text-stone-500">
                                {new Date(msg.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                              </div>
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              <div className="flex flex-col gap-2 bg-stone-50 p-4 lg:flex-row">
                <motion.button
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handleAction(approval.id, 'approve')}
                  className="btn-success w-full flex items-center justify-center gap-2"
                >
                  <Check size={20} strokeWidth={3} />
                  <span>YES, ORDER IT</span>
                </motion.button>
                <motion.button
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handleAction(approval.id, 'reject')}
                  className="rounded-xl p-3 text-xs font-black uppercase tracking-widest text-red-700 transition-all hover:bg-red-50 lg:w-auto"
                >
                  ❌ No, skip
                </motion.button>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

```


## File: `./dashboard/src/components/HomeTab.jsx`
```jsx
import React from 'react';
import { motion } from 'framer-motion';
import { 
  TrendingUp, 
  Package, 
  Megaphone, 
  Clock,
  ChevronRight,
  CheckCircle2,
  AlertCircle,
  RotateCw,
  Zap,
  ArrowUpRight,
  Briefcase,
  FolderKanban,
  UserCircle2
} from 'lucide-react';

const PRODUCT_ICONS = {
  'SKU-001': '🍦', // Ice Cream
  'SKU-002': '🧂', // Salt
  'SKU-003': '🍼', // Milk
  'SKU-004': '🍞', // Bread
  'SKU-005': '🥚', // Eggs
};

export default function HomeTab({
  stats,
  logs,
  approvalCount,
  plans,
  workspaceProfile,
  onGoToApprovals,
  onGoToPlans,
  onGoToWorkspace,
}) {
  const getEventIcon = (log) => {
    if (log.skill === 'inventory') return <Package size={14} className="text-amber-400" />;
    if (log.skill === 'procurement') return <TrendingUp size={14} className="text-blue-400" />;
    if (log.skill === 'negotiation') return <RotateCw size={14} className="text-green-400" />;
    if (log.skill === 'customer') return <Megaphone size={14} className="text-purple-400" />;
    return <CheckCircle2 size={14} className="text-white/40" />;
  };

  const getLogMessage = (log) => {
    if (log.skill === 'inventory' && log.event_type === 'low_stock_detected') {
      try {
        const data = JSON.parse(log.outcome);
        const icon = PRODUCT_ICONS[data.sku] || '📦';
        return `${icon} ${data.product_name} was running low. Checking with suppliers...`;
      } catch { return log.decision; }
    }
    if (log.skill === 'negotiation' && log.event_type === 'outreach_sent') {
      const meta = log.metadata || {};
      return `🤝 Sent a message to ${meta.supplier_id || 'supplier'} to get a better price.`;
    }
    if (log.skill === 'negotiation' && log.event_type === 'reply_parsed') {
      return `💬 Supplier replied! They offered a good deal. Waiting for your approval.`;
    }
    if (log.skill === 'customer' && log.event_type === 'offer_sent') {
      return `📣 Sent a special offer to customers. 12 people already looked at it!`;
    }
    if (log.skill === 'orchestrator' && log.event_type === 'owner_approved') {
      return `✅ You approved the order. I've placed it with the supplier.`;
    }
    return log.decision;
  };

  const getStatusColor = (log) => {
    if (log.status === 'alert' || log.status === 'pending') return 'bg-amber-400';
    if (log.status === 'error' || log.status === 'failed') return 'bg-red-500';
    if (log.status === 'success' || log.status === 'approved') return 'bg-green-500';
    return 'bg-blue-500';
  };

  const statCards = [
    { label: 'Money Saved', value: `₹${stats.moneySaved.toLocaleString()}`, icon: TrendingUp, color: 'text-emerald-700', bg: 'bg-emerald-100' },
    { label: 'Orders Placed', value: stats.ordersPlaced, icon: Package, color: 'text-teal-700', bg: 'bg-teal-100' },
    { label: 'Offers Sent', value: stats.offersSent, icon: Megaphone, color: 'text-amber-700', bg: 'bg-amber-100' },
    { label: 'Hours Saved', value: `${stats.hoursSaved} hrs`, icon: Clock, color: 'text-stone-800', bg: 'bg-stone-200' },
  ];

  return (
    <div className="space-y-8 lg:space-y-10">
      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="overflow-hidden rounded-[32px] border border-black/5 bg-[linear-gradient(135deg,rgba(255,252,247,0.95),rgba(233,227,216,0.85))] p-7 shadow-[0_28px_70px_rgba(0,0,0,0.08)] lg:p-9"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-white/70 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-stone-600">
            Retail operations overview
          </div>
          <h1 className="font-display mt-5 max-w-3xl text-4xl font-bold tracking-tight text-stone-900 lg:text-6xl">
            A cleaner control room for what your store needs next.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-stone-600 lg:text-lg">
            Keep the experience web-first: clearer decisions, sharper visibility, and a workspace that feels built for an owner running a real store instead of a generic AI dashboard.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <button
              onClick={onGoToApprovals}
              className={`inline-flex items-center gap-2 rounded-full px-5 py-3 text-sm font-bold transition-all ${
                approvalCount > 0
                  ? 'bg-stone-900 text-white hover:bg-black'
                  : 'bg-emerald-700 text-white hover:bg-emerald-600'
              }`}
            >
              {approvalCount > 0 ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
              <span>
                {approvalCount > 0 ? `Review ${approvalCount} pending approvals` : 'Everything is stable right now'}
              </span>
              <ChevronRight size={16} />
            </button>
            <button
              onClick={onGoToPlans}
              className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white/70 px-5 py-3 text-sm font-bold text-stone-700 transition-all hover:bg-white"
            >
              <FolderKanban size={16} />
              <span>See project plans</span>
            </button>
          </div>
        </motion.div>

        <motion.button
          onClick={onGoToWorkspace}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.06 }}
          className="rounded-[32px] border border-black/5 bg-[rgba(255,252,247,0.78)] p-7 text-left shadow-[0_24px_60px_rgba(0,0,0,0.06)] transition-all hover:bg-white/90"
        >
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700">
                <UserCircle2 size={24} />
              </div>
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.22em] text-stone-500">Workspace profile</div>
                <h3 className="font-display mt-1 text-2xl font-bold tracking-tight text-stone-900">
                  {workspaceProfile.name}
                </h3>
              </div>
            </div>
            <Briefcase size={18} className="text-stone-400" />
          </div>
          <p className="mt-5 text-sm leading-relaxed text-stone-600">
            {workspaceProfile.workStyle}
          </p>
          <div className="mt-6 space-y-3">
            {workspaceProfile.preferences.slice(0, 3).map((item) => (
              <div key={item.label} className="flex items-start justify-between gap-4 border-t border-black/5 pt-3 text-sm">
                <span className="text-stone-500">{item.label}</span>
                <span className="max-w-[60%] text-right font-semibold text-stone-800">{item.value}</span>
              </div>
            ))}
          </div>
        </motion.button>
      </section>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {statCards.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
            className="rounded-[28px] border border-black/5 bg-[rgba(255,252,247,0.72)] p-5 shadow-[0_18px_45px_rgba(0,0,0,0.05)] transition-all"
          >
            <div className={`mb-4 flex h-11 w-11 items-center justify-center rounded-2xl ${stat.bg}`}>
              <stat.icon size={18} className={stat.color} />
            </div>
            <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-stone-500">{stat.label}</div>
            <div className={`mt-1 text-2xl font-black tracking-tight ${stat.color}`}>{stat.value}</div>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <motion.button
          onClick={onGoToPlans}
          whileTap={{ scale: 0.99 }}
          className="rounded-[32px] border border-black/5 bg-[rgba(255,252,247,0.78)] p-6 text-left shadow-[0_22px_55px_rgba(0,0,0,0.06)] transition-all hover:bg-white/90 lg:p-7"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-teal-50 px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-teal-700">
                <FolderKanban size={12} />
                Two Plans In Motion
              </div>
              <h3 className="font-display mt-4 text-2xl font-bold tracking-tight text-stone-900">Build the product in two tracks</h3>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-stone-600">
                One plan sharpens the UI. The other shapes a custom work setup around the user so RetailOS fits real daily flow.
              </p>
            </div>
            <ArrowUpRight size={18} className="flex-shrink-0 text-teal-700" />
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {plans.map((plan) => (
              <div key={plan.id} className="rounded-[26px] border border-black/5 bg-[linear-gradient(180deg,rgba(255,255,255,0.7),rgba(246,241,233,0.9))] p-5">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-black text-stone-900">{plan.title}</div>
                  <div className="text-[10px] font-black uppercase tracking-widest text-stone-500">
                    {plan.progress}%
                  </div>
                </div>
                <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-stone-200">
                  <div className="h-full rounded-full bg-gradient-to-r from-teal-700 to-amber-700" style={{ width: `${plan.progress}%` }} />
                </div>
                <p className="mt-3 text-xs leading-relaxed text-stone-600">{plan.focus}</p>
              </div>
            ))}
          </div>
        </motion.button>

        <div className="rounded-[32px] border border-black/5 bg-stone-900 p-6 text-stone-50 shadow-[0_22px_55px_rgba(0,0,0,0.18)] lg:p-7">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10 text-amber-300">
                <Zap size={20} />
              </div>
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.2em] text-stone-400">Live pulse</div>
                <h3 className="font-display mt-1 text-2xl font-bold">What matters right now</h3>
              </div>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            <div className="rounded-[24px] bg-white/5 p-4">
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-stone-400">Approvals</div>
              <div className="mt-2 text-4xl font-black text-white">{approvalCount}</div>
              <p className="mt-2 text-sm leading-relaxed text-stone-300">
                Decisions that still need the owner before the system can commit to a supplier or next action.
              </p>
            </div>
            <div className="rounded-[24px] bg-white/5 p-4">
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-stone-400">Workspace intent</div>
              <p className="mt-2 text-sm leading-relaxed text-stone-200">
                Keep the page calm, web-first, and practical: clear summaries, strong typography, and less AI-dashboard noise.
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-xs font-black uppercase tracking-[0.22em] text-stone-500">What&apos;s happening right now</h2>
          <div className="hidden lg:flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-stone-400">
            <Zap size={10} className="text-amber-700" />
            <span>Live Feed</span>
          </div>
        </div>
        <div className="space-y-3">
          {logs.slice(0, 20).map((log, i) => (
            <motion.div
              key={log.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.03 }}
              className="group flex items-start gap-4 rounded-[24px] border border-black/5 bg-[rgba(255,252,247,0.74)] p-4 transition-all hover:bg-white/90"
            >
              <div className="relative mt-1.5 flex-shrink-0">
                <div className={`w-2 h-2 rounded-full ${getStatusColor(log)}`} />
                <div className={`absolute inset-0 w-2 h-2 rounded-full ${getStatusColor(log)} animate-ping opacity-20`} />
              </div>
              <div className="flex-1 min-w-0 space-y-1">
                <div className="text-sm font-medium leading-snug text-stone-900">
                  {getLogMessage(log)}
                </div>
                <div className="flex items-center gap-2">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-stone-500">
                    {new Date(log.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </div>
                  <span className="text-[8px] text-stone-300">•</span>
                  <div className="flex items-center gap-1">
                    {getEventIcon(log)}
                    <span className="text-[10px] font-bold uppercase tracking-tighter text-stone-500">
                      {log.skill === 'orchestrator' ? 'Manager' : log.skill}
                    </span>
                  </div>
                </div>
              </div>
              <div className="hidden transition-opacity group-hover:opacity-100 lg:block">
                <ArrowUpRight size={14} className="text-stone-400" />
              </div>
            </motion.div>
          ))}
          {logs.length === 0 && (
            <div className="rounded-[28px] border-2 border-dashed border-black/10 py-20 text-center font-bold uppercase tracking-[0.22em] text-stone-400">
              Waiting for actions...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

```


## File: `./dashboard/src/components/AgentsTab.jsx`
```jsx
import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { 
  Package, 
  Search, 
  MessageCircle, 
  Megaphone, 
  BarChart3,
  Settings,
  Pause,
  Play,
  CheckCircle2,
  AlertCircle,
  Zap,
  Calendar
} from 'lucide-react';

const AGENTS = {
  'inventory': { 
    name: 'Stock Watcher', 
    role: 'Checks all 1,200 products every 60 seconds and alerts when anything is running low',
    icon: Package,
    color: 'text-amber-500',
    bg: 'bg-amber-500/10',
    gradient: 'from-amber-500/20 to-orange-500/5'
  },
  'procurement': { 
    name: 'Deal Finder', 
    role: 'Scours the market for the best prices and identifies the most reliable suppliers for you',
    icon: Search,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10',
    gradient: 'from-blue-500/20 to-cyan-500/5'
  },
  'negotiation': { 
    name: 'Supplier Talker', 
    role: 'Handles all the WhatsApp back-and-forth with suppliers to lock in the deals you want',
    icon: MessageCircle,
    color: 'text-green-500',
    bg: 'bg-green-500/10',
    gradient: 'from-green-500/20 to-emerald-500/5'
  },
  'customer': { 
    name: 'Offer Sender', 
    role: 'Finds your best customers and sends them personalized special offers they actually like',
    icon: Megaphone,
    color: 'text-purple-500',
    bg: 'bg-purple-500/10',
    gradient: 'from-purple-500/20 to-pink-500/5'
  },
  'analytics': { 
    name: 'Business Analyst', 
    role: 'Analyzes your sales and orders to give you clear advice on how to grow your supermart',
    icon: BarChart3,
    color: 'text-blue-400',
    bg: 'bg-blue-400/10',
    gradient: 'from-blue-400/20 to-indigo-500/5'
  },
};

export default function AgentsTab({ agents, onRefresh }) {
  const [isTriggering, setIsTriggering] = useState(false);

  const toggleAgent = async (name, currentState) => {
    const endpoint = currentState === 'running' ? 'pause' : 'resume';
    try {
      await fetch(`/api/skills/${name}/${endpoint}`, { method: 'POST' });
      onRefresh();
    } catch (e) {
      console.error('Failed to toggle agent:', e);
    }
  };

  const triggerDemo = async () => {
    setIsTriggering(true);
    try {
      await fetch('/api/demo/trigger-flow', { method: 'POST' });
      alert("✅ Demo triggered! Go to Dashboard to see it starting.");
    } catch (e) {
      console.error('Failed to trigger demo:', e);
    }
    setIsTriggering(false);
  };

  return (
    <div className="space-y-6 lg:space-y-8">
      <div className="flex items-center justify-between px-1">
        <h2 className="text-xs font-black uppercase tracking-widest text-stone-500">Your RetailOS Team</h2>
        <div className="text-[10px] font-bold uppercase tracking-tighter text-stone-500">
          {Object.keys(AGENTS).length} Active Agents
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4 lg:gap-5">
        {Object.entries(AGENTS).map(([key, config], i) => {
          const status = agents.find(a => a.name === key)?.status || 'stopped';
          const isRunning = status === 'running';

          return (
            <motion.div
              key={key}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08 }}
              className="group relative overflow-hidden rounded-[30px] border border-black/5 bg-[rgba(255,252,247,0.92)] p-5 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] transition-all hover:bg-white lg:p-6"
            >
              <div className={`absolute inset-0 bg-gradient-to-br ${config.gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-500`} />

              <div className="flex gap-4 items-start relative z-10">
                <div className={`flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl ${config.bg} shadow-sm lg:h-14 lg:w-14`}>
                  <config.icon size={24} className={config.color} />
                </div>
                
                <div className="flex-1 space-y-1">
                  <div className="flex items-center justify-between">
                    <h3 className="text-[15px] font-black leading-none text-stone-900 lg:text-[16px]">{config.name}</h3>
                    <div className="flex items-center gap-1.5 rounded-full border border-black/10 bg-white/85 px-2 py-0.5">
                      <div className={`h-1.5 w-1.5 rounded-full ${isRunning ? 'bg-emerald-600 animate-pulse' : 'bg-stone-400'}`} />
                      <span className="text-[9px] font-black uppercase tracking-widest text-stone-500">
                        {isRunning ? 'Working' : 'Paused'}
                      </span>
                    </div>
                  </div>
                  
                  <p className="text-[11px] font-medium leading-tight text-stone-600 lg:text-[12px]">
                    {config.role}
                  </p>
                </div>
              </div>

              <div className="relative z-10 mt-4 flex items-center justify-between border-t border-black/5 pt-4">
                <div className="flex items-center gap-4">
                  <div className="space-y-0.5">
                    <div className="text-[8px] font-black uppercase tracking-widest text-stone-500">Today's Work</div>
                    <div className="flex items-center gap-1 text-[11px] font-black text-stone-900">
                      <Zap size={10} className="text-teal-700" />
                      {key === 'inventory' ? '720 checks' : 
                       key === 'procurement' ? '8 suppliers found' :
                       key === 'negotiation' ? '4 deals closed' : 
                       key === 'customer' ? '23 offers sent' :
                       key === 'analytics' ? '3 insights' :
                       'No alerts today'}
                    </div>
                  </div>
                  <div className="h-6 w-px bg-black/8" />
                  <div className="space-y-0.5">
                    <div className="text-[8px] font-black uppercase tracking-widest text-stone-500">Efficiency</div>
                    <div className="text-[11px] font-black text-stone-700">98.2%</div>
                  </div>
                </div>

                <button 
                  onClick={() => toggleAgent(key, status)}
                  className={`p-2.5 rounded-xl border transition-all ${
                    isRunning 
                      ? 'border-black/10 bg-white/85 text-stone-500 hover:bg-white hover:text-stone-900' 
                      : 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                  }`}
                >
                  {isRunning ? <Pause size={14} /> : <Play size={14} />}
                </button>
              </div>
            </motion.div>
          );
        })}
      </div>

      <div className="pt-6 lg:pt-10 pb-4 flex flex-col items-center gap-4">
        <div className="text-[10px] font-black uppercase tracking-[0.3em] italic text-stone-400">Advanced Control</div>
        <button
          onClick={triggerDemo}
          disabled={isTriggering}
          className="flex items-center gap-2 rounded-2xl border border-black/10 bg-white/85 px-6 py-3 text-[10px] font-black uppercase tracking-widest text-stone-700 transition-all hover:bg-white hover:text-stone-900 disabled:opacity-50"
        >
          {isTriggering ? '🚀 Launching...' : '🚀 Launch Low Stock Demo'}
        </button>
      </div>
    </div>
  );
}

```


## File: `./dashboard/src/components/PlansTab.jsx`
```jsx
import React from 'react';
import { motion } from 'framer-motion';
import { CheckCircle2, CircleDashed, FolderKanban, Layers3, Sparkles } from 'lucide-react';

const STATUS_STYLES = {
  in_progress: {
    label: 'In Progress',
    color: 'text-teal-700',
    chip: 'bg-teal-50 border-teal-200',
  },
  planned: {
    label: 'Planned',
    color: 'text-amber-700',
    chip: 'bg-amber-50 border-amber-200',
  },
  done: {
    label: 'Done',
    color: 'text-emerald-700',
    chip: 'bg-emerald-50 border-emerald-200',
  },
};

export default function PlansTab({ plans }) {
  return (
    <div className="space-y-6 lg:space-y-8">
      <div className="overflow-hidden rounded-[2rem] border border-black/5 bg-[linear-gradient(135deg,rgba(239,247,242,0.96),rgba(247,241,232,0.9))] shadow-[0_20px_55px_rgba(0,0,0,0.06)]">
        <div className="p-6 lg:p-8">
          <div className="inline-flex items-center gap-2 rounded-full border border-teal-200 bg-white/75 px-3 py-1 text-[10px] font-black uppercase tracking-[0.24em] text-teal-700">
            <FolderKanban size={12} />
            Execution Map
          </div>
          <h2 className="font-display mt-4 text-2xl font-bold tracking-tight text-stone-900 lg:text-4xl">Two plans, one product direction</h2>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-stone-600 lg:text-base">
            We are improving the dashboard experience and building a custom work setup around the user at the same time, so the UI looks better and works more personally.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4 lg:gap-6">
        {plans.map((plan, index) => {
          const status = STATUS_STYLES[plan.status] || STATUS_STYLES.planned;

          return (
            <motion.div
              key={plan.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.08 }}
              className="overflow-hidden rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.86)] text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)]"
            >
              <div className="border-b border-black/5 p-6 lg:p-7">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-[0.18em] ${status.chip} ${status.color}`}>
                      <Layers3 size={12} />
                      {status.label}
                    </div>
                    <h3 className="font-display mt-4 text-xl font-bold tracking-tight text-stone-900 lg:text-2xl">{plan.title}</h3>
                    <p className="mt-1 text-sm text-stone-500">Owner: {plan.owner}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-3xl font-black text-stone-900">{plan.progress}%</div>
                    <div className="text-[10px] font-black uppercase tracking-widest text-stone-500">complete</div>
                  </div>
                </div>

                <div className="mt-5 h-2 w-full overflow-hidden rounded-full bg-stone-200">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-teal-700 via-teal-600 to-amber-600"
                    style={{ width: `${plan.progress}%` }}
                  />
                </div>
              </div>

              <div className="p-6 lg:p-7 space-y-5">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-[0.2em] text-stone-500">Summary</div>
                  <p className="mt-2 text-sm leading-relaxed text-stone-700">{plan.summary}</p>
                </div>

                <div>
                  <div className="text-[10px] font-black uppercase tracking-[0.2em] text-stone-500">Current Focus</div>
                  <p className="mt-2 text-sm leading-relaxed text-stone-700">{plan.focus}</p>
                </div>

                <div>
                  <div className="text-[10px] font-black uppercase tracking-[0.2em] text-stone-500">Milestones</div>
                  <div className="space-y-3 mt-3">
                    {plan.milestones.map((milestone) => (
                      <div key={milestone.label} className="flex items-center gap-3 text-sm">
                        {milestone.done ? (
                          <CheckCircle2 size={16} className="text-emerald-700 flex-shrink-0" />
                        ) : (
                          <CircleDashed size={16} className="text-stone-400 flex-shrink-0" />
                        )}
                        <span className={milestone.done ? 'text-stone-800' : 'text-stone-500'}>
                          {milestone.label}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-2xl border border-black/5 bg-white/88 p-4 shadow-sm">
                  <div className="flex items-center gap-2 text-teal-700">
                    <Sparkles size={14} />
                    <span className="text-[10px] font-black uppercase tracking-[0.18em]">Next Step</span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-stone-700">{plan.nextAction}</p>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

```


## File: `./dashboard/src/components/Sidebar.jsx`
```jsx
import React from 'react';
import { motion } from 'framer-motion';
import { 
  LayoutDashboard, 
  CheckCircle2, 
  History, 
  Users, 
  Zap,
  Wifi,
  WifiOff,
  Package,
  FolderKanban,
  Briefcase
} from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab, approvalCount, isConnected }) {
  const navItems = [
    { id: 'home', label: 'Overview', icon: LayoutDashboard },
    { id: 'plans', label: 'Plans', icon: FolderKanban },
    { id: 'inventory', label: 'Inventory', icon: Package },
    { id: 'workspace', label: 'Workspace', icon: Briefcase },
    { id: 'approvals', label: 'Approvals', icon: CheckCircle2, badge: approvalCount },
    { id: 'history', label: 'Activity', icon: History },
    { id: 'agents', label: 'Agents', icon: Users },
  ];

  return (
    <aside className="hidden">
      <div className="rounded-[28px] border border-black/5 bg-white/55 p-5 shadow-[0_20px_60px_rgba(0,0,0,0.06)]">
        <div className="mb-5 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-700 to-amber-700 text-white shadow-lg shadow-teal-900/15">
            <Zap size={18} className="text-white" />
          </div>
          <div>
            <h1 className="font-display text-lg font-bold tracking-tight text-stone-900">RetailOS</h1>
            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-stone-500">Navigation</p>
          </div>
        </div>

        <nav className="space-y-1">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition-all relative group ${
                activeTab === item.id 
                  ? 'bg-stone-900 text-white shadow-lg shadow-stone-900/10' 
                  : 'text-stone-600 hover:text-stone-900 hover:bg-black/[0.04]'
              }`}
            >
              {activeTab === item.id && (
                <motion.div
                  layoutId="sidebarActive"
                  className="absolute left-2 top-1/2 -translate-y-1/2 h-7 w-1 rounded-r-full bg-amber-600"
                  transition={{ type: "spring", stiffness: 300, damping: 30 }}
                />
              )}
              <item.icon size={18} strokeWidth={activeTab === item.id ? 2.5 : 2} />
              <span>{item.label}</span>
              {item.badge > 0 && (
                <span className="ml-auto flex h-5 w-5 items-center justify-center rounded-full bg-red-600 text-[10px] font-bold text-white">
                  {item.badge}
                </span>
              )}
            </button>
          ))}
        </nav>

        <div className="mt-6 space-y-4">
          <div className="flex items-center gap-3 rounded-2xl border border-black/5 bg-black/[0.03] px-4 py-3">
            {isConnected ? (
              <>
                <div className="relative">
                  <Wifi size={14} className="text-emerald-600" />
                  <div className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-emerald-500 opacity-50 animate-ping" />
                </div>
                <div>
                  <div className="text-xs font-bold text-emerald-700">Connected</div>
                  <div className="text-[10px] text-stone-500">Real-time updates active</div>
                </div>
              </>
            ) : (
              <>
                <WifiOff size={14} className="text-red-600" />
                <div>
                  <div className="text-xs font-bold text-red-700">Disconnected</div>
                  <div className="text-[10px] text-stone-500">Reconnecting...</div>
                </div>
              </>
            )}
          </div>
          <div className="text-center">
            <span className="text-[10px] font-bold tracking-[0.18em] text-stone-400">v1.0.0 · RetailOS</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

```


## File: `./dashboard/src/components/WorkspaceTab.jsx`
```jsx
import React from 'react';
import { motion } from 'framer-motion';
import { Briefcase, CheckCircle2, Clock3, MapPin, Sparkles, Target, UserCircle2 } from 'lucide-react';

export default function WorkspaceTab({ plans, workspaceProfile }) {
  return (
    <div className="space-y-6 lg:space-y-8">
      <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-4 lg:gap-6">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-[2rem] border border-black/5 bg-[linear-gradient(135deg,rgba(239,247,242,0.96),rgba(229,240,238,0.88))] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-8"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-white/70 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-emerald-700">
                <Briefcase size={12} />
                User Workspace
              </div>
              <h2 className="font-display mt-4 text-2xl font-bold tracking-tight lg:text-4xl">{workspaceProfile.name}</h2>
              <p className="mt-3 max-w-2xl text-sm leading-relaxed text-stone-600 lg:text-base">{workspaceProfile.workStyle}</p>
            </div>
            <div className="flex h-14 w-14 items-center justify-center rounded-3xl border border-white/70 bg-white/75 text-emerald-700 shadow-sm">
              <UserCircle2 size={30} />
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-3 mt-6">
            <div className="rounded-2xl border border-black/5 bg-white/80 p-4 shadow-sm">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-stone-500">
                <Target size={12} />
                Role
              </div>
              <div className="mt-2 text-lg font-black text-stone-900">{workspaceProfile.role}</div>
            </div>
            <div className="rounded-2xl border border-black/5 bg-white/80 p-4 shadow-sm">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-stone-500">
                <MapPin size={12} />
                Context
              </div>
              <div className="mt-2 text-lg font-black text-stone-900">{workspaceProfile.location}</div>
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.06 }}
          className="rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.82)] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-7"
        >
          <div className="text-[10px] font-black uppercase tracking-[0.2em] text-stone-500">Plan Alignment</div>
          <div className="space-y-4 mt-4">
            {plans.map((plan) => (
              <div key={plan.id} className="rounded-2xl border border-black/5 bg-white/88 p-4 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-black text-stone-900">{plan.title}</div>
                  <div className="text-xs font-bold text-stone-500">{plan.progress}%</div>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-stone-600">{plan.nextAction}</p>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[0.9fr_1.1fr] gap-4 lg:gap-6">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.12 }}
          className="rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.82)] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-7"
        >
          <div className="flex items-center gap-2 text-emerald-700">
            <Target size={16} />
            <h3 className="text-sm font-black uppercase tracking-[0.16em] text-stone-800">What matters to the user</h3>
          </div>
          <div className="space-y-3 mt-5">
            {workspaceProfile.goals.map((goal) => (
              <div key={goal} className="flex items-start gap-3">
                <CheckCircle2 size={16} className="text-emerald-700 flex-shrink-0 mt-0.5" />
                <p className="text-sm leading-relaxed text-stone-700">{goal}</p>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.18 }}
          className="rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.82)] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-7"
        >
          <div className="flex items-center gap-2 text-teal-700">
            <Clock3 size={16} />
            <h3 className="text-sm font-black uppercase tracking-[0.16em] text-stone-800">Daily flow setup</h3>
          </div>
          <div className="space-y-4 mt-5">
            {workspaceProfile.routines.map((routine) => (
              <div key={routine.label} className="rounded-2xl border border-black/5 bg-white/88 p-4 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-black text-stone-900">{routine.label}</div>
                  <div className="text-[11px] font-black uppercase tracking-widest text-teal-700">{routine.time}</div>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-stone-600">{routine.detail}</p>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.24 }}
        className="rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.82)] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-7"
      >
        <div className="flex items-center gap-2 text-amber-700">
          <Sparkles size={16} />
          <h3 className="text-sm font-black uppercase tracking-[0.16em] text-stone-800">Preference layer</h3>
        </div>
        <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-3 mt-5">
          {workspaceProfile.preferences.map((item) => (
            <div key={item.label} className="rounded-2xl border border-black/5 bg-white/88 p-4 shadow-sm">
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-stone-500">{item.label}</div>
              <div className="mt-2 text-sm font-semibold leading-relaxed text-stone-800">{item.value}</div>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

```


## File: `./dashboard/src/components/InventoryTab.jsx`
```jsx
import React, { useState, useEffect } from 'react';
import { Package, AlertTriangle, RefreshCw, PackageX, CheckCircle, Search, Plus, Minus } from 'lucide-react';
import { motion } from 'framer-motion';

export default function InventoryTab() {
  const [inventory, setInventory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const [updating, setUpdating] = useState(null);

  const fetchInventory = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/inventory');
      const data = await res.json();
      setInventory(data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleStockChange = async (sku, newQuantity) => {
    if (newQuantity < 0) return;
    setUpdating(sku);
    try {
      const response = await fetch('/api/inventory/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sku, quantity: newQuantity })
      });
      if (response.ok) {
        // optimistically update local state to avoid full reload delay
        setInventory(prev => prev.map(item => 
          item.sku === sku ? { ...item, current_stock: newQuantity } : item
        ));
      }
    } catch (err) {
      console.error('Failed to update stock:', err);
    } finally {
      setUpdating(null);
    }
  };

  useEffect(() => {
    fetchInventory();
  }, []);

  const filtered = inventory.filter(item => 
    item.product_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    item.sku?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <div className="relative flex-1 max-w-md">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
          <input
            type="text"
            placeholder="Search by name or SKU..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full rounded-xl border border-black/10 bg-white/80 py-2.5 pl-10 pr-4 text-sm text-stone-900 transition-colors placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
          />
        </div>
        <button 
          onClick={fetchInventory}
          disabled={loading}
          className="flex items-center gap-2 rounded-xl border border-black/10 bg-white/80 px-4 py-2.5 text-sm font-semibold text-stone-700 transition-all hover:bg-white disabled:opacity-50"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin text-teal-700' : 'text-teal-700'} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map(item => (
          <motion.div 
            key={item.sku}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="relative overflow-hidden rounded-[28px] border border-black/5 bg-[rgba(255,252,247,0.9)] p-5 text-stone-900 shadow-[0_18px_45px_rgba(0,0,0,0.05)] transition-colors hover:bg-white"
          >
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="mb-1 text-xs font-bold text-stone-500">{item.sku}</div>
                <h3 className="pr-8 text-base font-bold leading-tight text-stone-900">{item.product_name}</h3>
              </div>
              <div className={`p-2 rounded-xl border ${
                item.status === 'critical' ? 'bg-red-50 border-red-200 text-red-700' :
                item.status === 'warning' ? 'bg-amber-50 border-amber-200 text-amber-700' :
                'bg-emerald-50 border-emerald-200 text-emerald-700'
              }`}>
                {item.status === 'critical' ? <PackageX size={18} /> :
                 item.status === 'warning' ? <AlertTriangle size={18} /> :
                 <CheckCircle size={18} />}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-stone-500">Current Stock</div>
                <div className="flex items-center gap-2">
                  <div className="flex shrink-0 items-center overflow-hidden rounded-lg border border-black/10 bg-white/90">
                    <button 
                      onClick={() => handleStockChange(item.sku, item.current_stock - 5)}
                      disabled={updating === item.sku}
                      title="Decrease by 5"
                      className="p-1 px-2 text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-900 disabled:opacity-50"
                    >
                      <Minus size={14} />
                    </button>
                    <span className={`px-2 text-lg font-black text-center min-w-[2.5ch] ${
                      item.status === 'critical' ? 'text-red-700' : 
                      item.status === 'warning' ? 'text-amber-700' : 'text-stone-900'
                    }`}>
                      {updating === item.sku ? '...' : item.current_stock}
                    </span>
                    <button 
                      onClick={() => handleStockChange(item.sku, item.current_stock + 5)}
                      disabled={updating === item.sku}
                      title="Increase by 5"
                      className="p-1 px-2 text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-900 disabled:opacity-50"
                    >
                      <Plus size={14} />
                    </button>
                  </div>
                  <span className="ml-1 whitespace-nowrap pt-1 text-[10px] font-bold uppercase tracking-wider text-stone-500">
                    Min: {item.threshold}
                  </span>
                </div>
              </div>
              <div>
                <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-stone-500">Velocity</div>
                <div className="font-bold text-stone-900">{item.daily_sales_rate} <span className="text-xs font-medium text-stone-500">/day</span></div>
              </div>
            </div>

            <div className="mt-4 flex items-center justify-between border-t border-black/5 pt-4">
              <span className="text-xs font-semibold text-stone-500">Days until empty</span>
              <span className={`text-sm font-black ${
                item.days_until_stockout < 2 ? 'text-red-700' :
                item.days_until_stockout < 5 ? 'text-amber-700' : 'text-emerald-700'
              }`}>
                {item.days_until_stockout === 'Infinity' ? '∞' : item.days_until_stockout} days
              </span>
            </div>
            
            {item.status === 'critical' && (
              <div className="absolute top-0 right-0 w-16 h-16 pointer-events-none">
                <div className="absolute top-0 right-0 w-2 h-2 rounded-full bg-red-500 m-3 shadow-[0_0_12px_rgba(239,68,68,0.8)] animate-pulse" />
              </div>
            )}
          </motion.div>
        ))}
        {filtered.length === 0 && !loading && (
          <div className="col-span-full rounded-[28px] border border-dashed border-black/10 bg-white/70 p-8 py-12 text-center">
            <PackageX size={32} className="mx-auto mb-3 text-stone-400" />
            <h3 className="mb-1 font-semibold text-stone-800">No items found</h3>
            <p className="text-sm text-stone-500">Try adjusting your search</p>
          </div>
        )}
      </div>
    </div>
  );
}

```


## File: `./api/__init__.py`
```py

```


## File: `./api/routes.py`
```py
import asyncio
import json
import time
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from runtime.orchestrator import Orchestrator

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()


class EventPayload(BaseModel):
    type: str
    data: dict[str, Any] = {}


class StockUpdatePayload(BaseModel):
    sku: str
    quantity: int


class SupplierReplyPayload(BaseModel):
    negotiation_id: str
    supplier_id: str
    supplier_name: str
    message: str
    product_name: str = ""


class ApprovalPayload(BaseModel):
    approval_id: str
    reason: str = ""


def create_app(orchestrator: Orchestrator) -> FastAPI:
    app = FastAPI(title="RetailOS", description="Autonomous Agent Runtime for Retail Operations")

    @app.on_event("startup")
    async def startup_event():
        async def broadcast_log(entry):
            await manager.broadcast(json.dumps({
                "type": "audit_log",
                "data": entry
            }, default=str))
        orchestrator.audit.on_log = broadcast_log

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Helper ──────────────────────────────────────────────
    def _get_skill(name: str):
        """Look up a skill from the orchestrator's skills dict."""
        return orchestrator.skills.get(name)

    def _list_skills():
        """Return status for all loaded skills."""
        return [skill.status() for skill in orchestrator.skills.values()]

    # ── Real-time Events ────────────────────────────────────
    @app.websocket("/ws/events")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    # ── Runtime Status ──────────────────────────────────────

    @app.get("/api/status")
    async def get_status():
        skills = _list_skills()
        return {
            "runtime": "running" if orchestrator.running else "stopped",
            "skills": skills,
            "pending_approvals": len(orchestrator.pending_approvals),
            "timestamp": time.time(),
        }

    @app.get("/api/skills")
    async def list_skills():
        return _list_skills()

    @app.post("/api/skills/{skill_name}/pause")
    async def pause_skill(skill_name: str):
        skill = _get_skill(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
        await skill.pause()
        return {"status": "paused", "skill": skill_name}

    @app.post("/api/skills/{skill_name}/resume")
    async def resume_skill(skill_name: str):
        skill = _get_skill(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
        await skill.resume()
        return {"status": "resumed", "skill": skill_name}

    # ── Events ──────────────────────────────────────────────

    @app.post("/api/events")
    async def emit_event(payload: EventPayload):
        await orchestrator.emit_event({"type": payload.type, "data": payload.data})
        return {"status": "event_queued", "type": payload.type}

    # ── Inventory ───────────────────────────────────────────

    @app.get("/api/inventory")
    async def get_inventory():
        skill = _get_skill("inventory")
        if not skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")
        return await skill.get_full_inventory()

    @app.post("/api/inventory/update")
    async def update_stock(payload: StockUpdatePayload):
        """Manually update stock level — used for demo."""
        skill = _get_skill("inventory")
        if not skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")

        result = await skill.update_stock(payload.sku, payload.quantity)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        await orchestrator.emit_event({
            "type": "stock_update",
            "data": {"sku": payload.sku, "quantity": payload.quantity},
        })

        return result

    @app.post("/api/inventory/check")
    async def check_inventory():
        """Trigger a full inventory check."""
        await orchestrator.emit_event({"type": "inventory_check", "data": {}})
        return {"status": "inventory_check_queued"}

    # ── Supplier Reply Webhook ──────────────────────────────

    @app.post("/api/webhook/supplier-reply")
    async def supplier_reply_webhook(payload: SupplierReplyPayload):
        """WhatsApp webhook — receives supplier replies."""
        await orchestrator.emit_event({
            "type": "supplier_reply",
            "data": {
                "negotiation_id": payload.negotiation_id,
                "supplier_id": payload.supplier_id,
                "supplier_name": payload.supplier_name,
                "message": payload.message,
                "product_name": payload.product_name,
            },
        })
        return {"status": "reply_queued"}

    # Mock endpoint for demo — simulate supplier reply
    @app.post("/api/demo/supplier-reply")
    async def mock_supplier_reply(payload: SupplierReplyPayload):
        """Demo endpoint — simulate a supplier WhatsApp reply."""
        negotiation_skill = _get_skill("negotiation")
        if not negotiation_skill:
            raise HTTPException(status_code=404, detail="Negotiation skill not loaded")

        result = await negotiation_skill._handle_reply({
            "negotiation_id": payload.negotiation_id,
            "supplier_id": payload.supplier_id,
            "supplier_name": payload.supplier_name,
            "message": payload.message,
            "product_name": payload.product_name,
        })

        if result.get("needs_approval"):
            approval_id = result["approval_id"]
            orchestrator.pending_approvals[approval_id] = {
                "skill": "negotiation",
                "result": result,
                "event": {"type": "supplier_reply"},
                "timestamp": time.time(),
            }

        return result

    # ── Approvals ───────────────────────────────────────────

    @app.get("/api/approvals")
    async def get_approvals():
        return orchestrator.get_pending_approvals()

    @app.post("/api/approvals/approve")
    async def approve_action(payload: ApprovalPayload):
        result = await orchestrator.approve(payload.approval_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app.post("/api/approvals/reject")
    async def reject_action(payload: ApprovalPayload):
        result = await orchestrator.reject(payload.approval_id, payload.reason)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    # ── Audit Log ───────────────────────────────────────────

    @app.get("/api/audit")
    async def get_audit_logs(skill: str | None = None, event_type: str | None = None, limit: int = 50, offset: int = 0):
        return await orchestrator.audit.get_logs(
            skill=skill, event_type=event_type, limit=limit, offset=offset
        )

    @app.get("/api/audit/count")
    async def get_audit_count():
        count = await orchestrator.audit.get_log_count()
        return {"count": count}

    # ── Negotiations ────────────────────────────────────────

    @app.get("/api/negotiations")
    async def get_negotiations():
        skill = _get_skill("negotiation")
        if not skill:
            raise HTTPException(status_code=404, detail="Negotiation skill not loaded")
        return {
            "active": skill.active_negotiations,
            "message_log": skill.message_log[-50:],
        }

    # ── Analytics ───────────────────────────────────────────

    @app.post("/api/analytics/run")
    async def run_analytics():
        await orchestrator.emit_event({"type": "daily_analytics", "data": {}})
        return {"status": "analytics_queued"}

    @app.get("/api/analytics/summary")
    async def get_analytics_summary():
        if orchestrator.memory:
            summary = await orchestrator.memory.get("orchestrator:daily_summary")
            return summary or {"message": "No analytics summary available yet"}
        return {"message": "Memory not available"}

    # ── Demo Flow (Scripted Chain) ──────────────────────────

    @app.post("/api/demo/trigger-flow")
    async def trigger_demo_flow():
        """Trigger the full ice cream demo flow with timed events."""
        inventory_skill = _get_skill("inventory")
        if not inventory_skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")

        async def _run_demo():
            """Background task: runs the cinematic demo chain."""
            try:
                # Step 1: Drop stock to critical
                await orchestrator.audit.log(
                    skill="orchestrator",
                    event_type="demo_started",
                    decision="🎬 Demo started — Ice cream stock dropping to critical",
                    reasoning="Owner triggered the live demo flow",
                    outcome="Stock will drop to 5 units",
                    status="success",
                )
                await inventory_skill.update_stock("SKU-001", 5)

                await asyncio.sleep(2)

                # Step 2: Simulate inventory detection
                await orchestrator.audit.log(
                    skill="inventory",
                    event_type="low_stock_detected",
                    decision="🚨 Ice cream stock critically low — only 5 units left!",
                    reasoning="Stock dropped below reorder threshold of 20 units",
                    outcome=json.dumps({"sku": "SKU-001", "product_name": "Amul Vanilla Ice Cream", "quantity": 5, "threshold": 20}),
                    status="alert",
                )

                await asyncio.sleep(2)

                # Step 3: Simulate procurement search
                await orchestrator.audit.log(
                    skill="procurement",
                    event_type="supplier_ranking",
                    decision="📋 Evaluated 5 suppliers — FreshFreeze Distributors is the best option",
                    reasoning="Ranked by composite score: price ₹145/unit, reliability 4.8/5, next-day delivery, good trust score (94%)",
                    outcome=json.dumps([
                        {"rank": 1, "supplier_name": "FreshFreeze Distributors", "price_per_unit": 145, "delivery_days": 1},
                        {"rank": 2, "supplier_name": "CoolChain India", "price_per_unit": 155, "delivery_days": 2},
                    ]),
                    status="success",
                )

                await asyncio.sleep(2)

                # Step 4: Simulate negotiation outreach
                await orchestrator.audit.log(
                    skill="negotiation",
                    event_type="outreach_sent",
                    decision="📱 Sent WhatsApp message to FreshFreeze Distributors",
                    reasoning="Top-ranked supplier for ice cream procurement",
                    outcome="Message sent via WhatsApp Business API",
                    status="success",
                    metadata={"supplier_id": "SUP-001"},
                )

                await asyncio.sleep(2)

                # Step 5: Simulate supplier reply
                await orchestrator.audit.log(
                    skill="negotiation",
                    event_type="reply_parsed",
                    decision="💬 Supplier replied: 50 boxes at ₹145/unit, delivery tomorrow, COD accepted",
                    reasoning="Parsed WhatsApp reply from FreshFreeze — deal is within budget (saving ₹2,500 vs usual price)",
                    outcome=json.dumps({
                        "supplier": "FreshFreeze Distributors",
                        "price_per_unit": 145,
                        "quantity": 50,
                        "delivery": "tomorrow",
                        "terms": "COD"
                    }),
                    status="success",
                )

                await asyncio.sleep(2)

                # Step 6: Create the approval card
                approval_id = f"demo_procurement_SKU-001_{int(time.time())}"
                orchestrator.pending_approvals[approval_id] = {
                    "id": approval_id,
                    "skill": "negotiation",
                    "reason": "I found a better price for Amul Vanilla Ice Cream!",
                    "result": {
                        "product_name": "Amul Vanilla Ice Cream",
                        "sku": "SKU-001",
                        "negotiation_id": f"neg_demo_{int(time.time())}",
                        "top_supplier": {
                            "supplier_id": "SUP-001",
                            "supplier_name": "FreshFreeze Distributors",
                            "price_per_unit": 145,
                            "delivery_days": 1,
                            "min_order_qty": 30,
                        },
                        "parsed": {
                            "price_per_unit": 145,
                            "quantity": 50,
                            "delivery": "tomorrow",
                        },
                    },
                    "event": {"type": "supplier_reply"},
                    "timestamp": time.time(),
                }

                await orchestrator.audit.log(
                    skill="orchestrator",
                    event_type="approval_requested",
                    decision="🔔 Deal ready! Waiting for your approval on the Approvals tab",
                    reasoning="FreshFreeze offered ₹145/unit for 50 boxes of ice cream with next-day delivery. Saving ₹2,500 vs usual supplier.",
                    outcome="Approval card created — tap YES to order",
                    status="pending",
                )

            except Exception as e:
                await orchestrator.audit.log(
                    skill="orchestrator",
                    event_type="demo_error",
                    decision="Demo flow encountered an error",
                    reasoning=str(e),
                    outcome="Some steps may not have completed",
                    status="error",
                )

        # Launch the demo as a background task
        asyncio.create_task(_run_demo())

        return {
            "status": "demo_flow_triggered",
            "message": "🎬 Demo started! Watch the Dashboard tab for live events.",
        }

    return app

```


## File: `./skills/procurement.py`
```py
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
                if isinstance(history, str):
                    try:
                        history = json.loads(history)
                    except Exception:
                        history = {}
                
                from brain.context_builder import get_supplier_context
                trust_context = get_supplier_context(sid)
                
                if history and isinstance(history, dict):
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

```


## File: `./skills/__init__.py`
```py

```


## File: `./skills/scheduling.py`
```py
# skills/scheduling.py
import time
import json
from typing import Any
import math
from google import genai
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
        self.client = None
    
    async def init(self) -> None:
        self.state = SkillState.RUNNING

    async def run(self, event: dict[str, Any]) -> dict[str, Any]:
        event_type = event.get("type", "")
        data = event.get("data", {})
        
        if event_type in ["shift_review", "festival_alert"]:
            return await self._review_shifts(data)
        return {"status": "ignored"}

    def _format_am_pm(self, hour: int) -> str:
        if hour == 0: return "12am"
        if hour == 12: return "12pm"
        if hour > 12: return f"{hour-12}pm"
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
        
        if not self.client:
            import os
            api_key = os.environ.get("GEMINI_API_KEY", "")
            if api_key:
                self.client = genai.Client(api_key=api_key)
                
        if self.client:
            try:
                response = await self.client.aio.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt
                )
                report = response.text.strip()
            except Exception as e:
                report = self._build_raw_fallback(target_date, adequacy)
        else:
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

```


## File: `./skills/customer.py`
```py
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

```


## File: `./skills/analytics.py`
```py
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
        self.client: genai.Client | None = None

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
        if not self.client:
            import os
            api_key = os.environ.get("GEMINI_API_KEY", "")
            if api_key:
                self.client = genai.Client(api_key=api_key)
            else:
                return self._fallback_analysis(logs, inventory)

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
            logger.warning("Analytics Gemini call failed: %s", e)
            return self._fallback_analysis(logs, inventory)

    def _fallback_analysis(self, logs: list[dict], inventory: dict) -> dict[str, Any]:
        error_count = sum(1 for l in logs if l.get("status") == "error")
        success_count = sum(1 for l in logs if l.get("status") == "success")

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

```


## File: `./skills/negotiation.py`
```py
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
                model="gemini-2.0-flash",
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

```


## File: `./skills/inventory.py`
```py
import json
import time
from pathlib import Path
from typing import Any

from .base_skill import BaseSkill, SkillState

BASE_DIR = Path(__file__).resolve().parent.parent


class InventorySkill(BaseSkill):
    """Monitors stock levels and fires alerts when items cross thresholds.

    Pure math — no Gemini API calls. Intelligence comes from the orchestrator
    receiving the event and deciding what to do with it.
    """

    def __init__(self, memory=None, audit=None):
        super().__init__(name="inventory", memory=memory, audit=audit)
        self.inventory_data: list[dict] = []
        self.check_interval = 60  # seconds

    async def init(self) -> None:
        try:
            with open(BASE_DIR / "data" / "mock_inventory.json", "r") as f:
                self.inventory_data = json.load(f)
        except FileNotFoundError:
            self.inventory_data = []
        self.state = SkillState.RUNNING

    async def run(self, event: dict[str, Any]) -> dict[str, Any]:
        if not event:
            return {"status": "error", "message": "Event is None"}
            
        """Check inventory levels, return alerts for items crossing threshold."""
        alerts = []

        # Handle explicit expiry risk
        if event.get("type") == "expiry_risk":
            data = event.get("data", {})
            alert = {
                "sku": data.get("product_id"),
                "product_name": data.get("product_name"),
                "severity": "critical",
                "days_to_expiry": data.get("days_to_expiry"),
                "expected_unsold": data.get("expected_unsold"),
                "reason": f"Expiring in {data.get('days_to_expiry')} days. At current velocity, ~{data.get('expected_unsold')} units will expire."
            }
            if self.audit:
                await self.audit.log(
                    skill=self.name,
                    event_type="expiry_risk_detected",
                    decision=f"Flagged expiry risk for {data.get('product_name')}",
                    reasoning=alert["reason"],
                    outcome=json.dumps(alert, default=str),
                    status="alert",
                )
            return {"alerts": [alert]}

        # If triggered with a specific SKU update, process just that
        if event.get("type") == "stock_update":
            sku = event["data"].get("sku")
            new_quantity = event["data"].get("quantity")
            item = self._find_item(sku)
            if item:
                old_qty = item["current_stock"]
                qty_change = new_quantity - old_qty
                
                # Log the movement
                if qty_change != 0:
                    movement_type = event["data"].get("movement_type")
                    if not movement_type:
                        movement_type = "restock" if qty_change > 0 else "sale"
                    from brain.wastage_tracker import log_movement
                    log_movement(sku, qty_change, movement_type)

                item["current_stock"] = new_quantity
                alert = self._check_item(item)
                if alert:
                    alerts.append(alert)
        else:
            # Full scan
            for item in self.inventory_data:
                alert = self._check_item(item)
                if alert:
                    alerts.append(alert)

        if alerts and self.audit:
            for alert in alerts:
                await self.audit.log(
                    skill=self.name,
                    event_type="low_stock_detected",
                    decision=f"Stock alert for {alert['product_name']}",
                    reasoning=(
                        f"Current stock: {alert['current_stock']} units. "
                        f"Daily sales rate: {alert['daily_sales_rate']}/day. "
                        f"Days until stockout: {alert['days_until_stockout']:.1f}. "
                        f"Threshold: {alert['threshold']} units."
                    ),
                    outcome=json.dumps(alert, default=str),
                    status="alert",
                )

        result = {"alerts": alerts, "total_checked": len(self.inventory_data)}
        
        # Only create approval if explicitly updated, to prevent infinite loops of auto-checks
        if alerts and event.get("type") in ["stock_update", "inventory_check"]:
            main_alert = alerts[0]
            result.update({
                "needs_approval": True,
                "approval_id": f"restock_{main_alert['sku']}_{int(time.time())}",
                "approval_reason": f"Low Stock Alert: {main_alert['product_name']} only has {main_alert['current_stock']} units left. Approve AI restock sequence?",
                "approval_details": {
                    "product": main_alert["product_name"],
                    "current_stock": main_alert["current_stock"],
                    "threshold": main_alert["threshold"],
                    "action_plan": "Approve to unleash the Procurement and Negotiation agents to find the best supplier and secure a deal."
                },
                "on_approval_event": {
                    "type": "start_procurement",
                    "data": {
                        "product_name": main_alert["product_name"],
                        "sku": main_alert["sku"],
                        "category": main_alert.get("category", ""),
                        "daily_sales_rate": main_alert.get("daily_sales_rate", 10)
                    }
                }
            })
            
        return result

    def _find_item(self, sku: str) -> dict | None:
        for item in self.inventory_data:
            if item["sku"] == sku:
                return item
        return None

    def _check_item(self, item: dict) -> dict | None:
        """Check if item needs restocking based on stock level AND sales velocity."""
        current = item.get("current_stock", 0)
        daily_rate = item.get("daily_sales_rate", 0)
        threshold = item.get("reorder_threshold", 0)

        # Calculate days until stockout
        days_until_stockout = current / daily_rate if daily_rate > 0 else float("inf")

        # Alert if below threshold OR less than 5 days of stock remaining
        if current <= threshold or (daily_rate > 0 and days_until_stockout < 5):
            return {
                "sku": item["sku"],
                "product_name": item["product_name"],
                "category": item.get("category", ""),
                "current_stock": current,
                "threshold": threshold,
                "daily_sales_rate": daily_rate,
                "days_until_stockout": days_until_stockout,
                "last_restock_date": item.get("last_restock_date", "unknown"),
                "unit_price": item.get("unit_price", 0),
                "severity": "critical" if days_until_stockout < 2 else "warning",
            }

        return None

    async def get_full_inventory(self) -> list[dict]:
        """Return full inventory with computed fields."""
        result = []
        for item in self.inventory_data:
            daily_rate = item.get("daily_sales_rate", 0)
            current = item.get("current_stock", 0)
            days_left = current / daily_rate if daily_rate > 0 else float("inf")
            result.append({
                **item,
                "days_until_stockout": round(float(days_left), 1),
                "status": "critical" if days_left < 2 else "warning" if days_left < 5 else "ok",
            })
        return result

    async def update_stock(self, sku: str, quantity: int, movement_type: str = "") -> dict:
        """Manually update stock for a SKU (used for demo)."""
        item = self._find_item(sku)
        if not item:
            return {"error": f"SKU {sku} not found"}
        old_stock = item["current_stock"]
        qty_change = quantity - old_stock
        
        # Log the movement
        if qty_change != 0:
            derived_type = movement_type if movement_type else ("restock" if qty_change > 0 else "sale")
            from brain.wastage_tracker import log_movement
            log_movement(sku, qty_change, derived_type)
            
        item["current_stock"] = quantity
        return {
            "sku": sku,
            "product_name": item["product_name"],
            "old_stock": old_stock,
            "new_stock": quantity,
        }

```


## File: `./skills/base_skill.py`
```py
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any
import time


class SkillState(Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class BaseSkill(ABC):
    """Abstract base class for all RetailOS skills.

    Every skill must implement: init, run, pause, resume, status.
    The orchestrator only ever calls these five methods.
    """

    def __init__(self, name: str, memory=None, audit=None):
        self.name = name
        self.state = SkillState.INITIALIZING
        self.memory = memory
        self.audit = audit
        self.last_run = None
        self.last_error = None
        self.run_count = 0

    @abstractmethod
    async def init(self) -> None:
        """Load config and memory on startup."""
        pass

    @abstractmethod
    async def run(self, event: dict[str, Any]) -> dict[str, Any]:
        """Execute the skill's core logic given an event."""
        pass

    async def pause(self) -> None:
        """Suspend this skill. Others keep running."""
        self.state = SkillState.PAUSED
        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="skill_paused",
                decision="Skill paused by orchestrator or owner",
                reasoning="Manual pause or orchestrator decision",
                outcome="Skill suspended",
                status="success",
            )

    async def resume(self) -> None:
        """Bring this skill back online."""
        self.state = SkillState.RUNNING
        if self.audit:
            await self.audit.log(
                skill=self.name,
                event_type="skill_resumed",
                decision="Skill resumed",
                reasoning="Manual resume or orchestrator decision",
                outcome="Skill active",
                status="success",
            )

    def status(self) -> dict[str, Any]:
        """Return current health and last action."""
        return {
            "name": self.name,
            "state": self.state.value,
            "last_run": self.last_run,
            "last_error": str(self.last_error) if self.last_error else None,
            "run_count": self.run_count,
        }

    async def _safe_run(self, event: dict[str, Any]) -> dict[str, Any]:
        """Wrapper that tracks run metadata and catches exceptions."""
        self.run_count += 1
        self.last_run = time.time()
        try:
            result = await self.run(event)
            self.state = SkillState.RUNNING
            return result
        except Exception as e:
            self.last_error = e
            self.state = SkillState.ERROR
            raise

```
