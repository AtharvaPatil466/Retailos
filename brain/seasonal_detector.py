# brain/seasonal_detector.py
import datetime

def detect_seasonal_spikes(current_date: datetime.date, historical_orders: list[dict]) -> list[dict]:
    """
    Analyzes historical orders to find seasonal spikes 6-8 weeks from current_date.
    Returns a list of 'seasonal_preempt' events to be emitted to the orchestrator.
    """
    # Target month is roughly 7 weeks ahead
    target_date = current_date + datetime.timedelta(weeks=7)
    target_month = target_date.month

    monthly_volumes = {}
    for order in historical_orders:
        date_str = order.get("date", "")
        if not date_str:
            continue
        try:
            d = datetime.date.fromisoformat(date_str)
        except ValueError:
            continue
            
        product = order.get("product_name")
        qty = order.get("quantity", 0)
        
        if product not in monthly_volumes:
            monthly_volumes[product] = {}
        monthly_volumes[product][d.month] = monthly_volumes[product].get(d.month, 0) + qty

    events = []
    for product, volumes in monthly_volumes.items():
        if target_month not in volumes:
            continue
            
        target_vol = volumes[target_month]
        other_vols = [v for m, v in volumes.items() if m != target_month]
        
        if not other_vols:
            continue
            
        avg_other = sum(other_vols) / len(other_vols)
        
        # Identify a spike if target month volume is > 2x the average of other months
        if target_vol > (avg_other * 2):
            events.append({
                "type": "seasonal_preempt",
                "data": {
                    "product_name": product,
                    "reason": f"Historical data shows a {(target_vol / avg_other):.1f}x volume spike in month {target_month}.",
                    "target_month": target_month,
                    "expected_increase": target_vol - avg_other
                }
            })
            
    return events
