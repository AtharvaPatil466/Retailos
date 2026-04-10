"""Comprehensive tests for brain/ modules.

Covers: db, decision_logger, trust_scorer, delivery_tracker, quality_scorer,
wastage_tracker, reorder_optimizer, expiry_alerter, footfall_analyzer,
message_tracker, conversion_scorer, price_monitor, price_analyzer,
churn_detector, seasonal_detector.
"""

import os
import time
import pytest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

# Use a test-specific DB to avoid polluting real data
TEST_DB = Path(__file__).resolve().parent.parent / "data" / "test_brain.db"


@pytest.fixture(autouse=True)
def _isolate_brain_db(tmp_path):
    """Point brain.db at a fresh temp file for each test."""
    import brain.db as db_mod

    db_file = tmp_path / "brain.db"
    original_path = db_mod.DB_PATH
    original_init = db_mod._initialized

    db_mod.DB_PATH = db_file
    db_mod._initialized = False

    yield

    db_mod.DB_PATH = original_path
    db_mod._initialized = original_init


# ── brain.db ─────────────────────────────────────────────

class TestBrainDB:
    def test_get_connection_creates_tables(self):
        from brain.db import get_connection
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in cursor.fetchall()}
        expected = {
            "decisions", "deliveries", "quality_flags", "message_outcomes",
            "stock_movements", "product_metadata", "market_prices",
            "footfall_logs", "staff_shifts",
        }
        assert expected.issubset(tables)

    def test_get_connection_idempotent(self):
        from brain.db import get_connection
        with get_connection() as conn:
            conn.execute("INSERT INTO decisions (supplier_id, amount, status, timestamp) VALUES ('s1', 10, 'approved', 0)")
        # Second connection should not re-create / wipe tables
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM decisions")
            assert cursor.fetchone()[0] == 1

    def test_db_exists(self):
        from brain.db import get_connection, db_exists
        assert not db_exists()
        get_connection().close()
        assert db_exists()


# ── decision_logger ──────────────────────────────────────

class TestDecisionLogger:
    def test_log_decision(self):
        from brain.decision_logger import log_decision
        from brain.db import get_connection
        log_decision("SUP1", 500.0, "approved")
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT supplier_id, amount, status FROM decisions")
            row = cursor.fetchone()
        assert row == ("SUP1", 500.0, "approved")

    def test_log_delivery(self):
        from brain.decision_logger import log_delivery
        from brain.db import get_connection
        log_delivery("SUP1", "ord_1", "2026-03-01", "2026-03-02")
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT supplier_id, order_id, expected_date, actual_date FROM deliveries")
            row = cursor.fetchone()
        assert row == ("SUP1", "ord_1", "2026-03-01", "2026-03-02")

    def test_log_quality_flag(self):
        from brain.decision_logger import log_quality_flag
        from brain.db import get_connection
        log_quality_flag("SUP1", "ord_1", "Damaged packaging")
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT supplier_id, reason FROM quality_flags")
            row = cursor.fetchone()
        assert row == ("SUP1", "Damaged packaging")


# ── delivery_tracker ─────────────────────────────────────

class TestDeliveryTracker:
    def test_perfect_delivery_score(self):
        from brain.decision_logger import log_delivery
        from brain.delivery_tracker import get_delivery_score
        for i in range(5):
            log_delivery("SUP_ON_TIME", f"ord_{i}", "2026-03-01", "2026-03-01")
        assert get_delivery_score("SUP_ON_TIME") == 100

    def test_late_delivery_lowers_score(self):
        from brain.decision_logger import log_delivery
        from brain.delivery_tracker import get_delivery_score
        log_delivery("SUP_LATE", "ord_0", "2026-03-01", "2026-03-01")
        log_delivery("SUP_LATE", "ord_1", "2026-03-01", "2026-03-10")  # very late
        score = get_delivery_score("SUP_LATE")
        assert score == 50  # 1 of 2 on time

    def test_unknown_supplier(self):
        from brain.delivery_tracker import get_delivery_score
        from brain.db import get_connection
        get_connection().close()  # ensure tables exist
        assert get_delivery_score("NOBODY") == 50


# ── quality_scorer ───────────────────────────────────────

class TestQualityScorer:
    def test_no_complaints(self):
        from brain.decision_logger import log_delivery
        from brain.quality_scorer import get_quality_score
        for i in range(5):
            log_delivery("SUP_CLEAN", f"ord_{i}", "2026-03-01", "2026-03-01")
        assert get_quality_score("SUP_CLEAN") == 100

    def test_high_complaint_ratio(self):
        from brain.decision_logger import log_delivery, log_quality_flag
        from brain.quality_scorer import get_quality_score
        for i in range(4):
            log_delivery("SUP_BAD", f"ord_{i}", "2026-03-01", "2026-03-01")
        for i in range(4):
            log_quality_flag("SUP_BAD", f"ord_{i}", "Moldy")
        score = get_quality_score("SUP_BAD")
        assert score == 0  # ratio 1.0 → penalty 500 → clamped to 0


# ── trust_scorer ─────────────────────────────────────────

class TestTrustScorer:
    def test_perfect_supplier(self):
        from brain.decision_logger import log_decision, log_delivery
        from brain.trust_scorer import get_trust_score
        for i in range(10):
            log_decision("SUP_TRUST", 100, "approved")
            log_delivery("SUP_TRUST", f"ord_{i}", "2026-03-01", "2026-03-01")
        result = get_trust_score("SUP_TRUST")
        assert result["score"] >= 90
        assert result["is_new"] is False

    def test_late_delivery_lowers_trust(self):
        from brain.decision_logger import log_decision, log_delivery
        from brain.trust_scorer import get_trust_score
        for i in range(10):
            log_decision("SUP_A", 100, "approved")
            log_delivery("SUP_A", f"ord_{i}", "2026-03-01", "2026-03-01")
        for i in range(10):
            log_decision("SUP_B", 100, "approved")
            log_delivery("SUP_B", f"ord_{i}", "2026-03-01", "2026-03-05")
        score_a = get_trust_score("SUP_A")
        score_b = get_trust_score("SUP_B")
        assert score_b["score"] < score_a["score"]

    def test_quality_complaints_lower_trust(self):
        from brain.decision_logger import log_decision, log_delivery, log_quality_flag
        from brain.trust_scorer import get_trust_score
        for i in range(10):
            log_decision("SUP_Q1", 100, "approved")
            log_delivery("SUP_Q1", f"ord_{i}", "2026-03-01", "2026-03-01")
        log_quality_flag("SUP_Q1", "ord_0", "Bad packaging")

        for i in range(10):
            log_decision("SUP_Q5", 100, "approved")
            log_delivery("SUP_Q5", f"ord_{i}", "2026-03-01", "2026-03-01")
        for i in range(5):
            log_quality_flag("SUP_Q5", f"ord_{i}", "Moldy")

        assert get_trust_score("SUP_Q1")["score"] > get_trust_score("SUP_Q5")["score"]

    def test_new_supplier(self):
        from brain.trust_scorer import get_trust_score
        from brain.db import get_connection
        get_connection().close()
        result = get_trust_score("BRAND_NEW")
        assert result["is_new"] is True
        assert result["score"] == 50


# ── wastage_tracker ──────────────────────────────────────

class TestWastageTracker:
    def test_log_movement_valid(self):
        from brain.wastage_tracker import log_movement
        from brain.db import get_connection
        log_movement("P1", 100, "restock")
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT product_id, quantity_change, movement_type FROM stock_movements")
            row = cursor.fetchone()
        assert row == ("P1", 100, "restock")

    def test_log_movement_invalid_type(self):
        from brain.wastage_tracker import log_movement
        with pytest.raises(ValueError):
            log_movement("P1", 10, "stolen")

    def test_wastage_summary(self):
        from brain.wastage_tracker import log_movement, get_wastage_summary
        log_movement("P2", 100, "restock")
        log_movement("P2", -20, "expiry")
        summary = get_wastage_summary("P2")
        assert summary["wastage_rate"] == 0.2
        assert summary["total_lost"] == 20
        assert summary["total_received"] == 100

    def test_no_wastage(self):
        from brain.wastage_tracker import log_movement, get_wastage_summary
        log_movement("P3", 50, "restock")
        summary = get_wastage_summary("P3")
        assert summary["wastage_rate"] == 0.0


# ── reorder_optimizer ────────────────────────────────────

class TestReorderOptimizer:
    def test_high_wastage_reduces_order(self):
        from brain.wastage_tracker import log_movement
        from brain.reorder_optimizer import get_optimized_reorder_quantity
        log_movement("PROD_A", 100, "restock")
        log_movement("PROD_A", -20, "expiry")
        log_movement("PROD_B", 100, "restock")
        log_movement("PROD_B", -5, "expiry")

        opt_a = get_optimized_reorder_quantity("PROD_A", 10, 7)
        opt_b = get_optimized_reorder_quantity("PROD_B", 10, 7)
        assert opt_a["optimized_quantity"] < opt_b["optimized_quantity"]
        assert opt_a["wastage_rate"] > opt_b["wastage_rate"]

    def test_zero_wastage(self):
        from brain.wastage_tracker import log_movement
        from brain.reorder_optimizer import get_optimized_reorder_quantity
        log_movement("PROD_C", 100, "restock")
        result = get_optimized_reorder_quantity("PROD_C", 10, 7)
        assert result["optimized_quantity"] == result["base_quantity"]


# ── expiry_alerter ───────────────────────────────────────

class TestExpiryAlerter:
    def test_slow_seller_flagged(self):
        from brain.db import get_connection
        from brain.expiry_alerter import get_expiry_risks
        yesterday = date.today() - timedelta(days=18)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO product_metadata (product_id, shelf_life_days, last_restock_date) VALUES (?, ?, ?)",
                ("SLOW", 21, yesterday.isoformat()),
            )
        inventory = [{"sku": "SLOW", "product_name": "Slow Milk", "current_stock": 30, "daily_sales_rate": 5}]
        risks = get_expiry_risks(inventory, current_date=date.today())
        assert any(r["data"]["product_id"] == "SLOW" for r in risks)

    def test_fast_seller_not_flagged(self):
        from brain.db import get_connection
        from brain.expiry_alerter import get_expiry_risks
        yesterday = date.today() - timedelta(days=18)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO product_metadata (product_id, shelf_life_days, last_restock_date) VALUES (?, ?, ?)",
                ("FAST", 21, yesterday.isoformat()),
            )
        inventory = [{"sku": "FAST", "product_name": "Fast Milk", "current_stock": 30, "daily_sales_rate": 15}]
        risks = get_expiry_risks(inventory, current_date=date.today())
        assert not any(r["data"]["product_id"] == "FAST" for r in risks)

    def test_no_metadata_no_risk(self):
        from brain.expiry_alerter import get_expiry_risks
        from brain.db import get_connection
        get_connection().close()
        inventory = [{"sku": "UNKNOWN", "product_name": "X", "current_stock": 10, "daily_sales_rate": 1}]
        risks = get_expiry_risks(inventory)
        assert risks == []


# ── footfall_analyzer ────────────────────────────────────

class TestFootfallAnalyzer:
    def test_log_and_retrieve_pattern(self):
        from brain.footfall_analyzer import log_footfall, get_footfall_pattern
        # Create 2 Mondays of data
        base = date.today() - timedelta(days=14)
        for offset in [0, 7]:
            d = base + timedelta(days=offset)
            while d.weekday() != 0:
                d += timedelta(days=1)
            log_footfall(d.strftime("%Y-%m-%d"), 10, 30, 20)
            log_footfall(d.strftime("%Y-%m-%d"), 14, 50, 35)

        pattern = get_footfall_pattern(0)  # Monday
        assert pattern[10] > 0
        assert pattern[14] > 0
        assert pattern[3] == 0  # no data for 3am

    def test_total_predicted(self):
        from brain.footfall_analyzer import log_footfall, get_total_predicted_footfall
        d = date.today()
        while d.weekday() != 2:
            d += timedelta(days=1)
        log_footfall(d.strftime("%Y-%m-%d"), 12, 40, 25)
        total = get_total_predicted_footfall(2)  # Wednesday
        assert total == 40


# ── message_tracker ──────────────────────────────────────

class TestMessageTracker:
    def test_log_and_track(self):
        from brain.message_tracker import log_message_sent, log_reply, log_conversion
        from brain.db import get_connection
        mid = log_message_sent("cust1", "msg_001", "promo_template")
        assert mid == "msg_001"
        log_reply("cust1", "msg_001")
        log_conversion("cust1", "msg_001", 250.0)
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT replied_at, converted_at, purchase_amount FROM message_outcomes WHERE message_id = 'msg_001'")
            row = cursor.fetchone()
        assert row[0] is not None  # replied_at set
        assert row[1] is not None  # converted_at set
        assert row[2] == 250.0

    def test_auto_generate_message_id(self):
        from brain.message_tracker import log_message_sent
        mid = log_message_sent("cust2", "", "template_b")
        assert mid.startswith("msg_")


# ── conversion_scorer ────────────────────────────────────

class TestConversionScorer:
    def test_template_rankings(self):
        from brain.message_tracker import log_message_sent, log_conversion
        from brain.conversion_scorer import get_template_rankings
        # Template A: 5 sends, 4 conversions (80%)
        for i in range(5):
            log_message_sent("c1", f"a_{i}", "Template A")
            if i < 4:
                log_conversion("c1", f"a_{i}", 100)
        # Template B: 10 sends, 2 conversions (20%)
        for i in range(10):
            log_message_sent("c2", f"b_{i}", "Template B")
            if i < 2:
                log_conversion("c2", f"b_{i}", 50)

        rankings = get_template_rankings()
        assert rankings[0]["template"] == "Template A"
        assert rankings[0]["conversion_rate"] == 80.0
        assert rankings[1]["template"] == "Template B"

    def test_template_context_string(self):
        from brain.message_tracker import log_message_sent, log_conversion
        from brain.conversion_scorer import get_template_context
        log_message_sent("c1", "x_0", "Flash Sale")
        log_conversion("c1", "x_0", 200)
        ctx = get_template_context()
        assert "Top performing message templates" in ctx
        assert "Flash Sale" in ctx

    def test_empty_rankings(self):
        from brain.conversion_scorer import get_template_rankings
        from brain.db import get_connection
        get_connection().close()
        assert get_template_rankings() == []


# ── price_monitor ────────────────────────────────────────

class TestPriceMonitor:
    def test_log_and_get_reference(self):
        from brain.price_monitor import log_manual_price, get_market_reference
        log_manual_price("PROD_X", "Store A", 100.0)
        log_manual_price("PROD_X", "Store B", 120.0)
        ref = get_market_reference("PROD_X")
        assert ref["median_price"] == 110.0
        assert ref["lowest_price"] == 100.0
        assert ref["lowest_source"] == "Store A"
        assert ref["confidence"] != "none"

    def test_old_data_low_confidence(self):
        from brain.price_monitor import log_manual_price, get_market_reference
        from brain.db import get_connection
        log_manual_price("PROD_OLD", "Store Z", 50.0)
        # Backdate the entry
        with get_connection() as conn:
            conn.execute(
                "UPDATE market_prices SET recorded_at = ? WHERE product_id = ?",
                (time.time() - 8 * 86400, "PROD_OLD"),
            )
        ref = get_market_reference("PROD_OLD")
        assert ref["confidence"] == "low"

    def test_no_data(self):
        from brain.price_monitor import get_market_reference
        from brain.db import get_connection
        get_connection().close()
        ref = get_market_reference("NONEXISTENT")
        assert ref["confidence"] == "none"
        assert ref["median_price"] is None


# ── price_analyzer ───────────────────────────────────────

class TestPriceAnalyzer:
    def test_above_market(self):
        from brain.price_analyzer import analyze_quote
        ref = {"median_price": 100.0}
        result = analyze_quote(110.0, ref)
        assert result["verdict"] == "above_market"
        assert result["delta_percentage"] == 10.0

    def test_below_market(self):
        from brain.price_analyzer import analyze_quote
        ref = {"median_price": 100.0}
        result = analyze_quote(90.0, ref)
        assert result["verdict"] == "below_market"

    def test_at_market(self):
        from brain.price_analyzer import analyze_quote
        ref = {"median_price": 100.0}
        result = analyze_quote(103.0, ref)
        assert result["verdict"] == "at_market"

    def test_suspiciously_low(self):
        from brain.price_analyzer import analyze_quote
        ref = {"median_price": 100.0}
        result = analyze_quote(70.0, ref)
        assert result["risk_flag"] is not None
        assert "suspiciously_low" in result["risk_flag"]

    def test_suspiciously_high(self):
        from brain.price_analyzer import analyze_quote
        ref = {"median_price": 100.0}
        result = analyze_quote(135.0, ref)
        assert result["risk_flag"] is not None
        assert "suspiciously_high" in result["risk_flag"]

    def test_no_market_data(self):
        from brain.price_analyzer import analyze_quote
        result = analyze_quote(50.0, {"median_price": None})
        assert result["verdict"] == "unknown"

    def test_format_verdict_above(self):
        from brain.price_analyzer import format_supplier_verdict
        ref = {"median_price": 100.0}
        text = format_supplier_verdict("SupplierX", 110.0, ref)
        assert "countering" in text

    def test_format_verdict_below(self):
        from brain.price_analyzer import format_supplier_verdict
        ref = {"median_price": 100.0}
        text = format_supplier_verdict("SupplierY", 90.0, ref)
        assert "countering" not in text


# ── churn_detector ───────────────────────────────────────

class TestChurnDetector:
    def test_on_schedule_low_score(self):
        from brain.churn_detector import get_churn_scores
        customers = [{
            "phone": "+91000", "name": "Regular",
            "purchase_history": [
                {"product": "A", "timestamp": 1000000},
                {"product": "B", "timestamp": 1000000 + 86400 * 7},
                {"product": "C", "timestamp": 1000000 + 86400 * 14},
            ],
        }]
        scores = get_churn_scores(customers, current_time=1000000 + 86400 * 18)
        assert scores[0]["churn_score"] < 50

    def test_lapsed_high_score(self):
        from brain.churn_detector import get_churn_scores
        customers = [{
            "phone": "+91001", "name": "Lapsed",
            "purchase_history": [
                {"product": "A", "timestamp": 1000000},
                {"product": "B", "timestamp": 1000000 + 86400 * 7},
            ],
        }]
        scores = get_churn_scores(customers, current_time=1000000 + 86400 * 30)
        assert scores[0]["churn_score"] >= 70

    def test_detect_at_risk(self):
        from brain.churn_detector import detect_at_risk_customers
        day = 86400
        now = time.time()
        customers = [{
            "id": "c1", "name": "Frequent",
            "purchase_history": [
                {"timestamp": now - 20 * day},
                {"timestamp": now - 16 * day},
                {"timestamp": now - 12 * day},
            ],
        }]
        events = detect_at_risk_customers(customers, current_time=now)
        assert len(events) == 1
        assert events[0]["type"] == "churn_risk"

    def test_insufficient_data_skipped(self):
        from brain.churn_detector import get_churn_scores
        customers = [{"phone": "x", "name": "New", "purchase_history": [{"timestamp": 1000}]}]
        assert get_churn_scores(customers) == []


# ── seasonal_detector ────────────────────────────────────

class TestSeasonalDetector:
    def test_detects_april_spike(self):
        from brain.seasonal_detector import detect_seasonal_spikes
        orders = [
            {"date": "2025-01-15", "product_name": "Mango Pulp", "quantity": 10},
            {"date": "2025-02-15", "product_name": "Mango Pulp", "quantity": 12},
            {"date": "2025-03-15", "product_name": "Mango Pulp", "quantity": 15},
            {"date": "2025-04-10", "product_name": "Mango Pulp", "quantity": 100},
            {"date": "2025-04-20", "product_name": "Mango Pulp", "quantity": 120},
            {"date": "2025-05-15", "product_name": "Mango Pulp", "quantity": 10},
        ]
        events = detect_seasonal_spikes(date(2026, 2, 20), orders)
        assert len(events) == 1
        assert events[0]["type"] == "seasonal_preempt"
        assert events[0]["data"]["product_name"] == "Mango Pulp"

    def test_no_spike(self):
        from brain.seasonal_detector import detect_seasonal_spikes
        orders = [
            {"date": "2025-01-15", "product_name": "Rice", "quantity": 50},
            {"date": "2025-04-15", "product_name": "Rice", "quantity": 55},
        ]
        events = detect_seasonal_spikes(date(2026, 2, 20), orders)
        assert events == []

    def test_empty_orders(self):
        from brain.seasonal_detector import detect_seasonal_spikes
        assert detect_seasonal_spikes(date(2026, 1, 1), []) == []
