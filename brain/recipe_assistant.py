import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from runtime.llm_client import get_llm_client
from runtime.utils import extract_json_from_llm

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_PATH = DATA_DIR / "recipe_cache.json"
CACHE_TTL_SECONDS = 6 * 60 * 60

RECIPE_PARSE_PROMPT = """You are helping a retail customer recipe assistant for an Indian grocery store.

Given a customer's request for a dish, infer the most likely base recipe ingredients.

Rules:
1. Return valid JSON only.
2. Prefer generic ingredient names, not brand names.
3. Keep the ingredient list practical for a neighborhood grocery store.
4. Mark uncertain extras as optional rather than required.
5. If the dish is ambiguous, choose a common base version and note that in `notes`.
6. Keep the ingredient list between 4 and 12 items.

Return this shape:
{
  "dish_name": "string",
  "notes": "string",
  "ingredients": [
    {
      "name": "string",
      "quantity_hint": "string",
      "category_hint": "string",
      "is_optional": false
    }
  ]
}
"""

FALLBACK_RECIPES = {
    "spaghetti tomato": {
        "dish_name": "Spaghetti with tomato sauce",
        "notes": "Using a basic tomato spaghetti recipe.",
        "ingredients": [
            {"name": "spaghetti pasta", "quantity_hint": "1 pack", "category_hint": "Grocery", "is_optional": False},
            {"name": "tomato", "quantity_hint": "4 to 5", "category_hint": "Produce", "is_optional": False},
            {"name": "onion", "quantity_hint": "1 medium", "category_hint": "Produce", "is_optional": False},
            {"name": "garlic", "quantity_hint": "4 cloves", "category_hint": "Produce", "is_optional": False},
            {"name": "cooking oil", "quantity_hint": "2 tbsp", "category_hint": "Grocery", "is_optional": False},
            {"name": "salt", "quantity_hint": "to taste", "category_hint": "Grocery", "is_optional": False},
            {"name": "chilli flakes", "quantity_hint": "1 tsp", "category_hint": "Grocery", "is_optional": True},
        ],
    },
    "paneer butter masala": {
        "dish_name": "Paneer Butter Masala",
        "notes": "Using a standard North Indian home-style version.",
        "ingredients": [
            {"name": "paneer", "quantity_hint": "200 g", "category_hint": "Dairy", "is_optional": False},
            {"name": "tomato", "quantity_hint": "4", "category_hint": "Produce", "is_optional": False},
            {"name": "onion", "quantity_hint": "1", "category_hint": "Produce", "is_optional": False},
            {"name": "butter", "quantity_hint": "2 tbsp", "category_hint": "Dairy", "is_optional": False},
            {"name": "cream", "quantity_hint": "small pack", "category_hint": "Dairy", "is_optional": True},
            {"name": "garlic", "quantity_hint": "4 cloves", "category_hint": "Produce", "is_optional": False},
            {"name": "ginger", "quantity_hint": "1 inch", "category_hint": "Produce", "is_optional": False},
            {"name": "garam masala", "quantity_hint": "1 tsp", "category_hint": "Grocery", "is_optional": False},
        ],
    },
    "chai": {
        "dish_name": "Masala Chai",
        "notes": "Using a simple daily chai version.",
        "ingredients": [
            {"name": "tea", "quantity_hint": "1 pack", "category_hint": "Beverages", "is_optional": False},
            {"name": "milk", "quantity_hint": "1 litre", "category_hint": "Dairy", "is_optional": False},
            {"name": "sugar", "quantity_hint": "to taste", "category_hint": "Grocery", "is_optional": False},
            {"name": "ginger", "quantity_hint": "small piece", "category_hint": "Produce", "is_optional": True},
            {"name": "cardamom", "quantity_hint": "2 pods", "category_hint": "Grocery", "is_optional": True},
        ],
    },
    "omelette": {
        "dish_name": "Masala Omelette",
        "notes": "Using a simple egg omelette recipe.",
        "ingredients": [
            {"name": "eggs", "quantity_hint": "4", "category_hint": "Dairy", "is_optional": False},
            {"name": "onion", "quantity_hint": "1 small", "category_hint": "Produce", "is_optional": True},
            {"name": "green chilli", "quantity_hint": "1", "category_hint": "Produce", "is_optional": True},
            {"name": "salt", "quantity_hint": "to taste", "category_hint": "Grocery", "is_optional": False},
            {"name": "cooking oil", "quantity_hint": "1 tbsp", "category_hint": "Grocery", "is_optional": False},
        ],
    },
}


def _normalize_recipe_key(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in value)
    return " ".join(normalized.split())


def _load_cache() -> dict[str, Any]:
    try:
        with open(CACHE_PATH, "r") as file:
            return json.load(file)
    except Exception:
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    with open(CACHE_PATH, "w") as file:
        json.dump(cache, file, indent=2)
        file.write("\n")


def _fallback_recipe(query: str) -> dict[str, Any]:
    normalized = _normalize_recipe_key(query)

    if normalized in FALLBACK_RECIPES:
        return FALLBACK_RECIPES[normalized]

    for key, recipe in FALLBACK_RECIPES.items():
        if normalized in key or key in normalized:
            return recipe

    dish_name = normalized.title() if normalized else "Requested recipe"
    return {
        "dish_name": dish_name,
        "notes": "Using a simple pantry-oriented ingredient guess because Gemini was unavailable.",
        "ingredients": [
            {"name": normalized, "quantity_hint": "1", "category_hint": "Grocery", "is_optional": False},
            {"name": "salt", "quantity_hint": "to taste", "category_hint": "Grocery", "is_optional": False},
            {"name": "cooking oil", "quantity_hint": "as needed", "category_hint": "Grocery", "is_optional": False},
        ],
    }


async def parse_recipe_request(text: str) -> dict[str, Any]:
    normalized = _normalize_recipe_key(text)
    cache = _load_cache()
    cached = cache.get(normalized)
    now = time.time()

    if cached and now - cached.get("timestamp", 0) < CACHE_TTL_SECONDS:
        return cached["data"]

    llm = get_llm_client()
    prompt = f"{RECIPE_PARSE_PROMPT}\n\nCustomer request: {text}\n"

    try:
        response_text = await llm.generate(prompt, timeout=30)
        parsed = extract_json_from_llm(response_text)
        ingredients = parsed.get("ingredients") or []
        if not parsed.get("dish_name") or not ingredients:
            raise ValueError("Gemini returned incomplete recipe data")

        recipe = {
            "dish_name": parsed.get("dish_name"),
            "notes": parsed.get("notes", ""),
            "ingredients": [
                {
                    "name": ingredient.get("name", "").strip(),
                    "quantity_hint": ingredient.get("quantity_hint", ""),
                    "category_hint": ingredient.get("category_hint", ""),
                    "is_optional": bool(ingredient.get("is_optional", False)),
                }
                for ingredient in ingredients
                if ingredient.get("name")
            ],
        }
        if not recipe["ingredients"]:
            raise ValueError("Gemini recipe ingredient list was empty")

        cache[normalized] = {"timestamp": now, "data": recipe}
        _save_cache(cache)
        return recipe
    except Exception as error:
        logger.warning("Recipe parsing failed, using fallback: %s", error)
        recipe = _fallback_recipe(text)
        cache[normalized] = {"timestamp": now, "data": recipe}
        _save_cache(cache)
        return recipe
