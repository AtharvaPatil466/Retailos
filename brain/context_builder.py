# brain/context_builder.py
import sqlite3
from pathlib import Path
from .trust_scorer import get_trust_score

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "brain.db"

def get_supplier_context(supplier_id: str) -> str:
    """Fetches trust score and last 5 decisions, formats as short paragraph for Gemini."""
    trust_data = get_trust_score(supplier_id)
    score = trust_data["score"]
    
    if trust_data["is_new"] or not DB_PATH.exists():
        return f"Trust Score: {score}/100 (Low Confidence - Brand New Supplier). No history available."

    history_text = []
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT amount, status
            FROM decisions 
            WHERE supplier_id = ?
            ORDER BY timestamp DESC
            LIMIT 5
        ''', (supplier_id,))
        
        rows = cursor.fetchall()
        
    if not rows:
        return f"Trust Score: {score}/100 (Low Confidence - Brand New Supplier). No history available."
        
    for row in rows:
        amount, status = row
        history_text.append(f"₹{amount} deal was {status}")
        
    history_joined = ", ".join(history_text)
    return f"Trust Score: {score}/100. Last 5 interactions: {history_joined}."
