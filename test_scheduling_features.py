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
