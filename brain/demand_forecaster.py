"""Time-series demand forecasting using exponential smoothing.

Replaces simple velocity with trend-aware prediction.
"""

import json
import time
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_orders():
    try:
        with open(DATA_DIR / "mock_orders.json") as f:
            return json.load(f).get("customer_orders", [])
    except Exception:
        return []


def get_daily_sales_history(sku: str, days: int = 30) -> list[float]:
    """Build a daily sales time series for a given SKU over the last N days."""
    orders = _load_orders()
    now = time.time()
    cutoff = now - (days * 86400)

    # Initialize daily buckets
    daily = [0.0] * days

    for order in orders:
        ts = order.get("timestamp", 0)
        if ts < cutoff:
            continue
        day_index = int((ts - cutoff) / 86400)
        if 0 <= day_index < days:
            for item in order.get("items", []):
                if item.get("sku") == sku:
                    daily[day_index] += item.get("qty", 1)

    return daily


def exponential_smoothing_forecast(series: list[float], alpha: float = 0.3, horizon: int = 7) -> dict:
    """Simple exponential smoothing with trend detection.

    Returns forecast for the next `horizon` days plus trend direction.
    """
    if not series or len(series) < 3:
        avg = sum(series) / len(series) if series else 0
        return {
            "forecast": [round(avg, 1)] * horizon,
            "trend": "insufficient_data",
            "confidence": "low",
            "avg_daily": round(avg, 1),
        }

    # Exponential smoothing
    smoothed = [series[0]]
    for i in range(1, len(series)):
        smoothed.append(alpha * series[i] + (1 - alpha) * smoothed[-1])

    last_smoothed = smoothed[-1]

    # Double exponential smoothing for trend
    beta = 0.2
    level = smoothed[-1]
    trend_val = (smoothed[-1] - smoothed[-2]) if len(smoothed) >= 2 else 0

    forecast = []
    for h in range(1, horizon + 1):
        forecast.append(max(0, round(level + h * trend_val, 1)))

    # Detect trend
    first_half = sum(series[: len(series) // 2]) / max(1, len(series) // 2)
    second_half = sum(series[len(series) // 2 :]) / max(1, len(series) - len(series) // 2)

    if second_half > first_half * 1.15:
        trend = "increasing"
    elif second_half < first_half * 0.85:
        trend = "decreasing"
    else:
        trend = "stable"

    # Confidence based on variance
    avg = sum(series) / len(series)
    variance = sum((x - avg) ** 2 for x in series) / len(series)
    cv = (variance ** 0.5) / avg if avg > 0 else 1
    confidence = "high" if cv < 0.3 else "medium" if cv < 0.6 else "low"

    return {
        "forecast": forecast,
        "trend": trend,
        "confidence": confidence,
        "avg_daily": round(avg, 1),
        "smoothed_current": round(last_smoothed, 1),
    }


def forecast_demand(sku: str, horizon: int = 7) -> dict:
    """Full demand forecast for a product."""
    history = get_daily_sales_history(sku, days=30)
    result = exponential_smoothing_forecast(history, horizon=horizon)
    result["sku"] = sku
    result["history_days"] = len(history)
    result["total_sold_30d"] = sum(history)
    return result
