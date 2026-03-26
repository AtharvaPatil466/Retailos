# brain/reorder_optimizer.py
from brain.wastage_tracker import get_wastage_summary

def get_optimized_reorder_quantity(product_id: str, avg_daily_sales: float, lead_time_days: int = 7) -> dict:
    summary = get_wastage_summary(product_id)
    wastage_rate = summary.get("wastage_rate", 0.0)
    
    # Base calculation based on expected sales
    base_quantity = avg_daily_sales * lead_time_days
    
    # Optimization logic: optimal_quantity = (avg_daily_sales × lead_time_days) × (1 - wastage_rate)
    # The idea is if 20% expires, you are ordering 20% too much. So reduce the order by 20%.
    optimal_quantity = base_quantity * (1 - wastage_rate)
    
    return {
        "base_quantity": max(1, int(base_quantity)),
        "optimized_quantity": max(1, int(optimal_quantity)),
        "wastage_rate": round(wastage_rate, 3),
        "lead_time_days": lead_time_days,
        "avg_daily_sales": avg_daily_sales
    }
