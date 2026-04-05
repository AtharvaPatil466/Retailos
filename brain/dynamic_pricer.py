"""Dynamic pricing engine.

Suggests price adjustments based on demand, inventory levels, expiry, and competition.
"""

import json
from pathlib import Path

from brain.demand_forecaster import forecast_demand
from brain.price_monitor import get_market_reference

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_inventory():
    try:
        with open(DATA_DIR / "mock_inventory.json") as f:
            return json.load(f)
    except Exception:
        return []


def get_price_suggestion(sku: str) -> dict:
    """Compute a dynamic price suggestion for a product."""
    inventory = _load_inventory()
    item = next((i for i in inventory if i["sku"] == sku), None)
    if not item:
        return {"error": f"SKU {sku} not found"}

    current_price = item.get("unit_price", 0)
    stock = item.get("current_stock", 0)
    threshold = item.get("reorder_threshold", 0)
    daily_rate = item.get("daily_sales_rate", 0)

    # Get demand forecast
    forecast = forecast_demand(sku, horizon=7)
    trend = forecast.get("trend", "stable")

    # Get market reference
    market = get_market_reference(sku)
    market_median = market.get("median_price")

    # Decision factors
    factors = []
    adjustment_pct = 0.0

    # Factor 1: Demand trend
    if trend == "increasing":
        adjustment_pct += 5.0
        factors.append({"factor": "demand_rising", "impact": "+5%", "detail": "Sales trending up over 30 days"})
    elif trend == "decreasing":
        adjustment_pct -= 5.0
        factors.append({"factor": "demand_falling", "impact": "-5%", "detail": "Sales trending down over 30 days"})

    # Factor 2: Overstock (> 3x threshold means overstocked)
    if threshold > 0 and stock > threshold * 3:
        adjustment_pct -= 8.0
        factors.append({"factor": "overstock", "impact": "-8%", "detail": f"Stock ({stock}) is 3x above threshold ({threshold})"})
    elif threshold > 0 and stock < threshold:
        adjustment_pct += 3.0
        factors.append({"factor": "low_stock", "impact": "+3%", "detail": f"Stock ({stock}) below threshold ({threshold})"})

    # Factor 3: Days until stockout
    if daily_rate > 0:
        days_left = stock / daily_rate
        if days_left < 3:
            adjustment_pct += 5.0
            factors.append({"factor": "near_stockout", "impact": "+5%", "detail": f"Only {days_left:.1f} days of stock left"})

    # Factor 4: Market competitiveness
    if market_median and current_price > market_median * 1.15:
        adjustment_pct -= 5.0
        factors.append({"factor": "above_market", "impact": "-5%", "detail": f"Current ₹{current_price} > market median ₹{market_median}"})
    elif market_median and current_price < market_median * 0.85:
        adjustment_pct += 3.0
        factors.append({"factor": "below_market", "impact": "+3%", "detail": f"Current ₹{current_price} < market median ₹{market_median}"})

    # Calculate suggested price
    suggested_price = round(current_price * (1 + adjustment_pct / 100), 2)

    # Clamp: never go below cost (assume cost = 60% of current price as estimate)
    min_price = current_price * 0.6
    suggested_price = max(suggested_price, min_price)

    return {
        "sku": sku,
        "product_name": item.get("product_name", ""),
        "current_price": current_price,
        "suggested_price": suggested_price,
        "adjustment_pct": round(adjustment_pct, 1),
        "factors": factors,
        "demand_trend": trend,
        "market_median": market_median,
        "confidence": forecast.get("confidence", "low"),
    }


def get_all_price_suggestions() -> list[dict]:
    """Get price suggestions for all products."""
    inventory = _load_inventory()
    suggestions = []
    for item in inventory:
        suggestion = get_price_suggestion(item["sku"])
        if "error" not in suggestion and suggestion.get("adjustment_pct", 0) != 0:
            suggestions.append(suggestion)
    suggestions.sort(key=lambda x: abs(x.get("adjustment_pct", 0)), reverse=True)
    return suggestions
