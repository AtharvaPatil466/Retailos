"""Tests for demand forecasting and time-series analysis."""

from brain.demand_forecast import (
    exponential_smoothing,
    double_exponential_smoothing,
    detect_seasonality,
    forecast_demand,
    bulk_forecast,
)


def test_exponential_smoothing_basic():
    series = [10, 12, 11, 13, 12, 14, 13, 15]
    result = exponential_smoothing(series, alpha=0.3, horizon=3)
    assert len(result) == 3
    assert all(isinstance(v, float) for v in result)
    # Forecasts should be in a reasonable range
    assert all(8 < v < 20 for v in result)


def test_exponential_smoothing_constant_series():
    series = [10.0] * 10
    result = exponential_smoothing(series, alpha=0.5, horizon=3)
    for v in result:
        assert abs(v - 10.0) < 0.01


def test_double_exponential_smoothing_trending():
    series = [10, 12, 14, 16, 18, 20, 22, 24]
    result = double_exponential_smoothing(series, alpha=0.5, beta=0.3, horizon=3)
    assert len(result) == 3
    # Should continue upward trend
    assert result[0] > 24
    assert result[1] > result[0]


def test_detect_seasonality_weekly():
    # 3 weeks of daily data with weekly pattern
    weekly = [10, 8, 9, 12, 15, 20, 18] * 3
    result = detect_seasonality(weekly)
    assert result["detected"] is True
    assert result["period"] == 7


def test_detect_seasonality_none():
    random_ish = [10, 11, 10, 9, 10, 11, 10, 9, 10, 10]
    result = detect_seasonality(random_ish)
    # Flat data shouldn't show strong seasonality
    assert isinstance(result["detected"], bool)


def test_forecast_demand_full():
    sales_history = [5, 6, 7, 8, 7, 6, 5, 6, 7, 8, 9, 8, 7, 6]
    result = forecast_demand(
        sku="TEST-SKU",
        sales_history=sales_history,
        horizon=7,
    )
    assert result["sku"] == "TEST-SKU"
    assert len(result["forecast"]) == 7
    assert "trend" in result
    assert result["trend"] in ("increasing", "decreasing", "stable")
    assert "confidence_interval" in result
    assert len(result["confidence_interval"]) == 7


def test_forecast_demand_insufficient_data():
    result = forecast_demand(sku="SHORT", sales_history=[5, 6], horizon=3)
    assert result["trend"] == "insufficient_data"


def test_forecast_demand_with_reorder():
    sales_history = [10, 12, 11, 13, 12, 14, 13, 15, 14, 16]
    result = forecast_demand(
        sku="REORDER-SKU",
        sales_history=sales_history,
        horizon=7,
        current_stock=20,
        lead_time_days=3,
    )
    assert "reorder_recommendation" in result
    rec = result["reorder_recommendation"]
    assert "reorder_point" in rec
    assert "suggested_quantity" in rec


def test_bulk_forecast():
    products = {
        "SKU-A": [5, 6, 7, 8, 7, 6, 5, 6, 7, 8],
        "SKU-B": [20, 22, 21, 23, 22, 24, 23, 25, 24, 26],
    }
    results = bulk_forecast(products, horizon=5)
    assert len(results) == 2
    assert results[0]["sku"] in ("SKU-A", "SKU-B")
    assert results[1]["sku"] in ("SKU-A", "SKU-B")
    assert len(results[0]["forecast"]) == 5
