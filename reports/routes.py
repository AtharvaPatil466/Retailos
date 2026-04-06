import io
import json
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth.dependencies import require_role
from db.models import User
from reports.generators import (
    generate_gst_excel,
    generate_inventory_excel,
    generate_pnl_pdf,
    generate_sales_excel,
)
from reports.gst_invoice import generate_gst_invoice

router = APIRouter(prefix="/api/reports", tags=["reports"])

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _read_json(filename: str, default=None):
    try:
        with open(DATA_DIR / filename) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []


@router.get("/sales/excel")
async def export_sales_excel(
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    user: User = Depends(require_role("manager")),
):
    orders = _read_json("mock_orders.json", {"customer_orders": []})
    all_orders = orders.get("customer_orders", [])

    # Filter by date range (timestamp)
    from datetime import datetime
    ts_from = datetime.strptime(date_from, "%Y-%m-%d").timestamp()
    ts_to = datetime.strptime(date_to, "%Y-%m-%d").timestamp() + 86400

    filtered = [o for o in all_orders if ts_from <= o.get("timestamp", 0) < ts_to]

    buf = generate_sales_excel(filtered, date_from, date_to)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=sales_{date_from}_{date_to}.xlsx"},
    )


@router.get("/pnl/pdf")
async def export_pnl_pdf(
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    user: User = Depends(require_role("owner")),
):
    orders = _read_json("mock_orders.json", {"customer_orders": []})
    all_orders = orders.get("customer_orders", [])

    from datetime import datetime
    ts_from = datetime.strptime(date_from, "%Y-%m-%d").timestamp()
    ts_to = datetime.strptime(date_to, "%Y-%m-%d").timestamp() + 86400

    filtered = [o for o in all_orders if ts_from <= o.get("timestamp", 0) < ts_to]

    revenue = sum(o.get("total_amount", 0) for o in filtered)
    gst_collected = sum(o.get("gst_amount", 0) for o in filtered)

    # Estimate COGS at ~70% of revenue (placeholder until real cost tracking)
    cost_of_goods = revenue * 0.70

    returns = _read_json("mock_returns.json", [])
    returns_amount = sum(
        r.get("refund_amount", 0) for r in returns
        if ts_from <= r.get("timestamp", 0) < ts_to
    )

    period = f"{date_from} to {date_to}"
    buf = generate_pnl_pdf(revenue, cost_of_goods, gst_collected, returns_amount, period)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=pnl_{date_from}_{date_to}.pdf"},
    )


@router.get("/gst/excel")
async def export_gst_excel(
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    user: User = Depends(require_role("manager")),
):
    orders = _read_json("mock_orders.json", {"customer_orders": []})
    all_orders = orders.get("customer_orders", [])

    from datetime import datetime
    ts_from = datetime.strptime(date_from, "%Y-%m-%d").timestamp()
    ts_to = datetime.strptime(date_to, "%Y-%m-%d").timestamp() + 86400

    filtered = [o for o in all_orders if ts_from <= o.get("timestamp", 0) < ts_to]

    # Enrich items with category from inventory
    inventory = _read_json("mock_inventory.json", [])
    inv_map = {item["sku"]: item for item in inventory}

    for order in filtered:
        for item in order.get("items", []):
            if "category" not in item:
                inv_item = inv_map.get(item.get("sku", ""), {})
                item["category"] = inv_item.get("category", "Grocery")

    buf = generate_gst_excel(filtered, date_from, date_to)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=gst_{date_from}_{date_to}.xlsx"},
    )


@router.get("/inventory/excel")
async def export_inventory_excel(
    user: User = Depends(require_role("staff")),
):
    inventory = _read_json("mock_inventory.json", [])
    buf = generate_inventory_excel(inventory)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=inventory_report.xlsx"},
    )


# ── GST Invoice ──────────────────────────────────────────

class InvoiceItem(BaseModel):
    description: str
    hsn_code: str = ""
    qty: int = 1
    unit: str = "pcs"
    rate: float = 0.0
    gst_rate: float = 18.0


class InvoiceParty(BaseModel):
    name: str
    address: str = ""
    gstin: str = ""
    state: str = ""
    phone: str = ""


class GenerateInvoiceRequest(BaseModel):
    invoice_number: str
    invoice_date: str = ""
    seller: InvoiceParty
    buyer: InvoiceParty
    items: list[InvoiceItem]
    place_of_supply: str = ""
    reverse_charge: bool = False
    notes: str = ""


@router.post("/invoice/gst")
async def generate_invoice(
    body: GenerateInvoiceRequest,
    user: User = Depends(require_role("cashier")),
):
    """Generate a GST-compliant tax invoice PDF.

    Includes GSTIN, HSN codes, CGST/SGST/IGST breakdowns,
    amount in words, and all legally required fields.
    """
    invoice_date = body.invoice_date or time.strftime("%Y-%m-%d")

    pdf_bytes = generate_gst_invoice(
        invoice_number=body.invoice_number,
        invoice_date=invoice_date,
        seller=body.seller.model_dump(),
        buyer=body.buyer.model_dump(),
        items=[item.model_dump() for item in body.items],
        place_of_supply=body.place_of_supply,
        reverse_charge=body.reverse_charge,
        notes=body.notes,
    )

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=invoice_{body.invoice_number}.pdf"},
    )
