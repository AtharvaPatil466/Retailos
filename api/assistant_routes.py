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
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
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
    from google import genai
    import os

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        # Fallback: use the basic voice parser
        from brain.voice_input import voice_processor
        parsed = voice_processor.parse_command(body.text)
        return {
            "response": parsed.get("action_description", "I understand you said: " + body.text),
            "intent": parsed.get("intent", "unknown"),
            "mode": "fallback",
            "language": body.language,
        }

    # Gather live context
    context = _gather_store_context()

    # Build conversation history
    conv_id = body.conversation_id or f"conv_{user.id}_{int(time.time())}"
    history = _conversations.get(conv_id, [])

    # Build messages for Gemini
    system_prompt = ASSISTANT_SYSTEM_PROMPT.format(context=context)

    # Build the full prompt with history
    prompt_parts = [system_prompt + "\n\n"]
    for msg in history[-6:]:  # Keep last 6 exchanges for context
        role = "Owner" if msg["role"] == "user" else "Assistant"
        prompt_parts.append(f"{role}: {msg['content']}\n")
    prompt_parts.append(f"Owner: {body.text}\nAssistant:")

    full_prompt = "".join(prompt_parts)

    try:
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=full_prompt,
        )

        assistant_response = response.text.strip()

        # Save to conversation history
        history.append({"role": "user", "content": body.text, "timestamp": time.time()})
        history.append({"role": "assistant", "content": assistant_response, "timestamp": time.time()})
        _conversations[conv_id] = history[-20:]  # Keep last 20 messages

        # Detect if response contains actionable items
        actions = _extract_actions(assistant_response, body.text)

        return {
            "response": assistant_response,
            "conversation_id": conv_id,
            "actions": actions,
            "mode": "gemini",
            "language": body.language,
        }

    except Exception as e:
        # Graceful fallback
        from brain.voice_input import voice_processor
        parsed = voice_processor.parse_command(body.text)

        return {
            "response": parsed.get("action_description", f"I heard: {body.text}. Let me help with that."),
            "intent": parsed.get("intent", "unknown"),
            "mode": "fallback",
            "language": body.language,
            "error": str(e),
        }


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
    import os
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
