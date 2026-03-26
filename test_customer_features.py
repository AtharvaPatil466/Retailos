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
