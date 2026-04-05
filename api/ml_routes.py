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
