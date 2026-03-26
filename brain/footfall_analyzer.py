# brain/footfall_analyzer.py
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "brain.db"

def _get_connection():
    from brain.decision_logger import _get_connection as _get_main_conn
    return _get_main_conn()

def log_footfall(process_date: str, hour: int, customer_count: int, transaction_count: int, source: str = "pos_proxy"):
    """Captures hourly footfall entries into the database."""
    with _get_connection() as conn:
        conn.execute(
            """INSERT INTO footfall_logs (date, hour, customer_count, transaction_count, source)
               VALUES (?, ?, ?, ?, ?)""",
            (process_date, hour, customer_count, transaction_count, source)
        )

def get_footfall_pattern(day_of_week: int) -> dict:
    """Returns predictive customer load per hour based on historical day_of_week averages (0=Monday, 6=Sunday)."""
    if not DB_PATH.exists():
        return {h: 0.0 for h in range(24)}

    hourly_averages = {h: 0.0 for h in range(24)}
    
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT date, hour, customer_count FROM footfall_logs")
        rows = cursor.fetchall()
        
        hour_buckets = {h: [] for h in range(24)}
        for row in rows:
            row_date_str = row[0]
            try:
                row_date = datetime.strptime(row_date_str, "%Y-%m-%d").date()
                if row_date.weekday() == day_of_week:
                    hour_buckets[row[1]].append(row[2])
            except ValueError:
                pass
                
        for h, counts in hour_buckets.items():
            if counts:
                hourly_averages[h] = sum(counts) / len(counts)
                
    return hourly_averages

def get_total_predicted_footfall(day_of_week: int) -> int:
    pattern = get_footfall_pattern(day_of_week)
    return int(sum(pattern.values()))
