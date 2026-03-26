# brain/auto_approver.py
from .config import TRUST_THRESHOLD, AMOUNT_CEILING
from .trust_scorer import get_trust_score

def should_auto_approve(supplier_id: str, amount: float) -> bool:
    """If trust score is above threshold and amount is below ceiling, silently approve."""
    try:
        amt = float(amount)
    except (ValueError, TypeError):
        return False
        
    trust_data = get_trust_score(supplier_id)
    
    if trust_data.get("is_new"):
        return False
        
    return trust_data.get("score", 0) >= TRUST_THRESHOLD and amt <= AMOUNT_CEILING
