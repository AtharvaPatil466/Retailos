# brain/wastage_tracker.py
import sqlite3
import time
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "brain.db"

def _get_connection():
    from brain.decision_logger import _get_connection as _get_main_conn
    return _get_main_conn()

def log_movement(product_id: str, quantity: int, movement_type: str, order_id: Optional[str] = None):
    """
    Records a stock movement.
    movement_type must be one of: 'sale', 'expiry', 'damage', 'theft', 'restock'
    quantity should be positive for 'restock', negative for others.
    """
    valid_types = {'sale', 'expiry', 'damage', 'theft', 'restock'}
    if movement_type not in valid_types:
        raise ValueError(f"Invalid movement_type: {movement_type}")
        
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO stock_movements (product_id, quantity_change, movement_type, timestamp, order_id) VALUES (?, ?, ?, ?, ?)",
            (product_id, quantity, movement_type, time.time(), order_id)
        )

def get_wastage_summary(product_id: str, days: int = 30) -> dict:
    """
    Calculates the ratio of lost units (expiry + damage + theft) to 
    total units received (restock) over the given time window.
    """
    if not DB_PATH.exists():
        return {"wastage_rate": 0.0, "total_lost": 0, "total_received": 0}

    now = time.time()
    cutoff = now - (days * 86400)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Get total lost
        cursor.execute('''
            SELECT SUM(quantity_change) 
            FROM stock_movements 
            WHERE product_id = ? 
            AND movement_type IN ('expiry', 'damage', 'theft')
            AND timestamp >= ?
        ''', (product_id, cutoff))
        lost_row = cursor.fetchone()
        total_lost = abs(lost_row[0] or 0)
        
        # Get total received (restocks) + starting balance heuristic
        cursor.execute('''
            SELECT SUM(quantity_change) 
            FROM stock_movements 
            WHERE product_id = ? 
            AND movement_type = 'restock'
            AND timestamp >= ?
        ''', (product_id, cutoff))
        received_row = cursor.fetchone()
        total_received = abs(received_row[0] or 0)
        
        # If no restocks recorded in window, use total sales + total lost as a denominator proxy
        if total_received == 0:
            cursor.execute('''
                SELECT SUM(quantity_change) 
                FROM stock_movements 
                WHERE product_id = ? 
                AND movement_type = 'sale'
                AND timestamp >= ?
            ''', (product_id, cutoff))
            sales_row = cursor.fetchone()
            total_sales = abs(sales_row[0] or 0)
            total_received = total_sales + total_lost

        rate = (total_lost / total_received) if total_received > 0 else 0.0

        return {
            "wastage_rate": min(1.0, round(rate, 3)),
            "total_lost": total_lost,
            "total_received": total_received
        }
