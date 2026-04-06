"""Time-series demand forecasting for inventory planning.

Uses exponential smoothing and trend decomposition to predict
future demand for products. Works with historical sales data
to generate forecasts with confidence intervals.

No external ML libraries required — pure Python implementation.
"""

import math
import statistics
from typing import Any


def exponential_smoothing(series: list[float], alpha: float = 0.3) -> list[float]:
    """Simple exponential smoothing."""
    if not series:
        return []
    result = [series[0]]
    for i in range(1, len(series)):
        result.append(alpha * series[i] + (1 - alpha) * result[-1])
    return result


def double_exponential_smoothing(
    series: list[float],
    alpha: float = 0.3,
    beta: float = 0.1,
) -> tuple[list[float], float, float]:
    """Holt's double exponential smoothing for trend detection.

    Returns: (smoothed_values, final_level, final_trend)
    """
    if len(series) < 2:
        return series, series[0] if series else 0, 0

    level = series[0]
    trend = series[1] - series[0]
    smoothed = [level]

    for i in range(1, len(series)):
        prev_level = level
        level = alpha * series[i] + (1 - alpha) * (prev_level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        smoothed.append(level + trend)

    return smoothed, level, trend


def detect_seasonality(series: list[float], period: int = 7) -> list[float]:
    """Detect weekly seasonality pattern (7-day cycle).

    Returns seasonal indices (multiplicative).
    """
    if len(series) < period * 2:
        return [1.0] * period

    # Calculate average for each position in the cycle
    seasonal = [0.0] * period
    counts = [0] * period
    overall_mean = statistics.mean(series) if series else 1

    for i, val in enumerate(series):
        pos = i % period
        seasonal[pos] += val
        counts[pos] += 1

    for i in range(period):
        if counts[i] > 0:
            seasonal[i] = (seasonal[i] / counts[i]) / overall_mean if overall_mean > 0 else 1.0
        else:
            seasonal[i] = 1.0

    return seasonal


def forecast_demand(
    daily_sales: list[float],
    forecast_days: int = 14,
    product_name: str = "",
) -> dict[str, Any]:
    """Generate demand forecast with confidence intervals.

    Args:
        daily_sales: Historical daily sales quantities (most recent last)
        forecast_days: Number of days to forecast
        product_name: Product name for the report

    Returns:
        Forecast with daily predictions, trend, seasonality, and confidence.
    """
    if not daily_sales:
        return {
            "product_name": product_name,
            "status": "insufficient_data",
            "message": "No historical sales data available",
            "forecast": [],
        }

    n = len(daily_sales)

    # Basic stats
    avg_daily = statistics.mean(daily_sales)
    std_daily = statistics.stdev(daily_sales) if n > 1 else 0

    # Trend analysis with double exponential smoothing
    smoothed, level, trend = double_exponential_smoothing(daily_sales)

    # Seasonality detection (7-day weekly pattern)
    seasonal = detect_seasonality(daily_sales, period=7)

    # Generate forecast
    forecast = []
    for i in range(forecast_days):
        # Base prediction from trend
        base = level + trend * (i + 1)

        # Apply seasonality
        season_idx = (n + i) % 7
        seasonal_factor = seasonal[season_idx]
        predicted = max(0, base * seasonal_factor)

        # Confidence interval (widens with forecast horizon)
        uncertainty = std_daily * math.sqrt(1 + i * 0.1)
        lower = max(0, predicted - 1.96 * uncertainty)
        upper = predicted + 1.96 * uncertainty

        forecast.append({
            "day": i + 1,
            "predicted_qty": round(predicted, 1),
            "lower_bound": round(lower, 1),
            "upper_bound": round(upper, 1),
            "confidence": round(max(0.5, 1 - (i * 0.02)), 2),
            "seasonal_factor": round(seasonal_factor, 3),
        })

    # Trend classification
    if n >= 7:
        recent_avg = statistics.mean(daily_sales[-7:])
        older_avg = statistics.mean(daily_sales[:min(7, n)])
        trend_pct = ((recent_avg - older_avg) / older_avg * 100) if older_avg > 0 else 0
    else:
        trend_pct = trend / avg_daily * 100 if avg_daily > 0 else 0

    if trend_pct > 10:
        trend_label = "increasing"
    elif trend_pct < -10:
        trend_label = "decreasing"
    else:
        trend_label = "stable"

    # Reorder recommendation
    total_forecast = sum(f["predicted_qty"] for f in forecast)
    weekly_forecast = sum(f["predicted_qty"] for f in forecast[:7])

    return {
        "product_name": product_name,
        "status": "ok",
        "data_points": n,
        "avg_daily_sales": round(avg_daily, 1),
        "std_daily_sales": round(std_daily, 1),
        "trend": {
            "direction": trend_label,
            "daily_change": round(trend, 2),
            "pct_change": round(trend_pct, 1),
        },
        "seasonality": {
            "detected": any(abs(s - 1.0) > 0.1 for s in seasonal),
            "pattern": {
                "monday": round(seasonal[0], 3),
                "tuesday": round(seasonal[1], 3),
                "wednesday": round(seasonal[2], 3),
                "thursday": round(seasonal[3], 3),
                "friday": round(seasonal[4], 3),
                "saturday": round(seasonal[5], 3),
                "sunday": round(seasonal[6], 3),
            },
            "peak_day": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][seasonal.index(max(seasonal))],
            "low_day": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][seasonal.index(min(seasonal))],
        },
        "forecast": forecast,
        "summary": {
            "next_7_days": round(weekly_forecast, 1),
            "next_14_days": round(total_forecast, 1),
            "recommended_reorder_qty": round(weekly_forecast * 1.2, 0),  # 20% safety buffer
        },
    }


def bulk_forecast(products: list[dict], forecast_days: int = 14) -> list[dict]:
    """Forecast demand for multiple products.

    Each product dict should have 'product_name' and 'daily_sales' (list of floats).
    """
    results = []
    for product in products:
        result = forecast_demand(
            daily_sales=product.get("daily_sales", []),
            forecast_days=forecast_days,
            product_name=product.get("product_name", "Unknown"),
        )
        results.append(result)
    return results
