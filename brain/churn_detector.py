# brain/churn_detector.py
import time

CHURN_THRESHOLD = 70  # score above this triggers a churn_risk event

def get_churn_scores(customers: list[dict], current_time: float | None = None) -> list[dict]:
    """
    For each customer, calculates personal avg purchase frequency,
    compares to days since last purchase, returns a churn risk score 0-100.
    """
    if current_time is None:
        current_time = time.time()

    results = []
    for customer in customers:
        purchases = customer.get("purchase_history", [])
        if len(purchases) < 2:
            # Not enough data to establish a baseline
            continue

        # Sort by timestamp
        sorted_purchases = sorted(purchases, key=lambda p: p.get("timestamp", 0))
        timestamps = [p.get("timestamp", 0) for p in sorted_purchases if p.get("timestamp", 0) > 0]

        if len(timestamps) < 2:
            continue

        # Calculate personal average gap between purchases (in days)
        gaps = []
        for i in range(1, len(timestamps)):
            gap_days = (timestamps[i] - timestamps[i - 1]) / 86400
            gaps.append(gap_days)

        avg_gap = sum(gaps) / len(gaps)
        if avg_gap <= 0:
            continue

        # Days since last purchase
        days_since_last = (current_time - timestamps[-1]) / 86400

        # Churn ratio: how many multiples of their average gap have elapsed
        churn_ratio = days_since_last / avg_gap

        # Map to 0-100 score:
        # ratio <= 1.0 → score 0 (buying on schedule)
        # ratio  = 2.0 → score 50 (double their usual gap)
        # ratio >= 3.0 → score 100 (triple or more)
        if churn_ratio <= 1.0:
            score = 0
        elif churn_ratio >= 3.0:
            score = 100
        else:
            score = int(((churn_ratio - 1.0) / 2.0) * 100)

        result = {
            "customer_id": customer.get("phone", customer.get("id", "")),
            "customer_name": customer.get("name", "Unknown"),
            "avg_purchase_gap_days": round(avg_gap, 1),
            "days_since_last_purchase": round(days_since_last, 1),
            "churn_ratio": round(churn_ratio, 2),
            "churn_score": score,
        }
        results.append(result)

    return results

def detect_at_risk_customers(customers: list[dict], current_time: float | None = None) -> list[dict]:
    """Returns only customers above the churn threshold, as events to emit."""
    scores = get_churn_scores(customers, current_time)
    events = []
    for s in scores:
        if s["churn_score"] >= CHURN_THRESHOLD:
            events.append({
                "type": "churn_risk",
                "data": {
                    "customer_id": s["customer_id"],
                    "customer_name": s["customer_name"],
                    "churn_score": s["churn_score"],
                    "avg_gap_days": s["avg_purchase_gap_days"],
                    "days_absent": s["days_since_last_purchase"],
                }
            })
    return events
