# brain/shift_optimizer.py
from datetime import date
from brain.footfall_analyzer import get_footfall_pattern
from brain.festival_detector import check_upcoming_festival

# Heuristic: 1 staff member can comfortably serve/checkout 20 customers per hour
CUSTOMERS_PER_STAFF_HOUR = 20

def _get_connection():
    from brain.decision_logger import _get_connection as _get_main_conn
    return _get_main_conn()

def get_current_shifts(shift_date: str) -> dict:
    """Returns a dict of hour -> assigned staff density for a given date."""
    coverage = {h: 0 for h in range(24)}
    
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT start_hour, end_hour FROM staff_shifts WHERE shift_date = ?", (shift_date,))
        rows = cursor.fetchall()
        for start_h, end_h in rows:
            for h in range(start_h, end_h):
                coverage[h] += 1
                
    return coverage

def calculate_adequacy(target_date: date) -> dict:
    target_date_str = target_date.strftime("%Y-%m-%d")
    day_of_week = target_date.weekday()
    
    # Extract prediction
    base_pattern = get_footfall_pattern(day_of_week)
    total_base = sum(base_pattern.values())
    
    # Assess contextual surges
    festival = check_upcoming_festival(target_date)
    multiplier = festival["multiplier"] if festival else 1.0
    
    predicted_pattern = {h: int(count * multiplier) for h, count in base_pattern.items()}
    total_predicted = sum(predicted_pattern.values())
    
    coverage = get_current_shifts(target_date_str)
    
    hourly_eval = {}
    for h in range(24):
        footfall = predicted_pattern.get(h, 0)
        # Skip empty inactive hours
        if footfall == 0 and coverage[h] == 0:
            continue
            
        required_staff = (footfall + CUSTOMERS_PER_STAFF_HOUR - 1) // CUSTOMERS_PER_STAFF_HOUR # ceiling
        actual_staff = coverage[h]
        
        status = "Adequate"
        gap = actual_staff - required_staff
        if gap < 0:
            status = "Understaffed"
        elif gap > 1:
            status = "Overstaffed" # Tolerate exactly 1 spare member safely
            
        hourly_eval[h] = {
            "predicted_footfall": footfall,
            "required_staff": required_staff,
            "actual_staff": actual_staff,
            "status": status,
            "gap": gap
        }
    
    # Group contiguous sequences explicitly mapping the hours cleanly
    grouped_blocks = []
    if hourly_eval:
        active_hours = sorted(hourly_eval.keys())
        current_status = hourly_eval[active_hours[0]]["status"]
        start_h = active_hours[0]
        avg_footfall_agg = [hourly_eval[active_hours[0]]["predicted_footfall"]]
        staff_vol = hourly_eval[active_hours[0]]["actual_staff"]
        sum_gap_agg = hourly_eval[active_hours[0]]["gap"]
        
        for h in active_hours[1:]:
            eval_h = hourly_eval[h]
            # Group if exact same block type logic matches
            if eval_h["status"] == current_status and eval_h["actual_staff"] == staff_vol and (h == active_hours[active_hours.index(h)-1] + 1):
                avg_footfall_agg.append(eval_h["predicted_footfall"])
                sum_gap_agg += eval_h["gap"]
            else:
                grouped_blocks.append({
                    "start": start_h,
                    "end": h,
                    "status": current_status,
                    "avg_footfall": int(sum(avg_footfall_agg)/len(avg_footfall_agg)),
                    "staff": staff_vol,
                    "gap": sum_gap_agg
                })
                # Reset counters
                current_status = eval_h["status"]
                start_h = h
                staff_vol = eval_h["actual_staff"]
                avg_footfall_agg = [eval_h["predicted_footfall"]]
                sum_gap_agg = eval_h["gap"]
                
        # Mount the tail block automatically
        grouped_blocks.append({
            "start": start_h,
            "end": active_hours[-1] + 1,
            "status": current_status,
            "avg_footfall": int(sum(avg_footfall_agg)/len(avg_footfall_agg)),
            "staff": staff_vol,
            "gap": sum_gap_agg
        })

    increase_pct = round((total_predicted / max(1.0, float(total_base)) - 1.0) * 100) if total_base > 0 else 0

    return {
        "target_date": target_date_str,
        "base_footfall": total_base,
        "predicted_footfall": total_predicted,
        "increase_pct": increase_pct,
        "festival": festival,
        "hourly_blocks": grouped_blocks
    }
