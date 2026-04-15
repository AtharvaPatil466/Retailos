import time

import pytest

from brain.db import get_connection
from brain.price_analyzer import analyze_quote, format_supplier_verdict
from brain.price_monitor import get_market_reference, log_manual_price
from skills.negotiation import NegotiationSkill


def test_price_verdicts_against_market_reference(isolated_brain_db):
    get_connection().close()

    log_manual_price("PROD_NEW", "Store B", 100.0)
    log_manual_price("PROD_NEW", "Store C", 100.0)

    reference = get_market_reference("PROD_NEW")
    high_quote = analyze_quote(110.0, reference)
    low_quote = analyze_quote(90.0, reference)

    assert high_quote["verdict"] == "above_market"
    assert high_quote["delta_percentage"] == 10.0
    assert low_quote["verdict"] == "below_market"
    assert "countering" in format_supplier_verdict("SupplierX", 110.0, reference)
    assert "countering" not in format_supplier_verdict("SupplierY", 90.0, reference)


def test_old_quotes_downgrade_confidence(isolated_brain_db):
    get_connection().close()

    log_manual_price("PROD_OLD", "Store A", 100.0)
    with get_connection() as conn:
        conn.execute(
            "UPDATE market_prices SET recorded_at = ? WHERE product_id = ?",
            (time.time() - (8 * 86400), "PROD_OLD"),
        )

    reference = get_market_reference("PROD_OLD")
    assert reference["confidence"] == "low"


@pytest.mark.asyncio
async def test_negotiation_prompt_includes_market_reference(isolated_brain_db, mock_llm_factory):
    get_connection().close()

    skill = NegotiationSkill()
    captured_prompts = []

    async def capture(prompt, *, timeout=30):
        captured_prompts.append(prompt)
        return "Mocked msg"

    skill.llm = mock_llm_factory(text="Mocked msg")
    skill.llm.generate.side_effect = capture

    log_manual_price("PROD_NEW", "Store B", 100.0)
    log_manual_price("PROD_NEW", "Store C", 100.0)
    market_ref = get_market_reference("PROD_NEW")
    price_context = (
        f"Market Reference Constraints: We recently saw this product heavily discounted at ₹{market_ref['lowest_price']} "
        f"({market_ref['lowest_source']}). The general market median is ₹{market_ref['median_price']}."
    )

    await skill._draft_outreach("PROD_NEW", {"supplier_name": "TestSupplier"}, {}, price_context)

    assert "Market Reference Constraints" in captured_prompts[0]
    assert "100.0" in captured_prompts[0]
