from datetime import date, timedelta

import pytest

from brain.db import get_connection
from brain.footfall_analyzer import log_footfall
from brain.shift_optimizer import calculate_adequacy
from skills.scheduling import SchedulingSkill


def _seed_footfall_history():
    base = date.today() - timedelta(days=20)
    for index in range(14):
        current = base + timedelta(days=index)
        current_str = current.strftime("%Y-%m-%d")
        is_saturday = current.weekday() == 5
        for hour in range(24):
            traffic = 45 if is_saturday and (10 <= hour < 18) else 10
            log_footfall(current_str, hour, traffic, traffic // 2)


def _next_target_saturday():
    base = date.today() - timedelta(days=20)
    while base.weekday() != 5:
        base += timedelta(days=1)
    return base + timedelta(days=14)


def test_peak_saturday_is_flagged_understaffed(isolated_brain_db):
    get_connection().close()
    _seed_footfall_history()
    next_saturday = _next_target_saturday()
    next_saturday_str = next_saturday.strftime("%Y-%m-%d")

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO staff_shifts (staff_id, staff_name, role, shift_date, start_hour, end_hour) VALUES (?, ?, ?, ?, ?, ?)",
            ("S1", "John", "Cashier", next_saturday_str, 10, 18),
        )

    adequacy = calculate_adequacy(next_saturday)
    assert any(block["status"] == "Understaffed" for block in adequacy["hourly_blocks"])


def test_festival_multiplier_increases_projection(isolated_brain_db):
    get_connection().close()
    _seed_footfall_history()

    # Use a fixed date near Diwali 2026 to reliably detect a festival
    adequacy = calculate_adequacy(date(2026, 11, 1))
    assert adequacy["festival"] is not None
    assert adequacy["increase_pct"] >= 15


def test_sufficient_staff_clears_understaffed_blocks(isolated_brain_db):
    get_connection().close()
    _seed_footfall_history()
    next_saturday = _next_target_saturday()
    next_saturday_str = next_saturday.strftime("%Y-%m-%d")

    with get_connection() as conn:
        shifts = [
            ("S1", "John", "Cashier"),
            ("S2", "Jane", "Cashier"),
            ("S3", "Bob", "Packer"),
            ("S4", "Alice", "Guard"),
        ]
        for staff_id, name, role in shifts:
            conn.execute(
                "INSERT INTO staff_shifts (staff_id, staff_name, role, shift_date, start_hour, end_hour) VALUES (?, ?, ?, ?, ?, ?)",
                (staff_id, name, role, next_saturday_str, 10, 19),
            )

    adequacy = calculate_adequacy(next_saturday)
    assert not any(
        block["status"] == "Understaffed" for block in adequacy["hourly_blocks"] if 10 <= block["start"] <= 18
    )


@pytest.mark.asyncio
async def test_scheduling_review_needs_approval_and_has_fallback_format(isolated_brain_db, mock_llm_factory):
    get_connection().close()
    _seed_footfall_history()
    next_saturday = _next_target_saturday()
    next_saturday_str = next_saturday.strftime("%Y-%m-%d")

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO staff_shifts (staff_id, staff_name, role, shift_date, start_hour, end_hour) VALUES (?, ?, ?, ?, ?, ?)",
            ("S1", "John", "Cashier", next_saturday_str, 10, 18),
        )

    skill = SchedulingSkill()
    skill.llm = mock_llm_factory(text="Mocked LLM Body perfectly formatting hour-by-hour output.")

    result = await skill._review_shifts({"target_date": next_saturday_str})
    assert result["needs_approval"] is True
    assert result["status"] == "pending_manager_review"

    # Test fallback when LLM raises
    skill.llm = mock_llm_factory(side_effect=RuntimeError("no key"))
    fallback = await skill._review_shifts({"target_date": next_saturday_str})
    assert "Tomorrow —" in fallback["report"]
    assert "Hour-by-hour adequacy:" in fallback["report"]
    assert "✓" in fallback["report"] or "✗" in fallback["report"]
