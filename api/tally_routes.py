"""Tally ERP sync API endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from auth.dependencies import require_role
from db.models import User
from integrations.tally import tally_sync

router = APIRouter(prefix="/api/tally", tags=["integrations"])


class SyncOrder(BaseModel):
    order_id: str
    customer_name: str = "Cash Sales"
    total_amount: float
    gst_amount: float = 0
    payment_method: str = "Cash"
    date: str = ""


class SyncPO(BaseModel):
    po_number: str
    supplier_name: str
    total_amount: float
    date: str = ""


class LedgerMapping(BaseModel):
    retailos_name: str
    tally_name: str


@router.get("/status")
async def tally_status():
    """Get Tally sync configuration status."""
    return {
        "is_configured": tally_sync.is_configured,
        "tally_url": tally_sync.tally_url or "(not set)",
        "company_name": tally_sync.company_name,
    }


@router.post("/sync-order")
async def sync_order(
    body: SyncOrder,
    user: User = Depends(require_role("manager")),
):
    """Sync a sales order to Tally ERP."""
    return await tally_sync.sync_order(body.model_dump())


@router.post("/sync-purchase")
async def sync_purchase(
    body: SyncPO,
    user: User = Depends(require_role("manager")),
):
    """Sync a purchase order to Tally ERP."""
    return await tally_sync.sync_purchase_order(body.model_dump())


@router.get("/voucher-xml")
async def get_voucher_xml(
    order_id: str = "",
    total_amount: float = 0,
    gst_amount: float = 0,
    payment_method: str = "Cash",
    voucher_type: str = "sales",
    user: User = Depends(require_role("manager")),
):
    """Preview Tally voucher XML without syncing."""
    order = {
        "order_id": order_id,
        "total_amount": total_amount,
        "gst_amount": gst_amount,
        "payment_method": payment_method,
    }
    xml = tally_sync.get_voucher_xml(order, voucher_type)
    return Response(content=xml, media_type="application/xml")


@router.get("/ledger-mappings")
async def get_ledger_mappings(user: User = Depends(require_role("manager"))):
    """Get current ledger mappings between RetailOS and Tally."""
    return {"mappings": tally_sync.get_ledger_mappings()}


@router.post("/ledger-mappings")
async def set_ledger_mapping(
    body: LedgerMapping,
    user: User = Depends(require_role("owner")),
):
    """Set a custom ledger mapping."""
    tally_sync.map_ledger(body.retailos_name, body.tally_name)
    return {"status": "mapped", "retailos_name": body.retailos_name, "tally_name": body.tally_name}


@router.get("/sync-log")
async def sync_log(
    limit: int = 50,
    user: User = Depends(require_role("manager")),
):
    """Get Tally sync history."""
    return {"log": tally_sync.get_sync_log(limit)}
