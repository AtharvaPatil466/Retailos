import asyncio
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from runtime.orchestrator import Orchestrator
from auth.routes import router as auth_router
from notifications.routes import router as notifications_router
from reports.routes import router as reports_router
from api.loyalty_routes import router as loyalty_router
from api.health_routes import router as health_router
from api.ml_routes import router as ml_router
from api.workflow_routes import router as workflow_router
from api.returns_routes import router as returns_router
from api.vendor_routes import router as vendor_router
from api.udhaar_routes import router as udhaar_v2_router
from api.promotions_routes import router as promotions_router
from api.staff_routes import router as staff_router
from api.webhook_routes import router as webhook_router
from api.store_routes import router as store_router
from api.i18n_routes import router as i18n_router
from api.mobile_routes import router as mobile_router
from api.payment_routes import router as payment_router
from api.whatsapp_routes import router as whatsapp_router
from api.backup_routes import router as backup_router
from api.scheduler_routes import router as scheduler_router, set_scheduler
from api.push_routes import router as push_router
from api.sms_routes import router as sms_router
from api.digest_routes import router as digest_router
from api.tally_routes import router as tally_router


# ── Helpers ────────────────────────────────────────────────

def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _read_json(filename: str, default=None):
    try:
        with open(_data_dir() / filename, "r") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []


def _write_json(filename: str, data):
    with open(_data_dir() / filename, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()


# ── Pydantic Models ────────────────────────────────────────

class EventPayload(BaseModel):
    type: str
    data: dict[str, Any] = {}

class StockUpdatePayload(BaseModel):
    sku: str
    quantity: int
    unit_price: float | None = None
    image_url: str | None = None
    category: str | None = None

class InventoryRegisterPayload(BaseModel):
    sku: str
    product_name: str
    unit_price: float
    category: str
    image_url: str | None = None
    barcode: str | None = None
    threshold: int
    daily_sales_rate: int
    current_stock: int = 0

class InventoryPatchPayload(BaseModel):
    unit_price: float | None = None
    image_url: str | None = None
    category: str | None = None
    barcode: str | None = None

class SaleItemPayload(BaseModel):
    sku: str
    qty: int

class InventorySalePayload(BaseModel):
    items: list[SaleItemPayload]
    customer_id: str | None = None
    customer_name: str | None = None
    phone: str | None = None
    payment_method: str = "Cash"

class SupplierReplyPayload(BaseModel):
    negotiation_id: str
    supplier_id: str
    supplier_name: str
    message: str
    product_name: str = ""

class ApprovalPayload(BaseModel):
    approval_id: str
    reason: str = ""

class SupplierRegisterPayload(BaseModel):
    supplier_id: str
    supplier_name: str
    contact_phone: str
    whatsapp_number: str = ""
    products: list[str] = []
    categories: list[str] = []
    price_per_unit: float = 0
    min_order_qty: int = 0
    delivery_days: int = 0
    payment_terms: str = ""
    location: str = ""
    notes: str = ""

class MarketPriceLogPayload(BaseModel):
    product_id: str
    source_name: str
    price_per_unit: float
    unit: str = "kg"

class DeliveryStatusPayload(BaseModel):
    status: str

class UdhaarCreditPayload(BaseModel):
    customer_id: str
    customer_name: str
    phone: str
    items: list[dict]
    amount: float

class UdhaarPaymentPayload(BaseModel):
    udhaar_id: str
    amount: float
    note: str = ""

class ReturnPayload(BaseModel):
    order_id: str
    customer_id: str
    customer_name: str
    items: list[dict]
    refund_method: str = "Cash"

class SupplierPaymentPayload(BaseModel):
    order_id: str

class VoiceCommandPayload(BaseModel):
    text: str

class CustomerAssistantPayload(BaseModel):
    text: str


# ── GST Rates by category ─────────────────────────────────
GST_RATES = {
    "Grocery": 0.05,
    "Dairy": 0.05,
    "Frozen": 0.12,
    "Snacks": 0.12,
    "Beverages": 0.12,
    "Personal Care": 0.18,
    "Cleaning": 0.18,
    "Baby Care": 0.12,
    "Bakery": 0.05,
    "Protein & Health": 0.18,
}

STORE_PROFILE_DEFAULT = {
    "store_name": "RetailOS Supermart",
    "phone": "+91 98765 43210",
    "address": "MG Road, Pune",
    "hours": {
        "monday": "8:00 AM - 10:00 PM",
        "tuesday": "8:00 AM - 10:00 PM",
        "wednesday": "8:00 AM - 10:00 PM",
        "thursday": "8:00 AM - 10:00 PM",
        "friday": "8:00 AM - 10:30 PM",
        "saturday": "8:00 AM - 10:30 PM",
        "sunday": "9:00 AM - 9:00 PM",
    },
    "holiday_note": "Holiday timings may vary on major festivals.",
}

ASSISTANT_CONFIG_DEFAULT = {
    "whatsapp_number": "+91 98765 43210",
    "supported_languages": ["English", "Hindi / Hinglish"],
    "default_voice_language": "en-IN",
    "enable_substitutes": True,
    "enable_recipe_clarifications": True,
    "recipe_bundles": [
        {
            "id": "chai-pack",
            "name": "Chai Pack",
            "prompt": "What do I need for chai?",
            "description": "Daily tea essentials",
            "inventory_queries": ["tea", "milk"],
        },
        {
            "id": "pasta-night",
            "name": "Pasta Night",
            "prompt": "I want to make spaghetti tomato",
            "description": "Check a simple tomato pasta ingredient set",
            "inventory_queries": ["cooking oil", "salt"],
        },
    ],
    "substitution_rules": {
        "cooking oil": [
            {"query": "sunflower oil", "label": "Fortune Sunflower Oil (1L)", "reason": "Closest stocked cooking oil"},
        ],
        "spaghetti pasta": [
            {"query": "maggi", "label": "Maggi 2-Minute Noodles", "reason": "Closest quick noodle substitute in store"},
        ],
    },
    "clarification_rules": [
        {
            "keyword": "pasta",
            "question": "Do you want red sauce pasta or white sauce pasta?",
            "options": ["Red sauce pasta", "White sauce pasta"],
        },
        {
            "keyword": "sandwich",
            "question": "Do you want a veg sandwich or a grilled cheese sandwich?",
            "options": ["Veg sandwich", "Grilled cheese sandwich"],
        },
    ],
}

LOOKUP_STOPWORDS = {
    "a",
    "an",
    "are",
    "available",
    "can",
    "do",
    "find",
    "for",
    "have",
    "i",
    "in",
    "is",
    "item",
    "located",
    "location",
    "me",
    "my",
    "on",
    "please",
    "product",
    "shelf",
    "show",
    "some",
    "stock",
    "the",
    "where",
    "which",
    "zone",
}

RECIPE_KEYWORDS = (
    "make",
    "cook",
    "recipe",
    "ingredients",
    "need for",
    "need to make",
    "want to make",
    "want to cook",
    "how do i make",
    "what do i need for",
)

INGREDIENT_ALIASES = {
    "cooking oil": ["oil", "sunflower oil", "refined oil"],
    "oil": ["sunflower oil", "refined oil"],
    "tea": ["tea", "chai"],
    "chai patti": ["tea", "chai"],
    "milk": ["milk"],
    "doodh": ["milk"],
    "butter": ["butter"],
    "makhan": ["butter"],
    "paneer": ["paneer"],
    "salt": ["salt"],
    "sugar": ["sugar"],
    "spaghetti pasta": ["pasta", "spaghetti"],
    "green chilli": ["chilli", "green chilli"],
}

HINGLISH_REPLACEMENTS = {
    "kidhar": "where",
    "kahan": "where",
    "hai kya": "do you have",
    "milta hai kya": "do you have",
    "band kab": "what time do you close",
    "khula kab": "when do you open",
    "banana hai": "want to make",
    "banani hai": "want to make",
    "banane ke liye": "what do i need for",
    "ke liye kya chahiye": "what do i need for",
    "chai ke liye kya chahiye": "what do i need for chai",
    "maggi hai kya": "do you have maggi",
    "amul butter kidhar hai": "where is amul butter",
}


def _normalize_lookup_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _lookup_tokens(value: str) -> list[str]:
    return [token for token in _normalize_lookup_text(value).split() if token and token not in LOOKUP_STOPWORDS]


def _inventory_snapshot(skill) -> list[dict[str, Any]]:
    return getattr(skill, "inventory_data", None) or _read_json("mock_inventory.json", [])


def _load_store_profile() -> dict[str, Any]:
    return _read_json("store_profile.json", STORE_PROFILE_DEFAULT)


def _load_assistant_config() -> dict[str, Any]:
    return _read_json("customer_assistant_config.json", ASSISTANT_CONFIG_DEFAULT)


def _write_assistant_config(config: dict[str, Any]) -> None:
    _write_json("customer_assistant_config.json", config)


def _load_assistant_logs() -> list[dict[str, Any]]:
    return _read_json("customer_assistant_logs.json", [])


def _write_assistant_logs(entries: list[dict[str, Any]]) -> None:
    _write_json("customer_assistant_logs.json", entries)


def _normalize_customer_query(text: str) -> str:
    normalized = text.strip()
    lowered = normalized.lower()
    for source, target in HINGLISH_REPLACEMENTS.items():
        lowered = lowered.replace(source, target)
    return lowered


def _resolve_zone_shelf(zone: dict[str, Any], shelf_level: str, preferred_shelf_id: str | None = None) -> dict[str, Any] | None:
    shelves = zone.get("shelves", [])
    if not shelves:
        return None

    if preferred_shelf_id:
        preferred = next((shelf for shelf in shelves if shelf.get("shelf_id") == preferred_shelf_id), None)
        if preferred:
            return preferred

    for shelf in shelves:
        if shelf_level in shelf.get("levels", []):
            return shelf

    return shelves[0]


def _hydrate_shelf_assignments(data: dict[str, Any], persist: bool = False) -> dict[str, Any]:
    changed = False
    for zone in data.get("zones", []):
        for product in zone.get("products", []):
            shelf = _resolve_zone_shelf(zone, product.get("shelf_level", "lower"), product.get("shelf_id"))
            if not shelf:
                continue
            if product.get("shelf_id") != shelf.get("shelf_id"):
                product["shelf_id"] = shelf.get("shelf_id")
                changed = True
            if product.get("shelf_name") != shelf.get("shelf_name"):
                product["shelf_name"] = shelf.get("shelf_name")
                changed = True

    if persist and changed:
        _write_json("mock_shelf_zones.json", data)

    return data


def _score_inventory_match(query: str, item: dict[str, Any]) -> int:
    normalized_query = _normalize_lookup_text(query)
    normalized_name = _normalize_lookup_text(item.get("product_name", ""))
    normalized_sku = _normalize_lookup_text(item.get("sku", ""))
    query_tokens = _lookup_tokens(query)
    name_tokens = set(_lookup_tokens(item.get("product_name", "")))

    score = 0
    if normalized_query == normalized_sku:
        score += 130
    if normalized_query == normalized_name:
        score += 120
    if normalized_query and normalized_query in normalized_name:
        score += 95
    if normalized_query and normalized_query in normalized_sku:
        score += 90

    for alias in INGREDIENT_ALIASES.get(normalized_query, []):
        normalized_alias = _normalize_lookup_text(alias)
        if normalized_alias and normalized_alias in normalized_name:
            score += 45

    overlap = len([token for token in query_tokens if token in name_tokens or token == normalized_sku])
    if overlap:
        score += overlap * 20

    category = _normalize_lookup_text(item.get("category", ""))
    if normalized_query and normalized_query == category:
        score += 10

    return score


def _find_best_inventory_match(query: str, inventory: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not query.strip():
        return None

    scored = []
    for item in inventory:
        score = _score_inventory_match(query, item)
        if score > 0:
            scored.append((score, item))

    if not scored:
        return None

    scored.sort(key=lambda entry: (entry[0], entry[1].get("daily_sales_rate", 0), entry[1].get("current_stock", 0)), reverse=True)
    return scored[0][1] if scored[0][0] >= 40 else None


def _find_substitutes(ingredient_name: str, inventory: list[dict[str, Any]], assistant_config: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions = []
    for rule in assistant_config.get("substitution_rules", {}).get(_normalize_lookup_text(ingredient_name), []):
        matched = _find_best_inventory_match(rule.get("query", ""), inventory)
        if not matched:
            continue
        suggestions.append(
            {
                "ingredient": ingredient_name,
                "label": rule.get("label", matched.get("product_name")),
                "reason": rule.get("reason", "Suggested substitute"),
                "matched_product": matched.get("product_name"),
                "sku": matched.get("sku"),
                "current_stock": matched.get("current_stock", 0),
            }
        )
    return suggestions


def _extract_candidate_product_query(text: str) -> str:
    patterns = [
        r"(?:where(?: can i find| is| are)?|find|locate|which shelf(?: is| are)?|which zone(?: is| are)?|show me)\s+(.+)",
        r"(?:do you have|have you got|is there|is|are)\s+(.+?)(?:\s+(?:available|in stock))?$",
        r"(.+?)\s+(?:available|in stock)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" ?.")
    return text.strip(" ?.")


def _format_store_hours(profile: dict[str, Any]) -> tuple[str, str]:
    hours = profile.get("hours", {})
    today_key = datetime.now().strftime("%A").lower()
    today_hours = hours.get(today_key, "Hours unavailable")
    weekly = ", ".join(
        f"{day[:3].title()} {hours[day]}"
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        if day in hours
    )
    return today_hours, weekly


def _is_recipe_query(text: str) -> bool:
    normalized = _normalize_lookup_text(text)
    return any(keyword in normalized for keyword in RECIPE_KEYWORDS)


def _extract_recipe_query(text: str) -> str:
    patterns = [
        r"(?:i want to make|i want to cook|want to make|want to cook|how do i make|what do i need for|ingredients for|recipe for)\s+(.+)",
        r"(?:make|cook)\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" ?.")
    return text.strip(" ?.")


def _build_recipe_clarification(recipe_query: str, assistant_config: dict[str, Any]) -> dict[str, Any] | None:
    normalized = _normalize_lookup_text(recipe_query)
    token_count = len(_lookup_tokens(recipe_query))
    if token_count > 3:
        return None

    for rule in assistant_config.get("clarification_rules", []):
        keyword = _normalize_lookup_text(rule.get("keyword", ""))
        if keyword and keyword in normalized:
            return {
                "intent": "recipe_clarification",
                "answer": rule.get("question", "Can you clarify which version you want?"),
                "clarification_question": rule.get("question", ""),
                "clarification_options": rule.get("options", []),
                "follow_up_suggestions": rule.get("options", []),
            }
    return None


def _build_shelf_lookup(shelf_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    shelf_lookup: dict[str, dict[str, Any]] = {}
    for zone in shelf_data.get("zones", []):
        for product in zone.get("products", []):
            shelf_lookup[product.get("sku", "")] = {
                "zone_id": zone.get("zone_id"),
                "zone_name": zone.get("zone_name"),
                "zone_type": zone.get("zone_type"),
                "shelf_id": product.get("shelf_id"),
                "shelf_name": product.get("shelf_name"),
                "shelf_level": product.get("shelf_level"),
            }
    return shelf_lookup


def _classify_inventory_match(item: dict[str, Any], placement: dict[str, Any] | None) -> str:
    stock = item.get("current_stock", 0)
    if stock <= 0:
        return "out_of_stock"
    if placement:
        return "in_stock_mapped"
    return "in_stock_unassigned"


def _match_recipe_ingredients(recipe: dict[str, Any], inventory: list[dict[str, Any]], shelf_lookup: dict[str, dict[str, Any]], assistant_config: dict[str, Any]) -> dict[str, Any]:
    found = []
    missing = []
    not_carried = []

    for ingredient in recipe.get("ingredients", []):
        ingredient_name = ingredient.get("name", "").strip()
        if not ingredient_name:
            continue

        matched = _find_best_inventory_match(ingredient_name, inventory)
        if not matched:
            entry = (
                {
                    "ingredient": ingredient_name,
                    "quantity_hint": ingredient.get("quantity_hint", ""),
                    "category_hint": ingredient.get("category_hint", ""),
                    "is_optional": bool(ingredient.get("is_optional", False)),
                    "status": "not_carried",
                }
            )
            if assistant_config.get("enable_substitutes"):
                entry["substitutes"] = _find_substitutes(ingredient_name, inventory, assistant_config)
            not_carried.append(entry)
            continue

        placement = shelf_lookup.get(matched.get("sku"))
        status = _classify_inventory_match(matched, placement)
        entry = {
            "ingredient": ingredient_name,
            "quantity_hint": ingredient.get("quantity_hint", ""),
            "category_hint": ingredient.get("category_hint", ""),
            "is_optional": bool(ingredient.get("is_optional", False)),
            "matched_product": matched.get("product_name"),
            "sku": matched.get("sku"),
            "current_stock": matched.get("current_stock", 0),
            "status": status,
        }
        if placement:
            entry.update(placement)
        if status != "in_stock_mapped" and assistant_config.get("enable_substitutes"):
            entry["substitutes"] = _find_substitutes(ingredient_name, inventory, assistant_config)

        if status == "out_of_stock":
            missing.append(entry)
        else:
            found.append(entry)

    return {
        "ingredients_found": found,
        "ingredients_missing": missing,
        "ingredients_not_carried": not_carried,
    }


def _build_recipe_answer(recipe: dict[str, Any], matched: dict[str, Any]) -> dict[str, Any]:
    found = matched["ingredients_found"]
    missing = matched["ingredients_missing"]
    not_carried = matched["ingredients_not_carried"]

    answer_parts = [
        f"For {recipe.get('dish_name', 'this dish')}, I checked the store and found {len(found)} ingredient{'s' if len(found) != 1 else ''} available now."
    ]
    if missing:
        answer_parts.append(f"{len(missing)} ingredient{' is' if len(missing) == 1 else 's are'} currently out of stock.")
    if not_carried:
        answer_parts.append(f"{len(not_carried)} ingredient{' is' if len(not_carried) == 1 else 's are'} not currently carried.")
    if recipe.get("notes"):
        answer_parts.append(recipe["notes"])

    first_available = found[0]["ingredient"] if found else None
    substitute_count = sum(len(entry.get("substitutes", [])) for entry in missing + not_carried)
    return {
        "intent": "recipe_assistant",
        "dish_name": recipe.get("dish_name"),
        "answer": " ".join(answer_parts),
        "recipe_notes": recipe.get("notes", ""),
        **matched,
        "substitute_count": substitute_count,
        "follow_up_suggestions": [
            f"Where is {first_available}?" if first_available else "Where is the first available ingredient?",
            "Do you have everything for chai?",
            "What time do you close?",
        ],
    }


def _bundle_recommendations(inventory: list[dict[str, Any]], assistant_config: dict[str, Any]) -> list[dict[str, Any]]:
    recommendations = []
    for bundle in assistant_config.get("recipe_bundles", []):
        bundle_items = []
        all_available = True
        for query in bundle.get("inventory_queries", []):
            matched = _find_best_inventory_match(query, inventory)
            bundle_items.append(
                {
                    "query": query,
                    "matched_product": matched.get("product_name") if matched else None,
                    "available": bool(matched and matched.get("current_stock", 0) > 0),
                }
            )
            if not matched or matched.get("current_stock", 0) <= 0:
                all_available = False
        recommendations.append(
            {
                **bundle,
                "all_available": all_available,
                "items": bundle_items,
            }
        )
    return recommendations


def _log_customer_assistant_query(original_text: str, normalized_text: str, response: dict[str, Any]) -> None:
    logs = _load_assistant_logs()
    logs.append(
        {
            "timestamp": time.time(),
            "query": original_text,
            "normalized_query": normalized_text,
            "intent": response.get("intent"),
            "dish_name": response.get("dish_name"),
            "availability_status": response.get("availability_status"),
            "missing_ingredients": [entry.get("ingredient") for entry in response.get("ingredients_missing", [])],
            "not_carried_ingredients": [entry.get("ingredient") for entry in response.get("ingredients_not_carried", [])],
        }
    )
    _write_assistant_logs(logs[-400:])


def _assistant_analytics() -> dict[str, Any]:
    logs = _load_assistant_logs()
    intent_counts: dict[str, int] = {}
    query_counts: dict[str, int] = {}
    missing_counts: dict[str, int] = {}
    recipe_counts: dict[str, int] = {}

    for entry in logs:
        intent = entry.get("intent") or "unknown"
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
        query = entry.get("normalized_query") or ""
        if query:
            query_counts[query] = query_counts.get(query, 0) + 1
        if entry.get("dish_name"):
            recipe_counts[entry["dish_name"]] = recipe_counts.get(entry["dish_name"], 0) + 1
        for ingredient in entry.get("missing_ingredients", []) + entry.get("not_carried_ingredients", []):
            if ingredient:
                missing_counts[ingredient] = missing_counts.get(ingredient, 0) + 1

    top_queries = sorted(query_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    top_missing = sorted(missing_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    top_recipes = sorted(recipe_counts.items(), key=lambda item: item[1], reverse=True)[:5]

    return {
        "total_queries": len(logs),
        "intent_counts": intent_counts,
        "top_queries": [{"query": query, "count": count} for query, count in top_queries],
        "top_missing_items": [{"ingredient": ingredient, "count": count} for ingredient, count in top_missing],
        "top_recipes": [{"dish_name": dish_name, "count": count} for dish_name, count in top_recipes],
    }


async def _answer_customer_assistant_query(
    text: str,
    inventory: list[dict[str, Any]],
    shelf_data: dict[str, Any],
    store_profile: dict[str, Any],
    assistant_config: dict[str, Any],
) -> dict[str, Any]:
    cleaned_text = text.strip()
    translated_text = _normalize_customer_query(cleaned_text)
    normalized = _normalize_lookup_text(translated_text)
    bundle_recommendations = _bundle_recommendations(inventory, assistant_config)

    if not normalized:
        return {
            "intent": "unknown",
            "answer": "Ask about a product location, availability, or store hours.",
            "bundle_recommendations": bundle_recommendations,
            "follow_up_suggestions": [
                "Where is Amul butter?",
                "Do you have Maggi?",
                "What time do you close?",
            ],
        }

    if any(phrase in normalized for phrase in ("store hours", "open today", "what time", "when do you open", "when do you close", "closing time", "opening time", "hours")):
        today_hours, weekly_hours = _format_store_hours(store_profile)
        return {
            "intent": "store_info",
            "answer": f"{store_profile.get('store_name', 'The store')} is open today from {today_hours}.",
            "store_name": store_profile.get("store_name"),
            "today_hours": today_hours,
            "weekly_hours": weekly_hours,
            "holiday_note": store_profile.get("holiday_note"),
            "bundle_recommendations": bundle_recommendations,
            "follow_up_suggestions": [
                "Where is Coca-Cola?",
                "Do you have Amul milk?",
            ],
        }

    if _is_recipe_query(translated_text):
        from brain.recipe_assistant import parse_recipe_request

        recipe_query = _extract_recipe_query(translated_text)
        if assistant_config.get("enable_recipe_clarifications"):
            clarification = _build_recipe_clarification(recipe_query, assistant_config)
            if clarification:
                clarification["bundle_recommendations"] = bundle_recommendations
                return clarification

        recipe = await parse_recipe_request(recipe_query)
        shelf_lookup = _build_shelf_lookup(shelf_data)
        matched = _match_recipe_ingredients(recipe, inventory, shelf_lookup, assistant_config)
        response = _build_recipe_answer(recipe, matched)
        response["bundle_recommendations"] = bundle_recommendations
        return response

    candidate_query = _extract_candidate_product_query(translated_text)
    matched = _find_best_inventory_match(candidate_query, inventory)
    if not matched:
        return {
            "intent": "product_lookup",
            "answer": f"I couldn't find a product matching '{candidate_query}'.",
            "availability_status": "not_found",
            "bundle_recommendations": bundle_recommendations,
            "follow_up_suggestions": [
                "Try the full product name",
                "Ask: Do you have Maggi?",
                "Ask: Where is Amul butter?",
            ],
        }

    shelf_lookup = _build_shelf_lookup(shelf_data)
    placement = shelf_lookup.get(matched.get("sku"))
    current_stock = matched.get("current_stock", 0)
    intent = "shelf_location" if any(word in normalized for word in ("where", "find", "shelf", "zone", "located")) else "product_availability"

    if intent == "shelf_location":
        if placement:
            answer = (
                f"{matched['product_name']} is in {placement['zone_name']} ({placement['zone_id']}), "
                f"{placement.get('shelf_name', 'Shelf')}, {placement.get('shelf_level', 'lower').replace('_', ' ')} level."
            )
            return {
                "intent": intent,
                "answer": answer,
                "product": matched["product_name"],
                "sku": matched["sku"],
                "availability_status": "in_stock" if current_stock > 0 else "out_of_stock",
                "current_stock": current_stock,
                "bundle_recommendations": bundle_recommendations,
                **placement,
                "follow_up_suggestions": [
                    f"Do you have {matched['product_name']}?",
                    "What time do you close?",
                ],
            }

        if current_stock > 0:
            return {
                "intent": intent,
                "answer": f"{matched['product_name']} is in stock, but it is not mapped to a shelf yet.",
                "product": matched["product_name"],
                "sku": matched["sku"],
                "availability_status": "in_stock_unassigned",
                "current_stock": current_stock,
                "bundle_recommendations": bundle_recommendations,
                "follow_up_suggestions": [
                    f"Do you have {matched['product_name']}?",
                    "What time do you close?",
                ],
            }

        substitutes = _find_substitutes(matched["product_name"], inventory, assistant_config) if assistant_config.get("enable_substitutes") else []
        return {
            "intent": intent,
            "answer": f"{matched['product_name']} is currently out of stock.",
            "product": matched["product_name"],
            "sku": matched["sku"],
            "availability_status": "out_of_stock",
            "current_stock": current_stock,
            "substitutes": substitutes,
            "bundle_recommendations": bundle_recommendations,
            "follow_up_suggestions": [
                "Do you have a similar item?",
                "What time do you open tomorrow?",
            ],
        }

    if current_stock > 0 and placement:
        answer = (
            f"Yes, {matched['product_name']} is available. "
            f"You can find it in {placement['zone_name']} ({placement['zone_id']}), {placement.get('shelf_name', 'Shelf')}."
        )
        return {
            "intent": intent,
            "answer": answer,
            "product": matched["product_name"],
            "sku": matched["sku"],
            "availability_status": "in_stock",
            "current_stock": current_stock,
            "bundle_recommendations": bundle_recommendations,
            **placement,
            "follow_up_suggestions": [
                f"Where is {matched['product_name']}?",
                "What time do you close?",
            ],
        }

    if current_stock > 0:
        return {
            "intent": intent,
            "answer": f"Yes, {matched['product_name']} is available. We have {current_stock} units in stock.",
            "product": matched["product_name"],
            "sku": matched["sku"],
            "availability_status": "in_stock",
            "current_stock": current_stock,
            "bundle_recommendations": bundle_recommendations,
            "follow_up_suggestions": [
                f"Where is {matched['product_name']}?",
                "What time do you close?",
            ],
        }

    substitutes = _find_substitutes(matched["product_name"], inventory, assistant_config) if assistant_config.get("enable_substitutes") else []
    return {
        "intent": intent,
        "answer": f"{matched['product_name']} is currently out of stock.",
        "product": matched["product_name"],
        "sku": matched["sku"],
        "availability_status": "out_of_stock",
        "current_stock": current_stock,
        "substitutes": substitutes,
        "bundle_recommendations": bundle_recommendations,
        "follow_up_suggestions": [
            "Ask for another product",
            "What time do you open tomorrow?",
        ],
    }


def _calc_gst(items: list, inventory_data: list | None = None) -> float:
    """Calculate GST for a list of order items."""
    total_gst = 0.0
    inv_map = {}
    if inventory_data:
        inv_map = {item["sku"]: item.get("category", "Grocery") for item in inventory_data}
    for item in items:
        cat = inv_map.get(item.get("sku"), "Grocery")
        rate = GST_RATES.get(cat, 0.05)
        total_gst += item.get("total", item.get("unit_price", 0) * item.get("qty", 1)) * rate
    return round(total_gst)


def _business_date_from_value(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value).date()
        except Exception:
            return None
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def _order_business_date(order: dict[str, Any]) -> date | None:
    return (
        _business_date_from_value(order.get("delivery_date"))
        or _business_date_from_value(order.get("payment_date"))
        or _business_date_from_value(order.get("timestamp"))
    )


def _return_business_date(return_entry: dict[str, Any]) -> date | None:
    return (
        _business_date_from_value(return_entry.get("processed_at"))
        or _business_date_from_value(return_entry.get("timestamp"))
    )


def _movement_type_for_return_reason(reason: str) -> str:
    normalized = (reason or "").lower()
    if "expir" in normalized:
        return "expiry"
    return "damage"


def _payment_due_snapshot(order: dict[str, Any]) -> dict[str, Any]:
    terms = order.get("payment_terms", "") or "Unspecified"
    base_date = (
        _business_date_from_value(order.get("delivery_date"))
        or _order_business_date(order)
        or date.today()
    )
    due_date = base_date

    match = re.search(r"net\s+(\d+)", terms.lower())
    if match:
        due_date = base_date + timedelta(days=int(match.group(1)))

    is_paid = order.get("payment_status") == "paid"
    overdue_days = 0
    if not is_paid and due_date < date.today():
        overdue_days = (date.today() - due_date).days

    return {
        "payment_terms": terms,
        "due_date": due_date.isoformat(),
        "is_overdue": overdue_days > 0,
        "overdue_days": overdue_days,
    }


def _latest_business_date(
    customer_orders: list[dict[str, Any]],
    returns: list[dict[str, Any]],
    deliveries: list[dict[str, Any]],
) -> date:
    dates: list[date] = []
    dates.extend(d for d in (_order_business_date(order) for order in customer_orders) if d)
    dates.extend(d for d in (_return_business_date(return_entry) for return_entry in returns) if d)
    dates.extend(
        d
        for d in (
            _business_date_from_value(delivery.get("requested_at")) for delivery in deliveries
        )
        if d
    )
    return max(dates) if dates else date.today()


def _init_sentry():
    """Initialize Sentry error tracking if DSN is configured."""
    import os
    dsn = os.environ.get("SENTRY_DSN", "")
    if dsn:
        import sentry_sdk
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
            send_default_pii=False,
        )


def create_app(orchestrator: Orchestrator) -> FastAPI:
    _init_sentry()

    app = FastAPI(
        title="RetailOS",
        description=(
            "Autonomous Agent Runtime for Indian Kirana & Retail Store Operations.\n\n"
            "## Modules\n"
            "- **Auth** — JWT login, role-based access (owner/manager/staff/cashier)\n"
            "- **Inventory** — Stock tracking, shelf management, expiry alerts\n"
            "- **Orders** — Customer & vendor order lifecycle\n"
            "- **Udhaar** — Credit/khata management with limits & reminders\n"
            "- **Returns** — Return processing, refunds, credit notes\n"
            "- **Promotions** — Coupons, combos, flash sales\n"
            "- **Loyalty** — Points program, digital receipts, online catalog\n"
            "- **Staff** — Attendance, shifts, performance tracking\n"
            "- **ML/Brain** — Demand forecasting, dynamic pricing, basket analysis\n"
            "- **Notifications** — Email, SMS, WhatsApp, push, in-app\n"
            "- **Reports** — PDF/Excel exports (sales, P&L, GST, inventory)\n"
            "- **Webhooks** — Third-party event subscriptions\n"
            "- **Workflows** — Approval chains, audit logs, undo/rollback"
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=[
            {"name": "auth", "description": "Authentication & user management"},
            {"name": "notifications", "description": "Multi-channel notifications"},
            {"name": "reports", "description": "PDF/Excel report exports"},
            {"name": "loyalty", "description": "Customer loyalty, receipts, catalog"},
            {"name": "health", "description": "Health checks & metrics"},
            {"name": "ml", "description": "Demand forecasting, pricing, basket analysis"},
            {"name": "workflows", "description": "Approval chains, audit, undo stack"},
            {"name": "returns", "description": "Return processing & refunds"},
            {"name": "vendor", "description": "Purchase orders & supplier portal"},
            {"name": "udhaar", "description": "Credit/khata management"},
            {"name": "promotions", "description": "Deals, coupons, flash sales"},
            {"name": "staff", "description": "Attendance, shifts, performance"},
            {"name": "webhooks", "description": "Webhook registration & events"},
        ],
    )

    async def _apply_return_effects(return_entry: dict[str, Any]) -> dict[str, Any]:
        skill = _get_skill("inventory")
        restocked_qty = 0
        wastage_qty = 0
        restocked_value = 0.0
        wastage_value = 0.0

        for item in return_entry.get("items", []):
            qty = int(item.get("qty", 1) or 1)
            unit_price = float(item.get("unit_price", 0) or 0)
            action = item.get("action", "restock")
            if action == "restock":
                if skill:
                    current = next((p for p in skill.inventory_data if p["sku"] == item["sku"]), None)
                    if current:
                        await skill.update_stock(
                            item["sku"],
                            current["current_stock"] + qty,
                            movement_type="restock",
                        )
                restocked_qty += qty
                restocked_value += qty * unit_price
            else:
                from brain.wastage_tracker import log_movement

                movement_type = _movement_type_for_return_reason(item.get("reason", ""))
                log_movement(item["sku"], -qty, movement_type, order_id=return_entry.get("order_id"))
                wastage_qty += qty
                wastage_value += qty * unit_price

        orders = _read_json("mock_orders.json", {"customer_orders": [], "vendor_orders": []})
        linked_order = next(
            (order for order in orders["customer_orders"] if order["order_id"] == return_entry.get("order_id")),
            None,
        )
        if linked_order:
            linked_order.setdefault("return_ids", [])
            if return_entry["return_id"] not in linked_order["return_ids"]:
                linked_order["return_ids"].append(return_entry["return_id"])
            linked_order["returned_amount"] = round(
                linked_order.get("returned_amount", 0) + float(return_entry.get("refund_amount", 0)),
                2,
            )
            linked_order["net_amount"] = round(
                max(0, linked_order.get("total_amount", 0) - linked_order["returned_amount"]),
                2,
            )
            linked_order["return_status"] = (
                "returned"
                if linked_order["returned_amount"] >= linked_order.get("total_amount", 0)
                else "partially_returned"
            )
            _write_json("mock_orders.json", orders)

        if return_entry.get("refund_method") == "Credit" and return_entry.get("customer_id"):
            udhaar_list = _read_json("mock_udhaar.json", [])
            existing = next(
                (
                    record
                    for record in udhaar_list
                    if record["customer_id"] == return_entry["customer_id"] and record["balance"] > 0
                ),
                None,
            )
            if existing:
                existing["balance"] = max(0, existing["balance"] - float(return_entry["refund_amount"]))
                existing["entries"].append(
                    {
                        "order_id": return_entry.get("order_id"),
                        "date": time.strftime("%Y-%m-%d"),
                        "items": [],
                        "amount": float(return_entry["refund_amount"]),
                        "type": "refund",
                        "note": f"Return refund for {return_entry['return_id']}",
                    }
                )
                _write_json("mock_udhaar.json", udhaar_list)

        return_entry["restocked_qty"] = restocked_qty
        return_entry["wastage_qty"] = wastage_qty
        return_entry["restocked_value"] = round(restocked_value, 2)
        return_entry["wastage_value"] = round(wastage_value, 2)
        return_entry["processed_at"] = return_entry.get("processed_at") or time.time()
        return_entry["status"] = "processed"
        return return_entry

    @app.on_event("startup")
    async def startup_event():
        from db.session import init_db
        await init_db()

        async def broadcast_log(entry):
            await manager.broadcast(json.dumps({
                "type": "audit_log",
                "data": entry
            }, default=str))
        orchestrator.audit.on_log = broadcast_log

        # Start background scheduler
        scheduler.start()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security middleware
    from auth.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=120)

    # ── Auth routes ──
    app.include_router(auth_router)
    app.include_router(notifications_router)
    app.include_router(reports_router)
    app.include_router(loyalty_router)
    app.include_router(health_router)
    app.include_router(ml_router)
    app.include_router(workflow_router)
    app.include_router(returns_router)
    app.include_router(vendor_router)
    app.include_router(udhaar_v2_router)
    app.include_router(promotions_router)
    app.include_router(staff_router)
    app.include_router(webhook_router)
    app.include_router(store_router)
    app.include_router(i18n_router)
    app.include_router(mobile_router)
    app.include_router(payment_router)
    app.include_router(whatsapp_router)
    app.include_router(backup_router)
    app.include_router(scheduler_router)
    app.include_router(push_router)
    app.include_router(sms_router)
    app.include_router(digest_router)
    app.include_router(tally_router)

    # ── Initialize scheduler ──
    from scheduler.engine import Scheduler, register_default_jobs
    scheduler = Scheduler()
    register_default_jobs(scheduler)
    set_scheduler(scheduler)

    # ── Load plugins ──
    from plugins.loader import load_plugins
    plugin_context = load_plugins(app)

    @app.get("/api/plugins", tags=["plugins"])
    async def list_plugins():
        return {"plugins": plugin_context.loaded_plugins}

    def _get_skill(name: str):
        return orchestrator.skills.get(name)

    def _list_skills():
        return [skill.status() for skill in orchestrator.skills.values()]

    # ── WebSocket ──────────────────────────────────────────
    @app.websocket("/ws/events")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    # ── Runtime Status ─────────────────────────────────────
    @app.get("/api/status")
    async def get_status():
        return {
            "runtime": "running" if orchestrator.running else "stopped",
            "skills": _list_skills(),
            "pending_approvals": len(orchestrator.pending_approvals),
            "timestamp": time.time(),
        }

    @app.get("/api/skills")
    async def list_skills():
        return _list_skills()

    @app.post("/api/skills/{skill_name}/pause")
    async def pause_skill(skill_name: str):
        skill = _get_skill(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
        await skill.pause()
        return {"status": "paused", "skill": skill_name}

    @app.post("/api/skills/{skill_name}/resume")
    async def resume_skill(skill_name: str):
        skill = _get_skill(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
        await skill.resume()
        return {"status": "resumed", "skill": skill_name}

    @app.post("/api/events")
    async def emit_event(payload: EventPayload):
        await orchestrator.emit_event({"type": payload.type, "data": payload.data})
        return {"status": "event_queued", "type": payload.type}

    # ══════════════════════════════════════════════════════════
    # INVENTORY (connected: sales → orders, returns → restock)
    # ══════════════════════════════════════════════════════════

    @app.get("/api/inventory")
    async def get_inventory():
        skill = _get_skill("inventory")
        if not skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")
        return await skill.get_full_inventory()

    @app.get("/api/store-profile")
    async def get_store_profile():
        return _load_store_profile()

    @app.put("/api/store-profile")
    async def update_store_profile(payload: dict):
        profile = {**_load_store_profile(), **payload}
        _write_json("store_profile.json", profile)
        return profile

    @app.get("/api/customer-assistant/config")
    async def get_customer_assistant_config():
        return _load_assistant_config()

    @app.put("/api/customer-assistant/config")
    async def update_customer_assistant_config(payload: dict):
        config = {**_load_assistant_config(), **payload}
        _write_assistant_config(config)
        return config

    @app.get("/api/customer-assistant/analytics")
    async def get_customer_assistant_analytics():
        return _assistant_analytics()

    @app.post("/api/inventory/update")
    async def update_stock(payload: StockUpdatePayload):
        skill = _get_skill("inventory")
        if not skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")
        result = await skill.update_stock(payload.sku, payload.quantity, unit_price=payload.unit_price, image_url=payload.image_url, category=payload.category)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        await orchestrator.emit_event({"type": "stock_update", "data": {"sku": payload.sku, "quantity": payload.quantity}})
        return result

    @app.post("/api/inventory/register")
    async def register_inventory_product(payload: InventoryRegisterPayload):
        skill = _get_skill("inventory")
        if not skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")
        result = await skill.register_product(payload.model_dump())
        if "error" in result:
            raise HTTPException(status_code=409, detail=result["error"])
        return result

    @app.patch("/api/inventory/{sku}")
    async def patch_inventory_item(sku: str, payload: InventoryPatchPayload):
        skill = _get_skill("inventory")
        if not skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")
        result = await skill.patch_item(sku, unit_price=payload.unit_price, image_url=payload.image_url, category=payload.category, barcode=payload.barcode)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app.post("/api/inventory/check")
    async def check_inventory():
        await orchestrator.emit_event({"type": "inventory_check", "data": {}})
        return {"status": "inventory_check_queued"}

    # ══════════════════════════════════════════════════════════
    # SALES (connected: inventory deduct → order created → udhaar if credit → GST calculated)
    # ══════════════════════════════════════════════════════════

    @app.post("/api/inventory/sale")
    async def record_inventory_sale(payload: InventorySalePayload):
        """Record a sale: deducts inventory, creates order, handles udhaar if credit."""
        skill = _get_skill("inventory")
        if not skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")

        result = await skill.record_sale([item.model_dump() for item in payload.items])
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        # Emit stock events for threshold crossings
        for crossing in result.get("threshold_crossings", []):
            await orchestrator.emit_event({"type": "stock_update", "data": {"sku": crossing["sku"], "quantity": crossing["new_quantity"], "movement_type": "sale"}})

        # Build order items with totals
        inv_data = skill.inventory_data if hasattr(skill, 'inventory_data') else []
        inv_map = {i["sku"]: i for i in inv_data}
        order_items = []
        for item in payload.items:
            inv_item = inv_map.get(item.sku, {})
            price = inv_item.get("unit_price", 0)
            order_items.append({
                "sku": item.sku,
                "product_name": inv_item.get("product_name", item.sku),
                "qty": item.qty,
                "unit_price": price,
                "total": price * item.qty,
            })

        total_amount = sum(i["total"] for i in order_items)
        gst = _calc_gst(order_items, inv_data)
        order_id = f"ORD-C{int(time.time()) % 100000:05d}"

        new_order = {
            "order_id": order_id,
            "customer_id": payload.customer_id or "WALK-IN",
            "customer_name": payload.customer_name or "Walk-in Customer",
            "phone": payload.phone or "",
            "items": order_items,
            "total_amount": total_amount,
            "status": "delivered",
            "payment_method": payload.payment_method,
            "source": "counter",
            "gst_amount": gst,
            "timestamp": time.time(),
        }

        # Persist order
        orders = _read_json("mock_orders.json", {"customer_orders": [], "vendor_orders": []})
        orders["customer_orders"].append(new_order)
        _write_json("mock_orders.json", orders)

        # If udhaar, create/update credit entry
        if payload.payment_method == "Udhaar" and payload.customer_id:
            udhaar_list = _read_json("mock_udhaar.json", [])
            existing = next((u for u in udhaar_list if u["customer_id"] == payload.customer_id and u["balance"] > 0), None)

            entry = {
                "order_id": order_id,
                "date": time.strftime("%Y-%m-%d"),
                "items": [{"product_name": i["product_name"], "qty": i["qty"], "unit_price": i["unit_price"]} for i in order_items],
                "amount": total_amount,
                "type": "credit",
            }

            if existing:
                existing["entries"].append(entry)
                existing["total_credit"] += total_amount
                existing["balance"] += total_amount
                new_order["udhaar_id"] = existing["udhaar_id"]
            else:
                udhaar_id = f"UDH-{int(time.time()) % 100000:05d}"
                udhaar_list.append({
                    "udhaar_id": udhaar_id,
                    "customer_id": payload.customer_id,
                    "customer_name": payload.customer_name or "",
                    "phone": payload.phone or "",
                    "whatsapp_opted_in": True,
                    "entries": [entry],
                    "total_credit": total_amount,
                    "total_paid": 0,
                    "balance": total_amount,
                    "last_reminder_sent": None,
                    "created_at": time.strftime("%Y-%m-%d"),
                })
                new_order["udhaar_id"] = udhaar_id

            _write_json("mock_udhaar.json", udhaar_list)
            # Re-save order with udhaar_id
            _write_json("mock_orders.json", orders)

        # Update customer purchase history
        if payload.customer_id and payload.customer_id != "WALK-IN":
            customers = _read_json("mock_customers.json", [])
            for cust in customers:
                if cust["customer_id"] == payload.customer_id:
                    for oi in order_items:
                        cust["purchase_history"].append({
                            "product": oi["product_name"],
                            "category": inv_map.get(oi["sku"], {}).get("category", "Other"),
                            "quantity": oi["qty"],
                            "price": oi["unit_price"],
                            "timestamp": time.time(),
                        })
                    break
            _write_json("mock_customers.json", customers)

        result["order_id"] = order_id
        result["gst_amount"] = gst
        return result

    # ══════════════════════════════════════════════════════════
    # ORDERS (reads from unified orders file)
    # ══════════════════════════════════════════════════════════

    @app.get("/api/orders")
    async def get_orders():
        return _read_json("mock_orders.json", {"customer_orders": [], "vendor_orders": []})

    # ══════════════════════════════════════════════════════════
    # CUSTOMERS (enriched: purchase history from orders, udhaar balance)
    # ══════════════════════════════════════════════════════════

    @app.get("/api/customers")
    async def get_customers():
        customers = _read_json("mock_customers.json", [])
        udhaar_list = _read_json("mock_udhaar.json", [])
        orders = _read_json("mock_orders.json", {"customer_orders": [], "vendor_orders": []})
        returns = _read_json("mock_returns.json", [])
        udhaar_map = {u["customer_id"]: u for u in udhaar_list}
        orders_by_customer: dict[str, list[dict[str, Any]]] = {}
        returns_by_customer: dict[str, list[dict[str, Any]]] = {}

        for order in orders["customer_orders"]:
            orders_by_customer.setdefault(order.get("customer_id", ""), []).append(order)
        for return_entry in returns:
            returns_by_customer.setdefault(return_entry.get("customer_id", ""), []).append(return_entry)

        for cust in customers:
            u = udhaar_map.get(cust["customer_id"])
            cust["udhaar_balance"] = u["balance"] if u else 0
            cust["udhaar_id"] = u["udhaar_id"] if u else None
            cust["last_reminder_sent"] = u.get("last_reminder_sent") if u else None

            customer_orders = orders_by_customer.get(cust["customer_id"], [])
            customer_returns = returns_by_customer.get(cust["customer_id"], [])
            cust["order_count"] = len(customer_orders)
            cust["return_count"] = len(customer_returns)
            cust["total_order_value"] = round(sum(order.get("total_amount", 0) for order in customer_orders), 2)
            cust["returned_amount"] = round(
                sum(return_entry.get("refund_amount", 0) for return_entry in customer_returns if return_entry.get("status") == "processed"),
                2,
            )
            cust["net_spend"] = round(cust["total_order_value"] - cust["returned_amount"], 2)
            cust["last_order_at"] = max((order.get("timestamp", 0) for order in customer_orders), default=None)
            cust["last_return_at"] = max((return_entry.get("timestamp", 0) for return_entry in customer_returns), default=None)

        return customers

    # ══════════════════════════════════════════════════════════
    # UDHAAR / CREDIT TRACKING
    # ══════════════════════════════════════════════════════════

    @app.get("/api/udhaar")
    async def get_udhaar():
        return _read_json("mock_udhaar.json", [])

    @app.post("/api/udhaar/credit")
    async def record_udhaar_credit(payload: UdhaarCreditPayload):
        """Give credit to customer (standalone, without cart sale)."""
        udhaar_list = _read_json("mock_udhaar.json", [])
        existing = next((u for u in udhaar_list if u["customer_id"] == payload.customer_id and u["balance"] > 0), None)
        entry = {
            "order_id": None,
            "date": time.strftime("%Y-%m-%d"),
            "items": payload.items,
            "amount": payload.amount,
            "type": "credit",
        }
        if existing:
            existing["entries"].append(entry)
            existing["total_credit"] += payload.amount
            existing["balance"] += payload.amount
            udhaar_id = existing["udhaar_id"]
        else:
            udhaar_id = f"UDH-{int(time.time()) % 100000:05d}"
            udhaar_list.append({
                "udhaar_id": udhaar_id,
                "customer_id": payload.customer_id,
                "customer_name": payload.customer_name,
                "phone": payload.phone,
                "whatsapp_opted_in": True,
                "entries": [entry],
                "total_credit": payload.amount,
                "total_paid": 0,
                "balance": payload.amount,
                "last_reminder_sent": None,
                "created_at": time.strftime("%Y-%m-%d"),
            })
        _write_json("mock_udhaar.json", udhaar_list)
        return {"status": "credit_recorded", "udhaar_id": udhaar_id, "balance": next(u["balance"] for u in udhaar_list if u["udhaar_id"] == udhaar_id)}

    @app.post("/api/udhaar/payment")
    async def record_udhaar_payment(payload: UdhaarPaymentPayload):
        """Record a payment against udhaar balance."""
        udhaar_list = _read_json("mock_udhaar.json", [])
        for u in udhaar_list:
            if u["udhaar_id"] == payload.udhaar_id:
                u["entries"].append({
                    "order_id": None,
                    "date": time.strftime("%Y-%m-%d"),
                    "items": [],
                    "amount": payload.amount,
                    "type": "payment",
                    "note": payload.note or "Payment received",
                })
                u["total_paid"] += payload.amount
                u["balance"] = max(0, u["balance"] - payload.amount)
                _write_json("mock_udhaar.json", udhaar_list)
                return {"status": "payment_recorded", "udhaar_id": payload.udhaar_id, "new_balance": u["balance"]}
        raise HTTPException(status_code=404, detail="Udhaar record not found")

    @app.post("/api/udhaar/{udhaar_id}/remind")
    async def send_udhaar_reminder(udhaar_id: str):
        """Send WhatsApp reminder for udhaar balance."""
        udhaar_list = _read_json("mock_udhaar.json", [])
        for u in udhaar_list:
            if u["udhaar_id"] == udhaar_id:
                u["last_reminder_sent"] = time.strftime("%Y-%m-%d")
                _write_json("mock_udhaar.json", udhaar_list)
                msg = f"Namaste {u['customer_name']} ji! Aapka {u['customer_name']}'s kirana store mein Rs {u['balance']} baaki hai. Jab ho sake payment kar dijiye. Dhanyavaad!"
                return {
                    "status": "reminder_sent",
                    "phone": u["phone"],
                    "message": msg,
                    "whatsapp_link": f"https://wa.me/{u['phone'].replace('+', '')}?text={msg}",
                }
        raise HTTPException(status_code=404, detail="Udhaar record not found")

    # ══════════════════════════════════════════════════════════
    # RETURNS & REFUNDS (connected: restocks inventory, updates wastage, linked to order)
    # ══════════════════════════════════════════════════════════

    @app.get("/api/returns")
    async def get_returns():
        returns = _read_json("mock_returns.json", [])
        orders = _read_json("mock_orders.json", {"customer_orders": [], "vendor_orders": []})
        order_map = {order["order_id"]: order for order in orders["customer_orders"]}
        enriched = []
        for return_entry in returns:
            linked_order = order_map.get(return_entry.get("order_id"), {})
            enriched.append(
                {
                    **return_entry,
                    "linked_payment_method": linked_order.get("payment_method"),
                    "linked_order_total": linked_order.get("total_amount"),
                    "return_status": linked_order.get("return_status"),
                }
            )
        return sorted(enriched, key=lambda item: item.get("timestamp", 0), reverse=True)

    @app.post("/api/returns")
    async def record_return(payload: ReturnPayload):
        """Process return: restock or wastage, refund, update order."""
        returns = _read_json("mock_returns.json", [])
        refund_amount = sum(i.get("unit_price", 0) * i.get("qty", 1) for i in payload.items)

        return_entry = {
            "return_id": f"RET-{int(time.time()) % 100000:05d}",
            "order_id": payload.order_id,
            "customer_id": payload.customer_id,
            "customer_name": payload.customer_name,
            "items": payload.items,
            "refund_amount": refund_amount,
            "refund_method": payload.refund_method,
            "status": "processed",
            "timestamp": time.time(),
            "processed_at": time.time(),
        }
        return_entry = await _apply_return_effects(return_entry)
        returns.append(return_entry)
        _write_json("mock_returns.json", returns)
        return return_entry

    @app.post("/api/returns/{return_id}/process")
    async def process_return(return_id: str):
        returns = _read_json("mock_returns.json", [])
        for idx, return_entry in enumerate(returns):
            if return_entry["return_id"] != return_id:
                continue
            if return_entry.get("status") == "processed":
                return return_entry
            returns[idx] = await _apply_return_effects(return_entry)
            _write_json("mock_returns.json", returns)
            return returns[idx]
        raise HTTPException(status_code=404, detail="Return not found")

    # ══════════════════════════════════════════════════════════
    # SUPPLIER PAYMENTS (connected: updates vendor order payment_status)
    # ══════════════════════════════════════════════════════════

    @app.post("/api/vendor-orders/{order_id}/pay")
    async def mark_vendor_paid(order_id: str):
        """Mark a vendor order as paid."""
        orders = _read_json("mock_orders.json", {"customer_orders": [], "vendor_orders": []})
        for vo in orders["vendor_orders"]:
            if vo["order_id"] == order_id:
                if vo.get("payment_status") == "paid":
                    snapshot = _payment_due_snapshot(vo)
                    return {"status": "paid", "order_id": order_id, "payment_date": vo.get("payment_date"), **snapshot}
                vo["payment_status"] = "paid"
                vo["payment_date"] = time.strftime("%Y-%m-%d")
                _write_json("mock_orders.json", orders)
                snapshot = _payment_due_snapshot(vo)
                return {"status": "paid", "order_id": order_id, "payment_date": vo["payment_date"], **snapshot}
        raise HTTPException(status_code=404, detail="Vendor order not found")

    @app.get("/api/vendor-payments")
    async def get_vendor_payment_summary():
        """Summary of vendor payment statuses."""
        orders = _read_json("mock_orders.json", {"customer_orders": [], "vendor_orders": []})
        paid = [o for o in orders["vendor_orders"] if o.get("payment_status") == "paid"]
        unpaid = [o for o in orders["vendor_orders"] if o.get("payment_status") != "paid"]
        unpaid_details = []
        for order in unpaid:
            snapshot = _payment_due_snapshot(order)
            unpaid_details.append(
                {
                    "order_id": order["order_id"],
                    "supplier_name": order["supplier_name"],
                    "amount": order["total_amount"],
                    "delivery_date": order.get("delivery_date", ""),
                    **snapshot,
                }
            )
        overdue = [detail for detail in unpaid_details if detail["is_overdue"]]
        return {
            "total_paid": sum(o["total_amount"] for o in paid),
            "total_unpaid": sum(o["total_amount"] for o in unpaid),
            "paid_orders": len(paid),
            "unpaid_orders": len(unpaid),
            "overdue_orders": len(overdue),
            "overdue_amount": sum(detail["amount"] for detail in overdue),
            "unpaid_details": unpaid_details,
        }

    # ══════════════════════════════════════════════════════════
    # GST & BILLING
    # ══════════════════════════════════════════════════════════

    @app.get("/api/gst/summary")
    async def get_gst_summary():
        """Monthly GST summary: output tax (sales) - input tax (purchases) = net liability."""
        orders = _read_json("mock_orders.json", {"customer_orders": [], "vendor_orders": []})
        output_gst = sum(o.get("gst_amount", 0) for o in orders["customer_orders"])
        input_gst = sum(o.get("gst_amount", 0) for o in orders["vendor_orders"])
        returns = _read_json("mock_returns.json", [])
        refund_gst = round(sum(r["refund_amount"] for r in returns if r["status"] == "processed") * 0.05)

        return {
            "reporting_period": date.today().strftime("%B %Y"),
            "output_gst": output_gst,
            "input_gst": input_gst,
            "refund_adjustment": refund_gst,
            "net_liability": output_gst - input_gst - refund_gst,
            "total_sales": sum(o["total_amount"] for o in orders["customer_orders"]),
            "total_purchases": sum(o["total_amount"] for o in orders["vendor_orders"]),
            "total_returns": sum(r["refund_amount"] for r in returns if r["status"] == "processed"),
            "gst_rates": GST_RATES,
        }

    # ══════════════════════════════════════════════════════════
    # DAILY WHATSAPP SUMMARY
    # ══════════════════════════════════════════════════════════

    @app.get("/api/daily-summary")
    async def get_daily_summary():
        """Generate daily summary for WhatsApp push."""
        orders = _read_json("mock_orders.json", {"customer_orders": [], "vendor_orders": []})
        udhaar = _read_json("mock_udhaar.json", [])
        returns = _read_json("mock_returns.json", [])
        delivery = _read_json("mock_delivery_requests.json", [])
        summary_date = _latest_business_date(orders["customer_orders"], returns, delivery)
        filtered_orders = [o for o in orders["customer_orders"] if _order_business_date(o) == summary_date]
        filtered_returns = [r for r in returns if _return_business_date(r) == summary_date]
        filtered_delivery = [
            request for request in delivery if _business_date_from_value(request.get("requested_at")) == summary_date
        ]

        revenue = sum(o["total_amount"] for o in filtered_orders)
        procurement = sum(o["total_amount"] for o in orders["vendor_orders"] if _order_business_date(o) == summary_date)
        udhaar_outstanding = sum(u["balance"] for u in udhaar)
        pending_deliveries = len([d for d in delivery if d["status"] in ("pending", "accepted", "out_for_delivery")])
        pending_returns = len([r for r in returns if r["status"] == "pending"])
        unpaid_vendors = len([o for o in orders["vendor_orders"] if o.get("payment_status") != "paid"])
        pending_approvals = len(orchestrator.pending_approvals)

        # Find top selling product
        product_sales = {}
        for o in filtered_orders:
            for item in o["items"]:
                product_sales[item["product_name"]] = product_sales.get(item["product_name"], 0) + item["qty"]
        top_product = max(product_sales.items(), key=lambda x: x[1]) if product_sales else ("None", 0)

        # Critical stock
        skill = _get_skill("inventory")
        critical_items = []
        if skill:
            for item in skill.inventory_data:
                if item["current_stock"] <= item["reorder_threshold"]:
                    critical_items.append(item["product_name"])

        summary_text = f"""Good morning, Soham!

Store summary for {summary_date.strftime("%d %b %Y")}:

Revenue: Rs {revenue:,}
Procurement: Rs {procurement:,}
Profit: Rs {revenue - procurement:,}

Top seller: {top_product[0]} ({top_product[1]} units)

Udhaar outstanding: Rs {udhaar_outstanding:,}
Pending deliveries: {pending_deliveries}
Unpaid vendor bills: {unpaid_vendors}
Pending returns: {pending_returns}
Pending approvals: {pending_approvals}

{f"Low stock: {', '.join(critical_items[:5])}" if critical_items else "All stock levels healthy!"}

Open RetailOS for details."""

        phone = "+919876543210"
        return {
            "summary_date": summary_date.isoformat(),
            "summary": summary_text,
            "whatsapp_link": f"https://wa.me/{phone.replace('+', '')}?text={quote(summary_text[:500])}",
            "metrics": {
                "revenue": revenue,
                "procurement": procurement,
                "profit": revenue - procurement,
                "top_product": top_product[0],
                "udhaar_outstanding": udhaar_outstanding,
                "pending_deliveries": pending_deliveries,
                "unpaid_vendors": unpaid_vendors,
                "pending_approvals": pending_approvals,
                "returns_processed_today": len([r for r in filtered_returns if r.get("status") == "processed"]),
                "delivery_requests_today": len(filtered_delivery),
                "critical_stock_count": len(critical_items),
            },
        }

    # ══════════════════════════════════════════════════════════
    # VOICE COMMAND PARSING
    # ══════════════════════════════════════════════════════════

    @app.post("/api/voice/parse")
    async def parse_voice_command(payload: VoiceCommandPayload):
        """Parse a voice command and route to the right action."""
        text = payload.text.lower().strip()

        # Load inventory for matching
        skill = _get_skill("inventory")
        inv_data = _inventory_snapshot(skill)

        # Parse patterns
        # "add 20 units of Amul butter"
        add_match = re.search(r'(?:add|restock|stock)\s+(\d+)\s+(?:units?\s+(?:of\s+)?)?(.+)', text)
        if add_match:
            qty = int(add_match.group(1))
            product_query = add_match.group(2).strip()
            matched = _find_best_inventory_match(product_query, inv_data)
            if matched and skill:
                new_stock = matched["current_stock"] + qty
                await skill.update_stock(matched["sku"], new_stock)
                return {"action": "stock_update", "product": matched["product_name"], "sku": matched["sku"], "quantity_added": qty, "new_stock": new_stock, "message": f"Added {qty} units of {matched['product_name']}. New stock: {new_stock}"}
            return {"action": "not_found", "message": f"Could not find product matching '{product_query}'"}

        # "sell 3 maggi to Rahul"
        sell_match = re.search(r'(?:sell|sold|sale)\s+(\d+)\s+(.+?)(?:\s+to\s+(.+))?$', text)
        if sell_match:
            qty = int(sell_match.group(1))
            product_query = sell_match.group(2).strip()
            customer_name = (sell_match.group(3) or "").strip()
            matched = _find_best_inventory_match(product_query, inv_data)
            if matched:
                return {"action": "sale_ready", "product": matched["product_name"], "sku": matched["sku"], "qty": qty, "customer": customer_name, "message": f"Ready to sell {qty}x {matched['product_name']}" + (f" to {customer_name}" if customer_name else "")}
            return {"action": "not_found", "message": f"Could not find product matching '{product_query}'"}

        # "supplier late" / "delivery late"
        if "late" in text or "delayed" in text:
            supplier_match = re.search(r'(.+?)(?:\s+(?:delivered|is|was))?\s+(?:late|delayed)', text)
            supplier_name = supplier_match.group(1).strip() if supplier_match else text
            return {"action": "supplier_feedback", "supplier": supplier_name, "feedback": "late_delivery", "message": f"Logged: {supplier_name} — late delivery reported"}

        # "check stock" / "stock status"
        if "stock" in text and ("check" in text or "status" in text or "low" in text):
            low = [i for i in inv_data if i["current_stock"] <= i["reorder_threshold"]]
            return {"action": "stock_check", "low_stock_count": len(low), "items": [{"name": i["product_name"], "stock": i["current_stock"]} for i in low[:5]], "message": f"{len(low)} items are running low"}

        # "udhaar" / "credit"
        if "udhaar" in text or "credit" in text or "khata" in text:
            udhaar = _read_json("mock_udhaar.json", [])
            active = [u for u in udhaar if u["balance"] > 0]
            total = sum(u["balance"] for u in active)
            return {"action": "udhaar_summary", "active_accounts": len(active), "total_outstanding": total, "message": f"{len(active)} customers owe Rs {total:,} total"}

        return {"action": "unknown", "message": f"I didn't understand '{text}'. Try: 'add 20 Amul butter', 'sell 3 maggi', 'check stock', or 'udhaar status'"}

    @app.post("/api/voice/execute")
    async def execute_voice_command(payload: VoiceCommandPayload):
        parsed = await parse_voice_command(payload)
        action = parsed.get("action")

        if action == "stock_update":
            return {**parsed, "executed": True}

        if action == "supplier_feedback":
            suppliers = _read_json("mock_suppliers.json", [])
            supplier = next(
                (
                    record
                    for record in suppliers
                    if parsed.get("supplier", "").lower() in record.get("supplier_name", "").lower()
                ),
                None,
            )
            if orchestrator.audit:
                await orchestrator.audit.log(
                    skill="procurement",
                    event_type="voice_supplier_feedback",
                    decision=f"Voice note captured for {parsed.get('supplier')}",
                    reasoning="Store owner reported a delivery delay through voice input.",
                    outcome=json.dumps(
                        {
                            "supplier_name": supplier.get("supplier_name") if supplier else parsed.get("supplier"),
                            "supplier_id": supplier.get("supplier_id") if supplier else None,
                            "feedback": parsed.get("feedback"),
                        }
                    ),
                    status="warning",
                )
            return {
                **parsed,
                "executed": True,
                "supplier_id": supplier.get("supplier_id") if supplier else None,
            }

        return {**parsed, "executed": False}

    @app.post("/api/customer-assistant/query")
    async def customer_assistant_query(payload: CustomerAssistantPayload):
        inventory_skill = _get_skill("inventory")
        inventory = _inventory_snapshot(inventory_skill)
        shelf_data = _hydrate_shelf_assignments(
            _read_json("mock_shelf_zones.json", {"zones": [], "ai_suggestions": []}),
            persist=True,
        )
        store_profile = _load_store_profile()
        assistant_config = _load_assistant_config()
        response = await _answer_customer_assistant_query(payload.text, inventory, shelf_data, store_profile, assistant_config)
        _log_customer_assistant_query(payload.text, _normalize_customer_query(payload.text), response)
        return response

    @app.post("/api/customer-assistant/whatsapp-link")
    async def customer_assistant_whatsapp_link(payload: CustomerAssistantPayload):
        inventory_skill = _get_skill("inventory")
        inventory = _inventory_snapshot(inventory_skill)
        shelf_data = _hydrate_shelf_assignments(
            _read_json("mock_shelf_zones.json", {"zones": [], "ai_suggestions": []}),
            persist=True,
        )
        store_profile = _load_store_profile()
        assistant_config = _load_assistant_config()
        response = await _answer_customer_assistant_query(payload.text, inventory, shelf_data, store_profile, assistant_config)
        _log_customer_assistant_query(payload.text, _normalize_customer_query(payload.text), response)
        whatsapp_number = assistant_config.get("whatsapp_number") or store_profile.get("phone", "")
        message = response.get("answer", "")
        return {
            "status": "ready",
            "answer": message,
            "whatsapp_link": f"https://wa.me/{str(whatsapp_number).replace('+', '').replace(' ', '')}?text={quote(message[:500])}",
        }

    # ══════════════════════════════════════════════════════════
    # DELIVERY REQUESTS (connected: delivered → creates order → deducts inventory)
    # ══════════════════════════════════════════════════════════

    @app.get("/api/delivery-requests")
    async def get_delivery_requests():
        return _read_json("mock_delivery_requests.json", [])

    @app.patch("/api/delivery-requests/{request_id}/status")
    async def update_delivery_status(request_id: str, payload: DeliveryStatusPayload):
        requests = _read_json("mock_delivery_requests.json", [])
        for req in requests:
            if req["request_id"] == request_id:
                old_status = req["status"]
                req["status"] = payload.status
                _write_json("mock_delivery_requests.json", requests)

                # When marked as delivered → create order + deduct inventory
                if payload.status == "delivered" and old_status != "delivered":
                    order_items = []
                    for item in req["items"]:
                        order_items.append({
                            "sku": item["sku"],
                            "product_name": item["product_name"],
                            "qty": item["qty"],
                            "unit_price": item["unit_price"],
                            "total": item["qty"] * item["unit_price"],
                        })

                    skill = _get_skill("inventory")
                    inv_data = skill.inventory_data if skill else []
                    gst = _calc_gst(order_items, inv_data)
                    order_id = f"ORD-D{int(time.time()) % 100000:05d}"

                    new_order = {
                        "order_id": order_id,
                        "customer_id": req.get("customer_id", ""),
                        "customer_name": req["customer_name"],
                        "phone": req.get("phone", ""),
                        "items": order_items,
                        "total_amount": req["total_amount"],
                        "status": "delivered",
                        "payment_method": "Cash",
                        "source": "delivery",
                        "gst_amount": gst,
                        "timestamp": time.time(),
                    }

                    orders = _read_json("mock_orders.json", {"customer_orders": [], "vendor_orders": []})
                    orders["customer_orders"].append(new_order)
                    _write_json("mock_orders.json", orders)

                    # Deduct inventory
                    if skill:
                        sale_result = await skill.record_sale([{"sku": i["sku"], "qty": i["qty"]} for i in req["items"]])
                        for crossing in sale_result.get("threshold_crossings", []):
                            await orchestrator.emit_event(
                                {
                                    "type": "stock_update",
                                    "data": {
                                        "sku": crossing["sku"],
                                        "quantity": crossing["new_quantity"],
                                        "movement_type": "sale",
                                    },
                                }
                            )

                return {"status": "updated", "request_id": request_id, "new_status": payload.status}
        raise HTTPException(status_code=404, detail=f"Request '{request_id}' not found")

    # ══════════════════════════════════════════════════════════
    # SHELF ZONES
    # ══════════════════════════════════════════════════════════

    @app.get("/api/shelf-zones")
    async def get_shelf_zones():
        from brain.velocity_analyzer import classify_velocity
        data = _read_json("mock_shelf_zones.json", {"zones": [], "ai_suggestions": []})
        data = _hydrate_shelf_assignments(data, persist=True)
        # Enrich with live stock data and velocity classification
        skill = _get_skill("inventory")
        if skill:
            inv_map = {i["sku"]: i for i in skill.inventory_data}
            for zone in data["zones"]:
                for product in zone["products"]:
                    inv = inv_map.get(product["sku"])
                    if inv:
                        product["current_stock"] = inv["current_stock"]
                        product["daily_sales_rate"] = inv["daily_sales_rate"]
                        product["velocity_classification"] = classify_velocity(inv["daily_sales_rate"])
        return data

    @app.get("/api/shelf-zones/velocity")
    async def get_shelf_velocity():
        from brain.velocity_analyzer import get_velocity_report
        return get_velocity_report()

    @app.post("/api/shelf-zones/zones")
    async def create_shelf_zone(payload: dict):
        data = _read_json("mock_shelf_zones.json", {"zones": [], "ai_suggestions": []})
        # Generate next zone ID
        existing_ids = [z["zone_id"] for z in data["zones"]]
        max_num = 0
        for zid in existing_ids:
            try:
                max_num = max(max_num, int(zid.split("-")[1]))
            except (IndexError, ValueError):
                pass
        new_id = f"Z-{max_num + 1:02d}"

        zone_type = payload.get("zone_type", "standard")
        if zone_type not in ("high_traffic", "refrigerated", "freezer", "standard"):
            raise HTTPException(status_code=400, detail="Invalid zone_type")

        new_zone = {
            "zone_id": new_id,
            "zone_name": payload.get("zone_name", f"Zone {new_id}"),
            "zone_type": zone_type,
            "total_slots": payload.get("total_slots", 6),
            "shelves": payload.get("shelves", []),
            "products": [],
        }
        data["zones"].append(new_zone)
        _write_json("mock_shelf_zones.json", data)
        return new_zone

    @app.put("/api/shelf-zones/zones/{zone_id}")
    async def update_shelf_zone(zone_id: str, payload: dict):
        data = _read_json("mock_shelf_zones.json", {"zones": [], "ai_suggestions": []})
        for zone in data["zones"]:
            if zone["zone_id"] == zone_id:
                if "zone_name" in payload:
                    zone["zone_name"] = payload["zone_name"]
                if "zone_type" in payload:
                    if payload["zone_type"] not in ("high_traffic", "refrigerated", "freezer", "standard"):
                        raise HTTPException(status_code=400, detail="Invalid zone_type")
                    zone["zone_type"] = payload["zone_type"]
                if "total_slots" in payload:
                    if payload["total_slots"] < len(zone["products"]):
                        raise HTTPException(status_code=400, detail="Cannot reduce slots below current product count")
                    zone["total_slots"] = payload["total_slots"]
                if "shelves" in payload:
                    zone["shelves"] = payload["shelves"]
                _write_json("mock_shelf_zones.json", data)
                return zone
        raise HTTPException(status_code=404, detail="Zone not found")

    @app.delete("/api/shelf-zones/zones/{zone_id}")
    async def delete_shelf_zone(zone_id: str):
        data = _read_json("mock_shelf_zones.json", {"zones": [], "ai_suggestions": []})
        for i, zone in enumerate(data["zones"]):
            if zone["zone_id"] == zone_id:
                if zone["products"]:
                    raise HTTPException(status_code=400, detail="Cannot delete zone with products. Remove products first.")
                data["zones"].pop(i)
                _write_json("mock_shelf_zones.json", data)
                return {"status": "deleted", "zone_id": zone_id}
        raise HTTPException(status_code=404, detail="Zone not found")

    @app.post("/api/shelf-zones/zones/{zone_id}/assign")
    async def assign_product_to_zone(zone_id: str, payload: dict):
        data = _read_json("mock_shelf_zones.json", {"zones": [], "ai_suggestions": []})
        data = _hydrate_shelf_assignments(data)
        sku = payload.get("sku")
        if not sku:
            raise HTTPException(status_code=400, detail="sku is required")

        # Check if product already placed in any zone
        for zone in data["zones"]:
            for p in zone["products"]:
                if p["sku"] == sku:
                    raise HTTPException(status_code=409, detail=f"Product {sku} already placed in {zone['zone_id']}")

        for zone in data["zones"]:
            if zone["zone_id"] == zone_id:
                if len(zone["products"]) >= zone["total_slots"]:
                    raise HTTPException(status_code=400, detail="Zone is full")

                shelf_level = payload.get("shelf_level", "lower")
                shelf = _resolve_zone_shelf(zone, shelf_level, payload.get("shelf_id"))

                # Get daily_sales_rate from inventory
                daily_rate = 0
                skill = _get_skill("inventory")
                if skill:
                    inv_map = {i["sku"]: i for i in skill.inventory_data}
                    inv = inv_map.get(sku)
                    if inv:
                        daily_rate = inv["daily_sales_rate"]

                new_product = {
                    "sku": sku,
                    "product_name": payload.get("product_name", sku),
                    "placed_date": date.today().isoformat(),
                    "days_here": 0,
                    "daily_sales_rate": daily_rate,
                    "shelf_level": shelf_level,
                    "shelf_id": shelf.get("shelf_id") if shelf else None,
                    "shelf_name": shelf.get("shelf_name") if shelf else None,
                }
                zone["products"].append(new_product)
                _write_json("mock_shelf_zones.json", data)
                return new_product
        raise HTTPException(status_code=404, detail="Zone not found")

    @app.delete("/api/shelf-zones/zones/{zone_id}/products/{sku}")
    async def remove_product_from_zone(zone_id: str, sku: str):
        data = _read_json("mock_shelf_zones.json", {"zones": [], "ai_suggestions": []})
        for zone in data["zones"]:
            if zone["zone_id"] == zone_id:
                for i, p in enumerate(zone["products"]):
                    if p["sku"] == sku:
                        removed = zone["products"].pop(i)
                        _write_json("mock_shelf_zones.json", data)
                        return {"status": "removed", "product": removed}
                raise HTTPException(status_code=404, detail="Product not found in zone")
        raise HTTPException(status_code=404, detail="Zone not found")

    @app.post("/api/shelf-zones/optimize")
    async def trigger_shelf_optimization():
        await orchestrator.emit_event({"type": "shelf_optimization", "data": {}})
        return {"status": "optimization_triggered", "message": "AI shelf optimization started. Check approvals queue for suggestions."}

    # ══════════════════════════════════════════════════════════
    # SUPPLIERS
    # ══════════════════════════════════════════════════════════

    @app.get("/api/suppliers")
    async def get_suppliers():
        from brain.trust_scorer import get_trust_score
        suppliers = _read_json("mock_suppliers.json", [])
        enriched = []
        for s in suppliers:
            trust = get_trust_score(s["supplier_id"])
            enriched.append({**s, "trust_score": trust["score"], "trust_breakdown": trust.get("breakdown", {})})
        return enriched

    @app.post("/api/suppliers/register")
    async def register_supplier(payload: SupplierRegisterPayload):
        suppliers = _read_json("mock_suppliers.json", [])
        for s in suppliers:
            if s["supplier_id"] == payload.supplier_id:
                raise HTTPException(status_code=409, detail="Supplier ID already exists")
        new_supplier = {
            "supplier_id": payload.supplier_id,
            "supplier_name": payload.supplier_name,
            "contact_phone": payload.contact_phone,
            "products": payload.products,
            "categories": payload.categories,
            "price_per_unit": payload.price_per_unit,
            "reliability_score": 3.0,
            "delivery_days": payload.delivery_days,
            "min_order_qty": payload.min_order_qty,
            "payment_terms": payload.payment_terms,
            "location": payload.location,
        }
        suppliers.append(new_supplier)
        _write_json("mock_suppliers.json", suppliers)
        return {"status": "registered", "supplier": new_supplier}

    @app.get("/api/suppliers/{supplier_id}/history")
    async def get_supplier_history(supplier_id: str):
        from brain.trust_scorer import get_trust_score
        from brain.decision_logger import _get_connection
        trust = get_trust_score(supplier_id)
        decisions = []
        try:
            with _get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT amount, status, timestamp FROM decisions WHERE supplier_id = ? ORDER BY timestamp DESC LIMIT 20", (supplier_id,))
                decisions = [{"amount": r[0], "status": r[1], "timestamp": r[2]} for r in cursor.fetchall()]
        except Exception:
            pass
        return {"trust": trust, "decisions": decisions}

    # ══════════════════════════════════════════════════════════
    # EXISTING ENDPOINTS (unchanged)
    # ══════════════════════════════════════════════════════════

    @app.post("/api/webhook/supplier-reply")
    async def supplier_reply_webhook(payload: SupplierReplyPayload):
        await orchestrator.emit_event({"type": "supplier_reply", "data": {"negotiation_id": payload.negotiation_id, "supplier_id": payload.supplier_id, "supplier_name": payload.supplier_name, "message": payload.message, "product_name": payload.product_name}})
        return {"status": "reply_queued"}

    @app.post("/api/demo/supplier-reply")
    async def mock_supplier_reply(payload: SupplierReplyPayload):
        negotiation_skill = _get_skill("negotiation")
        if not negotiation_skill:
            raise HTTPException(status_code=404, detail="Negotiation skill not loaded")
        result = await negotiation_skill._handle_reply({"negotiation_id": payload.negotiation_id, "supplier_id": payload.supplier_id, "supplier_name": payload.supplier_name, "message": payload.message, "product_name": payload.product_name})
        if result.get("needs_approval"):
            orchestrator.pending_approvals[result["approval_id"]] = {"skill": "negotiation", "result": result, "event": {"type": "supplier_reply"}, "timestamp": time.time()}
        return result

    @app.get("/api/approvals")
    async def get_approvals():
        return orchestrator.get_pending_approvals()

    @app.post("/api/approvals/approve")
    async def approve_action(payload: ApprovalPayload):
        result = await orchestrator.approve(payload.approval_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app.post("/api/approvals/reject")
    async def reject_action(payload: ApprovalPayload):
        result = await orchestrator.reject(payload.approval_id, payload.reason)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app.get("/api/audit")
    async def get_audit_logs(skill: str | None = None, event_type: str | None = None, limit: int = 50, offset: int = 0):
        return await orchestrator.audit.get_logs(skill=skill, event_type=event_type, limit=limit, offset=offset)

    @app.get("/api/audit/count")
    async def get_audit_count():
        return {"count": await orchestrator.audit.get_log_count()}

    @app.get("/api/negotiations")
    async def get_negotiations():
        skill = _get_skill("negotiation")
        if not skill:
            raise HTTPException(status_code=404, detail="Negotiation skill not loaded")
        return {"active": skill.active_negotiations, "message_log": skill.message_log[-50:]}

    @app.post("/api/analytics/run")
    async def run_analytics():
        await orchestrator.emit_event({"type": "daily_analytics", "data": {}})
        return {"status": "analytics_queued"}

    @app.get("/api/analytics/summary")
    async def get_analytics_summary():
        if orchestrator.memory:
            summary = await orchestrator.memory.get("orchestrator:daily_summary")
            return summary or {"message": "No analytics summary available yet"}
        return {"message": "Memory not available"}

    @app.post("/api/demo/trigger-flow")
    async def trigger_demo_flow():
        inventory_skill = _get_skill("inventory")
        if not inventory_skill:
            raise HTTPException(status_code=404, detail="Inventory skill not loaded")

        async def _run_demo():
            try:
                await orchestrator.audit.log(skill="orchestrator", event_type="demo_started", decision="Demo started — Ice cream stock dropping to critical", reasoning="Owner triggered the live demo flow", outcome="Stock will drop to 5 units", status="success")
                await inventory_skill.update_stock("SKU-001", 5)
                await asyncio.sleep(2)
                await orchestrator.audit.log(skill="inventory", event_type="low_stock_detected", decision="Ice cream stock critically low — only 5 units left!", reasoning="Stock dropped below reorder threshold of 20 units", outcome=json.dumps({"sku": "SKU-001", "product_name": "Amul Vanilla Ice Cream", "quantity": 5, "threshold": 20}), status="alert")
                await asyncio.sleep(2)
                await orchestrator.audit.log(skill="procurement", event_type="supplier_ranking", decision="Evaluated 5 suppliers — FreshFreeze Distributors is the best option", reasoning="Ranked by composite score: price 145/unit, reliability 4.8/5, next-day delivery, good trust score (94%)", outcome=json.dumps([{"rank": 1, "supplier_name": "FreshFreeze Distributors", "price_per_unit": 145, "delivery_days": 1}, {"rank": 2, "supplier_name": "CoolChain India", "price_per_unit": 155, "delivery_days": 2}]), status="success")
                await asyncio.sleep(2)
                await orchestrator.audit.log(skill="negotiation", event_type="outreach_sent", decision="Sent WhatsApp message to FreshFreeze Distributors", reasoning="Top-ranked supplier for ice cream procurement", outcome="Message sent via WhatsApp Business API", status="success", metadata={"supplier_id": "SUP-001"})
                await asyncio.sleep(2)
                await orchestrator.audit.log(skill="negotiation", event_type="reply_parsed", decision="Supplier replied: 50 boxes at 145/unit, delivery tomorrow, COD accepted", reasoning="Parsed WhatsApp reply from FreshFreeze — deal is within budget (saving 2,500 vs usual price)", outcome=json.dumps({"supplier": "FreshFreeze Distributors", "price_per_unit": 145, "quantity": 50, "delivery": "tomorrow", "terms": "COD"}), status="success")
                await asyncio.sleep(2)
                approval_id = f"demo_procurement_SKU-001_{int(time.time())}"
                orchestrator.pending_approvals[approval_id] = {"id": approval_id, "skill": "negotiation", "reason": "I found a better price for Amul Vanilla Ice Cream!", "result": {"product_name": "Amul Vanilla Ice Cream", "sku": "SKU-001", "negotiation_id": f"neg_demo_{int(time.time())}", "top_supplier": {"supplier_id": "SUP-001", "supplier_name": "FreshFreeze Distributors", "price_per_unit": 145, "delivery_days": 1, "min_order_qty": 30}, "parsed": {"price_per_unit": 145, "quantity": 50, "delivery": "tomorrow"}}, "event": {"type": "supplier_reply"}, "timestamp": time.time()}
                await orchestrator.audit.log(skill="orchestrator", event_type="approval_requested", decision="Deal ready! Waiting for your approval on the Approvals tab", reasoning="FreshFreeze offered 145/unit for 50 boxes of ice cream with next-day delivery. Saving 2,500 vs usual supplier.", outcome="Approval card created — tap YES to order", status="pending")
            except Exception as e:
                await orchestrator.audit.log(skill="orchestrator", event_type="demo_error", decision="Demo flow encountered an error", reasoning=str(e), outcome="Some steps may not have completed", status="error")

        asyncio.create_task(_run_demo())
        return {"status": "demo_flow_triggered", "message": "Demo started! Watch the Dashboard tab for live events."}

    @app.get("/api/inventory/expiry-risks")
    async def get_expiry_risks():
        from brain.expiry_alerter import get_expiry_risks
        try:
            items = _read_json("mock_inventory.json", [])
            risks = get_expiry_risks(items)
            return [r.get("data", r) for r in risks]
        except Exception:
            return []

    @app.get("/api/market-prices")
    async def get_all_market_prices():
        from brain.price_monitor import get_market_reference
        skill = _get_skill("inventory")
        if not skill:
            return []
        results = []
        for item in skill.inventory_data:
            ref = get_market_reference(item["sku"])
            if ref.get("median_price") is not None:
                results.append({"sku": item["sku"], "product_name": item["product_name"], **ref})
        return results

    @app.get("/api/market-prices/{sku}")
    async def get_market_price(sku: str):
        from brain.price_monitor import get_market_reference
        return get_market_reference(sku)

    @app.post("/api/market-prices/log")
    async def log_market_price(payload: MarketPriceLogPayload):
        from brain.price_monitor import log_manual_price
        log_manual_price(payload.product_id, payload.source_name, payload.price_per_unit, payload.unit)
        return {"status": "logged"}

    @app.get("/api/alerts")
    async def get_alerts(limit: int = 50):
        cutoff = time.time() - 48 * 3600
        all_logs = await orchestrator.audit.get_logs(limit=200)
        alerts = [log for log in all_logs if log.get("status") in ("alert", "critical", "escalated", "pending") and log.get("timestamp", 0) >= cutoff]
        return alerts[:limit]

    return app
