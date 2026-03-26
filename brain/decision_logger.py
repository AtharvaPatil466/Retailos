# brain/decision_logger.py
import sqlite3
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "brain.db"

def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
    ''')
    return conn

def log_decision(supplier_id: str, amount: float, status: str):
    """Writes one row to the decisions table."""
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO decisions (supplier_id, amount, status, timestamp) VALUES (?, ?, ?, ?)",
            (supplier_id, amount, status, time.time())
        )
