# runtime/dashboard_api.py
from typing import Optional

def _get_connection():
    from brain.decision_logger import _get_connection as _get_main_conn
    return _get_main_conn()

def add_manual_market_price(product_id: str, source_name: str, price: float, unit: str = "kg") -> dict:
    """Mock API endpoint handler for staff dashboard UI logging competitors."""
    from brain.price_monitor import log_manual_price
    try:
        log_manual_price(product_id, source_name, price, unit)
        return {"status": "success", "message": f"Logged ₹{price}/{unit} for {product_id} from {source_name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def get_product_dashboard_stats(product_id: str) -> dict:
    """Provides a read-only price comparison dashboard view data."""
    from brain.price_monitor import get_market_reference
    market = get_market_reference(product_id)
    
    # Normally fetch last purchase price from history, mock for now
    last_purchase_price = 105.0 if "PROD" not in product_id else None
    
    delta = None
    if market.get("median_price") and last_purchase_price:
        delta = round(((last_purchase_price - market["median_price"]) / market["median_price"]) * 100, 1)

    return {
        "product_id": product_id,
        "market_median": market.get("median_price", "N/A"),
        "market_lowest": market.get("lowest_price", "N/A"),
        "lowest_source": market.get("lowest_source", "N/A"),
        "last_purchase_price": last_purchase_price or "N/A",
        "delta_vs_market": delta,
        "confidence": market.get("confidence", "none")
    }
