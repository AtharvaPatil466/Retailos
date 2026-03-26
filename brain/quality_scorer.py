# brain/quality_scorer.py
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "brain.db"

def get_quality_score(supplier_id: str) -> int:
    """Calculates quality score (0-100) based on complaints per order."""
    if not DB_PATH.exists():
        return 50

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        try:
            # Getting total orders. We assume deliveries count as fulfilled orders.
            cursor.execute('SELECT COUNT(DISTINCT order_id) FROM deliveries WHERE supplier_id = ?', (supplier_id,))
            total_orders = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM quality_flags WHERE supplier_id = ?', (supplier_id,))
            total_complaints = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            return 50

    # Fallback to sum of decisions if no deliveries registered yet
    if total_orders == 0:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM decisions WHERE supplier_id = ? AND status = 'approved'", (supplier_id,))
            total_orders = cursor.fetchone()[0]
             
    if total_orders == 0:
        return 50

    ratio = total_complaints / total_orders
    
    # Sharp penalty mapping:
    # A 10% complaint ratio is disastrous in retail.
    # 1% complaints = -5 points. 10% complaints = -50 points. >=20% = 0.
    penalty = int(ratio * 500)
    score = max(0, 100 - penalty)
    return score
