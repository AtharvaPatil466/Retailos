"""ML & Intelligence API routes: demand forecast, dynamic pricing, basket analysis."""

from fastapi import APIRouter, Depends

from auth.dependencies import require_role
from db.models import User

router = APIRouter(prefix="/api/ml", tags=["ml-intelligence"])


@router.get("/forecast/{sku}")
async def get_demand_forecast(
    sku: str,
    horizon: int = 7,
    user: User = Depends(require_role("staff")),
):
    from brain.demand_forecaster import forecast_demand
    return forecast_demand(sku, horizon=horizon)


@router.get("/pricing/{sku}")
async def get_pricing_suggestion(
    sku: str,
    user: User = Depends(require_role("manager")),
):
    from brain.dynamic_pricer import get_price_suggestion
    return get_price_suggestion(sku)


@router.get("/pricing")
async def get_all_pricing_suggestions(
    user: User = Depends(require_role("manager")),
):
    from brain.dynamic_pricer import get_all_price_suggestions
    return {"suggestions": get_all_price_suggestions()}


@router.post("/forecast/advanced")
async def get_advanced_forecast(
    sku: str = "",
    product_name: str = "",
    forecast_days: int = 14,
    user: User = Depends(require_role("manager")),
):
    """Advanced time-series demand forecast with trend and seasonality."""
    import json
    import random
    from pathlib import Path
    from brain.demand_forecast import forecast_demand

    # Try to get real sales data from inventory
    data_dir = Path(__file__).resolve().parent.parent / "data"
    try:
        with open(data_dir / "mock_inventory.json") as f:
            inventory = json.load(f)
    except Exception:
        inventory = []

    product = next((p for p in inventory if p.get("sku") == sku), None)
    name = product_name or (product.get("product_name", sku) if product else sku)
    daily_rate = product.get("daily_sales_rate", 10) if product else 10

    # Simulate historical daily sales with some variance
    daily_sales = [max(0, daily_rate + random.gauss(0, daily_rate * 0.3)) for _ in range(30)]

    return forecast_demand(daily_sales, forecast_days=forecast_days, product_name=name)


@router.post("/forecast/bulk")
async def get_bulk_forecast(
    forecast_days: int = 14,
    user: User = Depends(require_role("manager")),
):
    """Bulk demand forecast for all active products."""
    import json
    import random
    from pathlib import Path
    from brain.demand_forecast import bulk_forecast

    data_dir = Path(__file__).resolve().parent.parent / "data"
    try:
        with open(data_dir / "mock_inventory.json") as f:
            inventory = json.load(f)
    except Exception:
        inventory = []

    products = []
    for item in inventory[:20]:
        rate = item.get("daily_sales_rate", 5)
        daily_sales = [max(0, rate + random.gauss(0, rate * 0.3)) for _ in range(30)]
        products.append({"product_name": item.get("product_name", ""), "daily_sales": daily_sales})

    forecasts = bulk_forecast(products, forecast_days=forecast_days)
    return {"forecasts": forecasts, "count": len(forecasts)}


@router.get("/basket/pairs")
async def get_basket_pairs(
    min_support: int = 2,
    user: User = Depends(require_role("staff")),
):
    from brain.basket_analyzer import compute_co_occurrences
    return {"pairs": compute_co_occurrences(min_support=min_support)}


@router.get("/basket/recommend/{sku}")
async def get_basket_recommendations(
    sku: str,
    top_n: int = 5,
    user: User = Depends(require_role("cashier")),
):
    from brain.basket_analyzer import get_recommendations_for
    return {"sku": sku, "recommendations": get_recommendations_for(sku, top_n=top_n)}
