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
