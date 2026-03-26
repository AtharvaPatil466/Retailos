# brain/delivery_tracker.py
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "brain.db"

def get_delivery_score(supplier_id: str) -> int:
    """Calculates delivery score (0-100) based on on-time deliveries."""
    if not DB_PATH.exists():
        return 50

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT expected_date, actual_date 
                FROM deliveries 
                WHERE supplier_id = ?
            ''', (supplier_id,))
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            # deliveries table might not exist yet during first boot
            return 50

    if not rows:
        return 50

    on_time = 0
    for expected, actual in rows:
        try:
            # Expected format: "YYYY-MM-DD" or similar ISO Date
            exp_date = datetime.fromisoformat(expected.replace("Z", "+00:00"))
            act_date = datetime.fromisoformat(actual.replace("Z", "+00:00"))
            if act_date <= exp_date + timedelta(days=1):
                on_time += 1
        except ValueError:
            # Fallback for simple string comparisons
            if actual <= expected:
                on_time += 1
            else:
                # very dumb fallback if formats are weird - assume it counts if it's identical
                if actual.startswith(expected):
                    on_time += 1
                
    return int((on_time / len(rows)) * 100)
