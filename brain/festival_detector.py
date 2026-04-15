# brain/festival_detector.py
"""Detect upcoming Indian festivals and return demand multipliers.

Festivals are loaded from a JSON config file so they can be updated
without code changes. Falls back to a built-in list covering major
pan-India holidays for 2025-2027.
"""

import json
from datetime import date, timedelta
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "festivals.json"

# Built-in fallback covering major Indian festivals (2025-2027)
_DEFAULT_FESTIVALS = [
    # 2025
    {"date": "2025-03-14", "name": "Holi", "multiplier": 1.4},
    {"date": "2025-04-14", "name": "Baisakhi", "multiplier": 1.2},
    {"date": "2025-08-16", "name": "Raksha Bandhan", "multiplier": 1.3},
    {"date": "2025-10-02", "name": "Gandhi Jayanti", "multiplier": 1.1},
    {"date": "2025-10-20", "name": "Diwali", "multiplier": 2.0},
    {"date": "2025-11-05", "name": "Chhath Puja", "multiplier": 1.3},
    {"date": "2025-12-25", "name": "Christmas", "multiplier": 1.2},
    # 2026
    {"date": "2026-01-14", "name": "Makar Sankranti", "multiplier": 1.2},
    {"date": "2026-03-04", "name": "Holi", "multiplier": 1.4},
    {"date": "2026-03-30", "name": "Eid ul-Fitr", "multiplier": 1.4},
    {"date": "2026-04-14", "name": "Baisakhi", "multiplier": 1.2},
    {"date": "2026-04-18", "name": "Ram Navami", "multiplier": 1.3},
    {"date": "2026-08-05", "name": "Raksha Bandhan", "multiplier": 1.3},
    {"date": "2026-08-14", "name": "Independence Day", "multiplier": 1.1},
    {"date": "2026-10-08", "name": "Navratri Start", "multiplier": 1.3},
    {"date": "2026-10-19", "name": "Dussehra", "multiplier": 1.4},
    {"date": "2026-11-08", "name": "Diwali", "multiplier": 2.0},
    {"date": "2026-12-25", "name": "Christmas", "multiplier": 1.2},
    # 2027
    {"date": "2027-01-14", "name": "Makar Sankranti", "multiplier": 1.2},
    {"date": "2027-03-22", "name": "Holi", "multiplier": 1.4},
    {"date": "2027-10-29", "name": "Diwali", "multiplier": 2.0},
]


def _load_festivals() -> list[dict]:
    """Load festivals from config file, falling back to built-in defaults."""
    try:
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return _DEFAULT_FESTIVALS


def check_upcoming_festival(target_date: date, lookahead_days: int = 14) -> dict:
    """Check if any festival falls within the lookahead window.

    Returns the nearest festival with its demand multiplier, or empty dict.
    """
    festivals = _load_festivals()
    nearest = None

    for entry in festivals:
        try:
            fest_date = date.fromisoformat(entry["date"])
        except (ValueError, KeyError):
            continue

        days_until = (fest_date - target_date).days
        if 0 <= days_until <= lookahead_days:
            if nearest is None or days_until < nearest["days_until"]:
                nearest = {
                    "festival_name": entry["name"],
                    "days_until": days_until,
                    "multiplier": entry.get("multiplier", 1.0),
                }

    return nearest or {}
