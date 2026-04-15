from datetime import date

from brain.decision_logger import log_decision, log_delivery, log_quality_flag
from brain.db import get_connection
from brain.seasonal_detector import detect_seasonal_spikes
from brain.trust_scorer import get_trust_score


def test_late_deliveries_reduce_trust_score(isolated_brain_db):
    get_connection().close()

    for index in range(10):
        log_decision("SUP-PERFECT", 100, "approved")
        log_delivery("SUP-PERFECT", f"ord_{index}", "2026-03-01", "2026-03-01")

    for index in range(10):
        log_decision("SUP-LATE", 100, "approved")
        log_delivery("SUP-LATE", f"ord_{index}", "2026-03-01", "2026-03-05")

    assert get_trust_score("SUP-LATE")["score"] < get_trust_score("SUP-PERFECT")["score"]


def test_quality_flags_reduce_trust_score(isolated_brain_db):
    get_connection().close()

    for index in range(10):
        log_decision("SUP-QUAL-1", 100, "approved")
        log_delivery("SUP-QUAL-1", f"ord_q1_{index}", "2026-03-01", "2026-03-01")
    log_quality_flag("SUP-QUAL-1", "ord_q1_0", "Bad packaging")

    for index in range(10):
        log_decision("SUP-QUAL-5", 100, "approved")
        log_delivery("SUP-QUAL-5", f"ord_q5_{index}", "2026-03-01", "2026-03-01")
    for index in range(5):
        log_quality_flag("SUP-QUAL-5", f"ord_q5_{index}", "Moldy")

    assert get_trust_score("SUP-QUAL-1")["score"] > get_trust_score("SUP-QUAL-5")["score"]


def test_seasonal_detector_emits_preempt_event():
    mock_orders = [
        {"date": "2025-01-15", "product_name": "Mango Pulp", "quantity": 10},
        {"date": "2025-02-15", "product_name": "Mango Pulp", "quantity": 12},
        {"date": "2025-03-15", "product_name": "Mango Pulp", "quantity": 15},
        {"date": "2025-04-10", "product_name": "Mango Pulp", "quantity": 100},
        {"date": "2025-04-20", "product_name": "Mango Pulp", "quantity": 120},
        {"date": "2025-05-15", "product_name": "Mango Pulp", "quantity": 10},
    ]

    events = detect_seasonal_spikes(date(2026, 2, 20), mock_orders)

    assert len(events) == 1
    assert events[0]["type"] == "seasonal_preempt"
    assert events[0]["data"]["product_name"] == "Mango Pulp"
