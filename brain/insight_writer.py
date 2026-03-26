# brain/insight_writer.py
import sqlite3
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "brain.db"

async def write_daily_insight(memory):
    """Called by analytics at end of day. Spots patterns and writes to memory."""
    if not DB_PATH.exists():
        return
        
    twenty_four_hours_ago = time.time() - (24 * 3600)
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT supplier_id, status, count(*) 
            FROM decisions 
            WHERE timestamp >= ?
            GROUP BY supplier_id, status
        ''', (twenty_four_hours_ago,))
        
        rows = cursor.fetchall()
        
    if not rows:
        return
        
    insights = []
    for row in rows:
        supplier_id, status, count = row
        if status == 'rejected' and count >= 2:
            insights.append(f"Supplier {supplier_id} had {count} rejected deals today (trust score likely dropping).")
        elif status == 'approved' and count >= 3:
            insights.append(f"Supplier {supplier_id} had {count} approved deals today (highly reliable).")
            
    if not insights:
        insights.append(f"Processed {len(rows)} decision entries today with no major anomalies.")
        
    insight_string = " | ".join(insights)
    
    # Read current summary and append
    summary = await memory.get("orchestrator:daily_summary")
    if summary:
        if "insights" not in summary:
            summary["insights"] = []
            
        summary["insights"].append({
            "type": "trust_pattern",
            "title": "Daily Trust & Approval Insights",
            "detail": insight_string,
            "recommendation": "Use these patterns in future procurement/negotiation.",
            "severity": "info"
        })
        await memory.set("orchestrator:daily_summary", summary)
