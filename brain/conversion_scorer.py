# brain/conversion_scorer.py
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "brain.db"

def get_template_rankings() -> list[dict]:
    """Queries message_outcomes, groups by template_used, returns ranked performance."""
    if not DB_PATH.exists():
        return []

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT 
                    template_used,
                    COUNT(*) as total_sent,
                    SUM(CASE WHEN converted_at IS NOT NULL THEN 1 ELSE 0 END) as conversions,
                    AVG(CASE WHEN purchase_amount IS NOT NULL THEN purchase_amount END) as avg_basket
                FROM message_outcomes
                GROUP BY template_used
                HAVING total_sent >= 1
                ORDER BY (CAST(conversions AS REAL) / total_sent) DESC
            ''')
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            return []

    rankings = []
    for row in rows:
        template, total, conversions, avg_basket = row
        rate = (conversions / total * 100) if total > 0 else 0
        rankings.append({
            "template": template,
            "total_sent": total,
            "conversions": conversions,
            "conversion_rate": round(rate, 1),
            "avg_basket": round(avg_basket, 0) if avg_basket else 0,
        })

    return rankings

def get_template_context() -> str:
    """Formats template rankings as a string block for injection into the Gemini prompt."""
    rankings = get_template_rankings()
    if not rankings:
        return ""

    lines = ["Top performing message templates this week:"]
    for r in rankings:
        lines.append(
            f"  {r['template']:.<25s} {r['conversion_rate']}% conversion, avg ₹{r['avg_basket']} basket ({r['total_sent']} sends)"
        )

    if rankings:
        lines.append(f"\nPrefer '{rankings[0]['template']}' framing for this customer segment.")

    return "\n".join(lines)
