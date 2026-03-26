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
