"""Basket analysis — frequently bought together.

Uses co-occurrence counting from order history.
"""

import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_orders():
    try:
        with open(DATA_DIR / "mock_orders.json") as f:
            return json.load(f).get("customer_orders", [])
    except Exception:
        return []


def _load_inventory():
    try:
        with open(DATA_DIR / "mock_inventory.json") as f:
            return {item["sku"]: item for item in json.load(f)}
    except Exception:
        return {}


def compute_co_occurrences(min_support: int = 2) -> list[dict]:
    """Find product pairs frequently bought together."""
    orders = _load_orders()
    inv = _load_inventory()
    pair_counts: Counter = Counter()
    sku_counts: Counter = Counter()

    for order in orders:
        skus = list({item["sku"] for item in order.get("items", [])})
        for sku in skus:
            sku_counts[sku] += 1
        for pair in combinations(sorted(skus), 2):
            pair_counts[pair] += 1

    results = []
    for (sku_a, sku_b), count in pair_counts.most_common(50):
        if count < min_support:
            break
        # Calculate lift: P(A&B) / (P(A) * P(B))
        total_orders = len(orders) or 1
        p_ab = count / total_orders
        p_a = sku_counts.get(sku_a, 1) / total_orders
        p_b = sku_counts.get(sku_b, 1) / total_orders
        lift = p_ab / (p_a * p_b) if (p_a * p_b) > 0 else 0

        results.append({
            "product_a": {"sku": sku_a, "name": inv.get(sku_a, {}).get("product_name", sku_a)},
            "product_b": {"sku": sku_b, "name": inv.get(sku_b, {}).get("product_name", sku_b)},
            "co_occurrence_count": count,
            "lift": round(lift, 2),
            "confidence_a_then_b": round(count / max(sku_counts.get(sku_a, 1), 1) * 100, 1),
            "confidence_b_then_a": round(count / max(sku_counts.get(sku_b, 1), 1) * 100, 1),
        })

    results.sort(key=lambda x: x["lift"], reverse=True)
    return results


def get_recommendations_for(sku: str, top_n: int = 5) -> list[dict]:
    """Given a product, recommend what to buy with it."""
    all_pairs = compute_co_occurrences(min_support=1)
    inv = _load_inventory()

    recommendations = []
    for pair in all_pairs:
        if pair["product_a"]["sku"] == sku:
            recommendations.append({
                "sku": pair["product_b"]["sku"],
                "product_name": pair["product_b"]["name"],
                "score": pair["lift"],
                "co_purchases": pair["co_occurrence_count"],
            })
        elif pair["product_b"]["sku"] == sku:
            recommendations.append({
                "sku": pair["product_a"]["sku"],
                "product_name": pair["product_a"]["name"],
                "score": pair["lift"],
                "co_purchases": pair["co_occurrence_count"],
            })

    recommendations.sort(key=lambda x: x["score"], reverse=True)
    return recommendations[:top_n]
