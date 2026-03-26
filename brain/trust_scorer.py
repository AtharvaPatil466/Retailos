# brain/trust_scorer.py
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "brain.db"

def get_trust_score(supplier_id: str) -> dict:
    """Reads from the table and returns a score dict for any supplier. Pure SQL + math, no AI."""
    if not DB_PATH.exists():
        return {"score": 50, "is_new": True}

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved
            FROM decisions 
            WHERE supplier_id = ?
        ''', (supplier_id,))
        
        row = cursor.fetchone()
        
    total = row[0]
    approved = row[1] if row[1] is not None else 0
    
    if total == 0:
        return {"score": 50, "is_new": True}
        
    return {"score": int((approved / total) * 100), "is_new": False}
