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
    conn.execute('''
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id TEXT NOT NULL,
            order_id TEXT NOT NULL,
            expected_date TEXT NOT NULL,
            actual_date TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS quality_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id TEXT NOT NULL,
            order_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS message_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            template_used TEXT NOT NULL,
            sent_at REAL NOT NULL,
            replied_at REAL,
            converted_at REAL,
            purchase_amount REAL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            quantity_change INTEGER NOT NULL,
            movement_type TEXT NOT NULL,
            timestamp REAL NOT NULL,
            order_id TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS product_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL UNIQUE,
            shelf_life_days INTEGER NOT NULL,
            last_restock_date TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS market_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            price_per_unit REAL NOT NULL,
            unit TEXT,
            recorded_at REAL NOT NULL,
            source_type TEXT NOT NULL,
            confidence TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS footfall_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            hour INTEGER NOT NULL,
            customer_count INTEGER NOT NULL,
            transaction_count INTEGER NOT NULL,
            source TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS staff_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id TEXT NOT NULL,
            staff_name TEXT NOT NULL,
            role TEXT NOT NULL,
            shift_date TEXT NOT NULL,
            start_hour INTEGER NOT NULL,
            end_hour INTEGER NOT NULL
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

def log_delivery(supplier_id: str, order_id: str, expected_date: str, actual_date: str):
    """Writes one row to the deliveries table."""
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO deliveries (supplier_id, order_id, expected_date, actual_date, timestamp) VALUES (?, ?, ?, ?, ?)",
            (supplier_id, order_id, expected_date, actual_date, time.time())
        )

def log_quality_flag(supplier_id: str, order_id: str, reason: str):
    """Writes one row to the quality_flags table."""
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO quality_flags (supplier_id, order_id, reason, timestamp) VALUES (?, ?, ?, ?)",
            (supplier_id, order_id, reason, time.time())
        )
