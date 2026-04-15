import time

from brain.conversion_scorer import get_template_context, get_template_rankings
from brain.db import get_connection
from brain.churn_detector import get_churn_scores
from brain.message_tracker import log_conversion, log_message_sent


def test_template_rankings_prioritize_conversion_rate(isolated_brain_db):
    get_connection().close()

    for index in range(5):
        message_id = f"msg_A_{index}"
        log_message_sent("cust1", message_id, "Template A")
        if index < 4:
            log_conversion("cust1", message_id, 100)

    for index in range(10):
        message_id = f"msg_B_{index}"
        log_message_sent("cust2", message_id, "Template B")
        if index < 2:
            log_conversion("cust2", message_id, 50)

    rankings = get_template_rankings()

    assert rankings[0]["template"] == "Template A"
    assert rankings[1]["template"] == "Template B"


def test_churn_detection_thresholds():
    current_time = time.time()
    day = 86400

    frequent_buyer = {
        "id": "c1",
        "name": "Frequent Buyer",
        "purchase_history": [
            {"timestamp": current_time - 20 * day},
            {"timestamp": current_time - 16 * day},
            {"timestamp": current_time - 12 * day},
        ],
    }
    monthly_buyer = {
        "id": "c2",
        "name": "Monthly Buyer",
        "purchase_history": [
            {"timestamp": current_time - 72 * day},
            {"timestamp": current_time - 42 * day},
            {"timestamp": current_time - 12 * day},
        ],
    }

    scores = get_churn_scores([frequent_buyer, monthly_buyer], current_time=current_time)
    frequent = next(score for score in scores if score["customer_id"] == "c1")
    monthly = next(score for score in scores if score["customer_id"] == "c2")

    assert frequent["churn_score"] >= 70
    assert monthly["churn_score"] < 70


def test_template_context_contains_top_performer(isolated_brain_db):
    get_connection().close()
    log_message_sent("cust1", "msg_1", "Template A")
    log_conversion("cust1", "msg_1", 120)

    context = get_template_context()

    assert "Top performing message templates" in context
    assert "Template A" in context
