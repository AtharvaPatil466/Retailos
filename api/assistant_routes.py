"""Voice Assistant API — Gemini-powered conversational assistant for store owners.

Unlike the basic voice_input module (regex pattern matching), this uses
Gemini with full store context to answer complex queries like:
- "How's my store doing today?"
- "Which supplier should I use for rice?"
- "Remind me about pending approvals"
- "कल कितनी बिक्री हुई?" (How much was sold yesterday?)

The assistant has access to live inventory, orders, suppliers, and analytics.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from auth.dependencies import require_role
from db.models import User

router = APIRouter(prefix="/api/assistant", tags=["voice-assistant"])

_data_dir = Path(__file__).resolve().parent.parent / "data"


def _read_json(filename: str, default=None):
    try:
        with open(_data_dir / filename, "r") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []


def _write_json(filename: str, data: Any) -> None:
    with open(_data_dir / filename, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


class AssistantQuery(BaseModel):
    text: str
    language: str = "en"
    conversation_id: str = ""
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"text": "How's my store doing today?", "language": "en"},
        {"text": "कौन सा supplier सबसे अच्छा है rice के लिए?", "language": "hi"},
        {"text": "Show me low stock items", "language": "en"},
    ]})


# Conversation history for multi-turn context (in-memory, per session)
_conversations: dict[str, list[dict]] = {}

LOOKUP_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "is",
    "my",
    "of",
    "please",
    "show",
    "the",
    "to",
    "with",
}


def _normalize_lookup_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _lookup_tokens(value: str) -> list[str]:
    return [token for token in _normalize_lookup_text(value).split() if token and token not in LOOKUP_STOPWORDS]


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

    overlap = len([token for token in query_tokens if token in name_tokens or token == normalized_sku])
    if overlap:
        score += overlap * 20

    return score


def _find_best_inventory_match(query: str, inventory: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not query.strip():
        return None

    scored: list[tuple[int, dict[str, Any]]] = []
    for item in inventory:
        score = _score_inventory_match(query, item)
        if score > 0:
            scored.append((score, item))

    if not scored:
        return None

    scored.sort(
        key=lambda entry: (
            entry[0],
            entry[1].get("daily_sales_rate", 0),
            entry[1].get("current_stock", 0),
        ),
        reverse=True,
    )
    return scored[0][1] if scored[0][0] >= 40 else None


def _latest_orders_snapshot(orders: dict[str, Any]) -> list[dict[str, Any]]:
    customer_orders = orders.get("customer_orders", [])
    if not customer_orders:
        return []

    latest_timestamp = max(order.get("timestamp", 0) for order in customer_orders)
    latest_day = time.strftime("%Y-%m-%d", time.localtime(latest_timestamp))
    return [
        order
        for order in customer_orders
        if time.strftime("%Y-%m-%d", time.localtime(order.get("timestamp", 0))) == latest_day
    ]


def _fallback_assistant_reply(text: str, conversation_id: str) -> dict[str, Any]:
    text = text.strip()
    text_lower = text.lower()
    inventory = _read_json("mock_inventory.json", [])
    orders = _read_json("mock_orders.json", {"customer_orders": [], "vendor_orders": []})
    suppliers = _read_json("mock_suppliers.json", [])
    udhaar = _read_json("mock_udhaar.json", [])

    add_match = re.search(r"(?:add|restock|stock)\s+(\d+)\s+(?:units?\s+(?:of\s+)?)?(.+)", text_lower)
    if add_match:
        qty = int(add_match.group(1))
        product_query = add_match.group(2).strip()
        matched = _find_best_inventory_match(product_query, inventory)
        if matched:
            updated_inventory = []
            new_stock = matched.get("current_stock", 0) + qty
            for item in inventory:
                if item.get("sku") == matched.get("sku"):
                    updated_inventory.append({**item, "current_stock": new_stock})
                else:
                    updated_inventory.append(item)
            _write_json("mock_inventory.json", updated_inventory)
            return {
                "response": f"Added {qty} units of {matched['product_name']}. New stock: {new_stock}",
                "actions": [{"type": "navigate", "target": "inventory", "label": "View Inventory"}],
                "conversation_id": conversation_id,
                "mode": "fallback",
            }
        return {
            "response": f"Could not find a product matching '{product_query}'.",
            "actions": [{"type": "navigate", "target": "inventory", "label": "Check Inventory"}],
            "conversation_id": conversation_id,
            "mode": "fallback",
        }

    sell_match = re.search(r"(?:sell|sold|sale)\s+(\d+)\s+(.+?)(?:\s+to\s+(.+))?$", text_lower)
    if sell_match:
        qty = int(sell_match.group(1))
        product_query = sell_match.group(2).strip()
        customer_name = (sell_match.group(3) or "").strip()
        matched = _find_best_inventory_match(product_query, inventory)
        if matched:
            response = f"Ready to sell {qty}x {matched['product_name']}"
            if customer_name:
                response += f" to {customer_name}"
            return {
                "response": response,
                "actions": [{"type": "navigate", "target": "cart", "label": "Open Cart"}],
                "conversation_id": conversation_id,
                "mode": "fallback",
            }

    if "late" in text_lower or "delayed" in text_lower:
        supplier_match = re.search(r"(.+?)(?:\s+(?:delivered|is|was))?\s+(?:late|delayed)", text_lower)
        supplier_name = supplier_match.group(1).strip() if supplier_match else text
        return {
            "response": f"Logged supplier feedback: {supplier_name} had a late delivery.",
            "actions": [{"type": "navigate", "target": "suppliers", "label": "View Suppliers"}],
            "conversation_id": conversation_id,
            "mode": "fallback",
        }

    if (
        "running low" in text_lower
        or "low stock" in text_lower
        or ("stock" in text_lower and any(keyword in text_lower for keyword in ("check", "status", "low")))
    ):
        low_stock = [
            item for item in inventory if item.get("current_stock", 0) <= item.get("reorder_threshold", 0)
        ]
        if low_stock:
            response = f"{len(low_stock)} items are running low:\n" + "\n".join(
                f"• {item['product_name']} ({item.get('current_stock', 0)} left)"
                for item in low_stock[:5]
            )
        else:
            response = "Stock levels look healthy right now."
        return {
            "response": response,
            "actions": [{"type": "navigate", "target": "inventory", "label": "View Inventory"}],
            "conversation_id": conversation_id,
            "mode": "fallback",
        }

    product_stock_match = re.search(
        r"(?:check|show|what(?:'s| is))\s+(?:the\s+)?stock(?:\s+of)?\s+(.+)$",
        text_lower,
    )
    if product_stock_match:
        product_query = product_stock_match.group(1).strip()
        matched = _find_best_inventory_match(product_query, inventory)
        if matched:
            return {
                "response": (
                    f"{matched['product_name']} has {matched.get('current_stock', 0)} units in stock. "
                    f"Reorder threshold: {matched.get('reorder_threshold', 0)}."
                ),
                "actions": [{"type": "navigate", "target": "inventory", "label": "View Inventory"}],
                "conversation_id": conversation_id,
                "mode": "fallback",
            }

    if "udhaar" in text_lower or "credit" in text_lower or "khata" in text_lower:
        active_accounts = [entry for entry in udhaar if entry.get("balance", 0) > 0]
        total = sum(entry.get("balance", 0) for entry in active_accounts)
        return {
            "response": f"{len(active_accounts)} customers owe Rs {total:,.0f} in total.",
            "actions": [{"type": "navigate", "target": "customers", "label": "View Customers"}],
            "conversation_id": conversation_id,
            "mode": "fallback",
        }

    if any(keyword in text_lower for keyword in ("how", "today", "summary", "overview")) and "store" in text_lower:
        latest_orders = _latest_orders_snapshot(orders)
        revenue = sum(order.get("total_amount", 0) for order in latest_orders)
        items_sold = sum(item.get("qty", 0) for order in latest_orders for item in order.get("items", []))
        total_orders = len(latest_orders)
        total_udhaar = sum(entry.get("balance", 0) for entry in udhaar)
        response = (
            "Here’s your latest store snapshot:\n"
            f"• Revenue: Rs {revenue:,.0f}\n"
            f"• Orders: {total_orders}\n"
            f"• Items sold: {items_sold}\n"
            f"• Udhaar outstanding: Rs {total_udhaar:,.0f}"
        )
        return {
            "response": response,
            "actions": [{"type": "navigate", "target": "home", "label": "Dashboard"}],
            "conversation_id": conversation_id,
            "mode": "fallback",
        }

    if any(keyword in text_lower for keyword in ("approval", "pending", "approve")):
        approvals = _read_json("approvals.json", [])
        pending = [entry for entry in approvals if entry.get("status") == "pending"]
        response = f"You have {len(pending)} pending approval{'s' if len(pending) != 1 else ''}."
        if pending:
            response += "\n" + "\n".join(
                f"• {entry.get('summary', entry.get('type', 'Unknown approval'))}" for entry in pending[:5]
            )
        return {
            "response": response,
            "actions": [{"type": "navigate", "target": "approvals", "label": "View Approvals"}],
            "conversation_id": conversation_id,
            "mode": "fallback",
        }

    if any(keyword in text_lower for keyword in ("top", "best", "selling", "popular")):
        product_sales: dict[str, int] = {}
        for order in orders.get("customer_orders", []):
            for item in order.get("items", []):
                product_sales[item.get("product_name", "Unknown")] = (
                    product_sales.get(item.get("product_name", "Unknown"), 0) + item.get("qty", 0)
                )
        top_products = sorted(product_sales.items(), key=lambda entry: entry[1], reverse=True)[:5]
        if not top_products:
            response = "I don't have enough sales data to rank products yet."
        else:
            response = "Top selling products:\n" + "\n".join(
                f"• {name} — {qty} units sold" for name, qty in top_products
            )
        return {
            "response": response,
            "actions": [{"type": "navigate", "target": "inventory", "label": "View Inventory"}],
            "conversation_id": conversation_id,
            "mode": "fallback",
        }

    if any(keyword in text_lower for keyword in ("supplier", "reliable", "vendor")):
        try:
            from brain.trust_scorer import get_trust_score

            ranked = sorted(
                [{**supplier, "trust_score": get_trust_score(supplier["supplier_id"])["score"]} for supplier in suppliers],
                key=lambda supplier: supplier.get("trust_score", 0),
                reverse=True,
            )[:3]
        except Exception:
            ranked = suppliers[:3]

        if not ranked:
            response = "I don't have supplier data available right now."
        else:
            response = "Your most reliable suppliers:\n" + "\n".join(
                f"• {supplier['supplier_name']} — trust score {supplier.get('trust_score', 'N/A')}"
                for supplier in ranked
            )
        return {
            "response": response,
            "actions": [{"type": "navigate", "target": "suppliers", "label": "View Suppliers"}],
            "conversation_id": conversation_id,
            "mode": "fallback",
        }

    return {
        "response": (
            f"I understood: \"{text}\"\n\n"
            "Try asking about:\n"
            "• Stock status or low inventory\n"
            "• Your latest store summary\n"
            "• Top selling products\n"
            "• Supplier reliability\n"
            "• Pending approvals\n"
            "• Udhaar or credit status"
        ),
        "actions": [],
        "conversation_id": conversation_id,
        "mode": "fallback",
    }


def _gather_store_context() -> str:
    """Gather live store data for the assistant's context window."""
    context_parts = []

    # Inventory summary
    inventory = _read_json("mock_inventory.json", [])
    if inventory:
        low_stock = [i for i in inventory if i.get("current_stock", 0) <= i.get("reorder_threshold", 0)]
        total_items = len(inventory)
        total_value = sum(i.get("current_stock", 0) * i.get("unit_price", 0) for i in inventory)
        context_parts.append(
            f"INVENTORY: {total_items} products, total value ₹{total_value:,.0f}. "
            f"{len(low_stock)} items below reorder threshold: "
            + ", ".join(f"{i['product_name']} ({i.get('current_stock', 0)} left)" for i in low_stock[:8])
        )

    # Today's orders
    orders = _read_json("mock_orders.json", {"customer_orders": [], "vendor_orders": []})
    today = time.strftime("%Y-%m-%d")
    today_orders = [o for o in orders.get("customer_orders", []) if time.strftime("%Y-%m-%d", time.localtime(o.get("timestamp", 0))) == today]
    revenue = sum(o.get("total_amount", 0) for o in today_orders)
    context_parts.append(
        f"TODAY'S SALES: {len(today_orders)} orders, total revenue ₹{revenue:,.0f}."
    )

    # Suppliers
    suppliers = _read_json("mock_suppliers.json", [])
    if suppliers:
        context_parts.append(
            f"SUPPLIERS: {len(suppliers)} active. "
            + ", ".join(
                f"{s['supplier_name']} (reliability: {s.get('reliability_score', 'N/A')}, "
                f"products: {', '.join(s.get('products', [])[:3])})"
                for s in suppliers[:5]
            )
        )

    # Udhaar
    udhaar = _read_json("mock_udhaar.json", [])
    if udhaar:
        total_outstanding = sum(u.get("balance", 0) for u in udhaar)
        context_parts.append(
            f"UDHAAR (CREDIT): {len(udhaar)} accounts, total outstanding ₹{total_outstanding:,.0f}."
        )

    # Recent alerts / expiry
    try:
        from brain.expiry_alerter import get_expiry_risks
        expiry_risks = get_expiry_risks(inventory)
        if expiry_risks:
            context_parts.append(
                f"EXPIRY ALERTS: {len(expiry_risks)} items approaching expiry."
            )
    except Exception:
        pass

    return "\n".join(context_parts)


ASSISTANT_SYSTEM_PROMPT = """You are RetailOS Assistant — a helpful, conversational AI assistant for an Indian kirana/retail store owner.

You have access to live store data provided below. Use it to answer questions accurately.
Be concise, friendly, and actionable. If the owner asks in Hindi or Hinglish, respond in the same language.

Guidelines:
- Give specific numbers from the data, not vague answers
- Suggest actions when appropriate (e.g., "You should reorder rice soon")
- For supplier questions, consider reliability scores and delivery times
- Currency is always INR (₹)
- Keep responses under 3-4 sentences unless the owner asks for details
- If you don't have the data to answer, say so honestly

LIVE STORE DATA:
{context}
"""


@router.post("/chat")
async def assistant_chat(
    body: AssistantQuery,
    user: User = Depends(require_role("cashier")),
):
    """Chat with the voice assistant. Supports multi-turn conversation."""
    conv_id = body.conversation_id or f"conv_{user.id}_{int(time.time())}"
    history = _conversations.get(conv_id, [])
    history.append({"role": "user", "content": body.text, "timestamp": time.time()})

    if not os.environ.get("GEMINI_API_KEY", ""):
        fallback = _fallback_assistant_reply(body.text, conv_id)
        history.append({"role": "assistant", "content": fallback["response"], "timestamp": time.time()})
        _conversations[conv_id] = history[-20:]
        return {**fallback, "language": body.language}

    try:
        from runtime.llm_client import get_llm_client

        context = _gather_store_context()
        system_prompt = ASSISTANT_SYSTEM_PROMPT.format(context=context)
        prompt_parts = [system_prompt + "\n\n"]
        for msg in history[-7:-1]:
            role = "Owner" if msg["role"] == "user" else "Assistant"
            prompt_parts.append(f"{role}: {msg['content']}\n")
        prompt_parts.append(f"Owner: {body.text}\nAssistant:")

        llm = get_llm_client()
        assistant_response = await llm.generate("".join(prompt_parts), timeout=30)
        history.append({"role": "assistant", "content": assistant_response, "timestamp": time.time()})
        _conversations[conv_id] = history[-20:]

        return {
            "response": assistant_response,
            "conversation_id": conv_id,
            "actions": _extract_actions(assistant_response, body.text),
            "mode": "gemini",
            "language": body.language,
        }
    except Exception as e:
        fallback = _fallback_assistant_reply(body.text, conv_id)
        history.append({"role": "assistant", "content": fallback["response"], "timestamp": time.time()})
        _conversations[conv_id] = history[-20:]
        return {**fallback, "language": body.language, "error": str(e)}


def _extract_actions(response: str, query: str) -> list[dict[str, Any]]:
    """Extract actionable suggestions from the assistant's response."""
    actions = []
    response_lower = response.lower()

    if any(word in response_lower for word in ["reorder", "restock", "order more", "running low"]):
        actions.append({"type": "navigate", "target": "inventory", "label": "Check Inventory"})

    if any(word in response_lower for word in ["approve", "approval", "pending"]):
        actions.append({"type": "navigate", "target": "approvals", "label": "View Approvals"})

    if any(word in response_lower for word in ["supplier", "vendor", "procurement"]):
        actions.append({"type": "navigate", "target": "suppliers", "label": "View Suppliers"})

    if any(word in response_lower for word in ["udhaar", "credit", "outstanding", "बकाया"]):
        actions.append({"type": "navigate", "target": "financials", "label": "View Financials"})

    return actions


@router.get("/status")
async def assistant_status():
    """Get voice assistant status."""
    has_gemini = bool(os.environ.get("GEMINI_API_KEY", ""))
    return {
        "mode": "gemini" if has_gemini else "fallback",
        "gemini_configured": has_gemini,
        "supported_languages": ["en", "hi", "hinglish"],
        "capabilities": [
            "Store performance queries",
            "Inventory status and alerts",
            "Supplier recommendations",
            "Sales summaries",
            "Udhaar/credit inquiries",
            "Approval status",
            "Multi-turn conversation",
            "Hindi/English/Hinglish support",
        ],
        "active_conversations": len(_conversations),
    }


@router.delete("/conversations/{conv_id}")
async def clear_conversation(
    conv_id: str,
    user: User = Depends(require_role("cashier")),
):
    """Clear a conversation's history."""
    _conversations.pop(conv_id, None)
    return {"status": "cleared", "conversation_id": conv_id}
