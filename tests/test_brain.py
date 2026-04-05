"""Integration tests for brain modules."""

from brain.churn_detector import get_churn_scores
from brain.demand_forecaster import exponential_smoothing_forecast
from brain.basket_analyzer import compute_co_occurrences
from brain.dynamic_pricer import get_price_suggestion


def test_churn_detector_on_schedule():
    customers = [
        {
            "phone": "+91000",
            "name": "Test",
            "purchase_history": [
                {"product": "A", "timestamp": 1000000},
                {"product": "B", "timestamp": 1000000 + 86400 * 7},
                {"product": "C", "timestamp": 1000000 + 86400 * 14},
            ],
        }
    ]
    # Set current_time to right after last purchase (on schedule)
    scores = get_churn_scores(customers, current_time=1000000 + 86400 * 18)
    assert len(scores) == 1
    assert scores[0]["churn_score"] < 50  # Not yet at risk


def test_churn_detector_at_risk():
    customers = [
        {
            "phone": "+91001",
            "name": "Lapsed",
            "purchase_history": [
                {"product": "A", "timestamp": 1000000},
                {"product": "B", "timestamp": 1000000 + 86400 * 7},
            ],
        }
    ]
    # Set current_time to way past their usual gap (3x)
    scores = get_churn_scores(customers, current_time=1000000 + 86400 * 30)
    assert len(scores) == 1
    assert scores[0]["churn_score"] >= 70


def test_exponential_smoothing_stable():
    series = [10, 11, 10, 9, 10, 11, 10, 10, 10, 10]
    result = exponential_smoothing_forecast(series, horizon=3)
    assert result["trend"] == "stable"
    assert len(result["forecast"]) == 3
    assert all(f > 0 for f in result["forecast"])


def test_exponential_smoothing_increasing():
    series = [5, 6, 7, 8, 9, 10, 12, 14, 16, 18]
    result = exponential_smoothing_forecast(series, horizon=3)
    assert result["trend"] == "increasing"


def test_exponential_smoothing_insufficient_data():
    result = exponential_smoothing_forecast([5], horizon=3)
    assert result["trend"] == "insufficient_data"
    assert result["confidence"] == "low"


def test_basket_analysis_runs():
    pairs = compute_co_occurrences(min_support=1)
    assert isinstance(pairs, list)


def test_price_suggestion_missing_sku():
    result = get_price_suggestion("NONEXISTENT-SKU")
    assert "error" in result
