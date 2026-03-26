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
