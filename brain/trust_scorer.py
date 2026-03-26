# brain/trust_scorer.py
import sqlite3
from pathlib import Path

from brain.delivery_tracker import get_delivery_score
from brain.quality_scorer import get_quality_score

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "brain.db"

def get_trust_score(supplier_id: str) -> dict:
    """Reads from the table and returns a score dict for any supplier. Pure SQL + math, no AI."""
    if not DB_PATH.exists():
        return {"score": 50, "is_new": True, "breakdown": {}}

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
    
    approval_score = int((approved / total) * 100) if total > 0 else 50
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT amount FROM decisions 
            WHERE supplier_id = ? AND status = 'approved'
        ''', (supplier_id,))
        amounts = [r[0] for r in cursor.fetchall()]
        
    if len(amounts) > 1:
        mean = sum(amounts) / len(amounts)
        variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
        std_dev = variance ** 0.5
        coef_var = (std_dev / mean) if mean > 0 else 0
        price_consistency_score = max(0, 100 - int(coef_var * 200)) # e.g. 50% variance => 0 score
    else:
        price_consistency_score = 50
        
    delivery_score = get_delivery_score(supplier_id)
    quality_score = get_quality_score(supplier_id)
    
    final_score = int(
        approval_score * 0.40 +
        delivery_score * 0.30 +
        quality_score * 0.20 +
        price_consistency_score * 0.10
    )
    
    return {
        "score": final_score, 
        "is_new": total == 0,
        "breakdown": {
            "approval": approval_score,
            "delivery": delivery_score,
            "quality": quality_score,
            "price_consistency": price_consistency_score
        }
    }
