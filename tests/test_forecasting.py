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
    result = exponential_smoothing(series, alpha=0.3)
    assert len(result) == len(series)
    assert all(isinstance(v, (int, float)) for v in result)
    # Smoothed values should be in a reasonable range
    assert all(8 < v < 20 for v in result)


def test_exponential_smoothing_constant_series():
    series = [10.0] * 10
    result = exponential_smoothing(series, alpha=0.5)
    for v in result:
        assert abs(v - 10.0) < 0.01


def test_double_exponential_smoothing_trending():
    series = [10, 12, 14, 16, 18, 20, 22, 24]
    smoothed, level, trend = double_exponential_smoothing(series, alpha=0.5, beta=0.3)
    assert len(smoothed) == len(series)
    # Should detect upward trend
    assert trend > 0
    assert level > 20


def test_detect_seasonality_weekly():
    # 3 weeks of daily data with weekly pattern
    weekly = [10, 8, 9, 12, 15, 20, 18] * 3
    result = detect_seasonality(weekly)
    assert isinstance(result, list)
    assert len(result) == 7
    # Peak should be Saturday (index 5, value 20)
    assert result.index(max(result)) == 5


def test_detect_seasonality_none():
    random_ish = [10, 11, 10, 9, 10, 11, 10, 9, 10, 10]
    result = detect_seasonality(random_ish)
    assert isinstance(result, list)
    # Flat data should have seasonal factors close to 1.0
    assert all(isinstance(v, (int, float)) for v in result)


def test_forecast_demand_full():
    sales_history = [5, 6, 7, 8, 7, 6, 5, 6, 7, 8, 9, 8, 7, 6]
    result = forecast_demand(
        daily_sales=sales_history,
        forecast_days=7,
        product_name="TEST-SKU",
    )
    assert result["product_name"] == "TEST-SKU"
    assert result["status"] == "ok"
    assert len(result["forecast"]) == 7
    assert result["trend"]["direction"] in ("increasing", "decreasing", "stable")
    # Each forecast entry should have confidence bounds
    for f in result["forecast"]:
        assert "lower_bound" in f
        assert "upper_bound" in f


def test_forecast_demand_insufficient_data():
    result = forecast_demand(daily_sales=[], product_name="SHORT")
    assert result["status"] == "insufficient_data"


def test_forecast_demand_with_reorder():
    sales_history = [10, 12, 11, 13, 12, 14, 13, 15, 14, 16]
    result = forecast_demand(
        daily_sales=sales_history,
        forecast_days=7,
        product_name="REORDER-SKU",
    )
    assert "summary" in result
    assert "recommended_reorder_qty" in result["summary"]
    assert result["summary"]["recommended_reorder_qty"] > 0


def test_bulk_forecast():
    products = [
        {"product_name": "SKU-A", "daily_sales": [5, 6, 7, 8, 7, 6, 5, 6, 7, 8]},
        {"product_name": "SKU-B", "daily_sales": [20, 22, 21, 23, 22, 24, 23, 25, 24, 26]},
    ]
    results = bulk_forecast(products, forecast_days=5)
    assert len(results) == 2
    assert results[0]["product_name"] in ("SKU-A", "SKU-B")
    assert results[1]["product_name"] in ("SKU-A", "SKU-B")
    assert len(results[0]["forecast"]) == 5
