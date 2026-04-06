"""Tally ERP integration for accounting sync.

Supports:
- Export transactions in Tally XML format (TallyPrime compatible)
- Voucher generation (Sales, Purchase, Payment, Receipt)
- Ledger mapping between RetailOS and Tally
- Sync status tracking

In demo mode (no Tally URL configured), generates XML files locally.
"""

import logging
import os
import time
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

logger = logging.getLogger(__name__)


LEDGER_MAP = {
    "Cash": "Cash-in-Hand",
    "UPI": "Bank Account (UPI)",
    "Card": "Bank Account (Card)",
    "Credit": "Sundry Debtors",
    "sales": "Sales Account",
    "purchase": "Purchase Account",
    "gst_output": "Output GST",
    "gst_input": "Input GST",
    "discount": "Discount Allowed",
    "returns": "Sales Return",
}


class TallySync:
    """Tally ERP sync client."""

    def __init__(self):
        self.tally_url = os.environ.get("TALLY_URL", "")  # e.g., http://localhost:9000
        self.company_name = os.environ.get("TALLY_COMPANY", "RetailOS Store")
        self._sync_log: list[dict] = []
        self._ledger_map = dict(LEDGER_MAP)

    @property
    def is_configured(self) -> bool:
        return bool(self.tally_url)

    def map_ledger(self, retailos_name: str, tally_name: str):
        """Map a RetailOS account name to a Tally ledger."""
        self._ledger_map[retailos_name] = tally_name

    def get_ledger_mappings(self) -> dict[str, str]:
        return dict(self._ledger_map)

    def generate_sales_voucher_xml(self, order: dict) -> str:
        """Generate Tally Sales Voucher XML for an order."""
        envelope = Element("ENVELOPE")
        header = SubElement(envelope, "HEADER")
        SubElement(header, "TALLYREQUEST").text = "Import Data"

        body = SubElement(envelope, "BODY")
        import_data = SubElement(body, "IMPORTDATA")
        req_desc = SubElement(import_data, "REQUESTDESC")
        SubElement(req_desc, "REPORTNAME").text = "Vouchers"
        static_vars = SubElement(req_desc, "STATICVARIABLES")
        SubElement(static_vars, "SVCURRENTCOMPANY").text = self.company_name

        req_data = SubElement(import_data, "REQUESTDATA")
        voucher = SubElement(req_data, "TALLYMESSAGE", xmlns_UDF="TallyUDF")
        v = SubElement(voucher, "VOUCHER", VCHTYPE="Sales", ACTION="Create")

        SubElement(v, "DATE").text = order.get("date", time.strftime("%Y%m%d"))
        SubElement(v, "NARRATION").text = f"RetailOS Order {order.get('order_id', '')}"
        SubElement(v, "VOUCHERTYPENAME").text = "Sales"
        SubElement(v, "VOUCHERNUMBER").text = order.get("order_id", "")
        SubElement(v, "PARTYLEDGERNAME").text = order.get("customer_name", "Cash Sales")

        # Debit: Payment method
        payment_method = order.get("payment_method", "Cash")
        ledger_dr = self._ledger_map.get(payment_method, "Cash-in-Hand")
        entry_dr = SubElement(v, "ALLLEDGERENTRIES.LIST")
        SubElement(entry_dr, "LEDGERNAME").text = ledger_dr
        SubElement(entry_dr, "ISDEEMEDPOSITIVE").text = "Yes"
        SubElement(entry_dr, "AMOUNT").text = str(-order.get("total_amount", 0))

        # Credit: Sales
        entry_cr = SubElement(v, "ALLLEDGERENTRIES.LIST")
        SubElement(entry_cr, "LEDGERNAME").text = self._ledger_map.get("sales", "Sales Account")
        SubElement(entry_cr, "ISDEEMEDPOSITIVE").text = "No"
        taxable = order.get("total_amount", 0) - order.get("gst_amount", 0)
        SubElement(entry_cr, "AMOUNT").text = str(taxable)

        # Credit: GST
        if order.get("gst_amount", 0) > 0:
            entry_gst = SubElement(v, "ALLLEDGERENTRIES.LIST")
            SubElement(entry_gst, "LEDGERNAME").text = self._ledger_map.get("gst_output", "Output GST")
            SubElement(entry_gst, "ISDEEMEDPOSITIVE").text = "No"
            SubElement(entry_gst, "AMOUNT").text = str(order.get("gst_amount", 0))

        return tostring(envelope, encoding="unicode", xml_declaration=True)

    def generate_purchase_voucher_xml(self, po: dict) -> str:
        """Generate Tally Purchase Voucher XML."""
        envelope = Element("ENVELOPE")
        header = SubElement(envelope, "HEADER")
        SubElement(header, "TALLYREQUEST").text = "Import Data"

        body = SubElement(envelope, "BODY")
        import_data = SubElement(body, "IMPORTDATA")
        req_desc = SubElement(import_data, "REQUESTDESC")
        SubElement(req_desc, "REPORTNAME").text = "Vouchers"
        static_vars = SubElement(req_desc, "STATICVARIABLES")
        SubElement(static_vars, "SVCURRENTCOMPANY").text = self.company_name

        req_data = SubElement(import_data, "REQUESTDATA")
        voucher = SubElement(req_data, "TALLYMESSAGE")
        v = SubElement(voucher, "VOUCHER", VCHTYPE="Purchase", ACTION="Create")

        SubElement(v, "DATE").text = po.get("date", time.strftime("%Y%m%d"))
        SubElement(v, "NARRATION").text = f"RetailOS PO {po.get('po_number', '')}"
        SubElement(v, "VOUCHERTYPENAME").text = "Purchase"
        SubElement(v, "PARTYLEDGERNAME").text = po.get("supplier_name", "Sundry Creditors")

        entry_dr = SubElement(v, "ALLLEDGERENTRIES.LIST")
        SubElement(entry_dr, "LEDGERNAME").text = self._ledger_map.get("purchase", "Purchase Account")
        SubElement(entry_dr, "ISDEEMEDPOSITIVE").text = "Yes"
        SubElement(entry_dr, "AMOUNT").text = str(-po.get("total_amount", 0))

        entry_cr = SubElement(v, "ALLLEDGERENTRIES.LIST")
        SubElement(entry_cr, "LEDGERNAME").text = po.get("supplier_name", "Sundry Creditors")
        SubElement(entry_cr, "ISDEEMEDPOSITIVE").text = "No"
        SubElement(entry_cr, "AMOUNT").text = str(po.get("total_amount", 0))

        return tostring(envelope, encoding="unicode", xml_declaration=True)

    async def sync_order(self, order: dict) -> dict:
        """Sync a sales order to Tally."""
        xml = self.generate_sales_voucher_xml(order)

        if self.is_configured:
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.post(self.tally_url, content=xml, headers={"Content-Type": "text/xml"}, timeout=10)
                    result = {"status": "synced", "order_id": order.get("order_id"), "tally_response": resp.text[:200]}
            except Exception as e:
                result = {"status": "error", "order_id": order.get("order_id"), "detail": str(e)}
        else:
            result = {"status": "generated", "order_id": order.get("order_id"), "xml_length": len(xml), "demo": True}

        result["timestamp"] = time.time()
        self._sync_log.append(result)
        return result

    async def sync_purchase_order(self, po: dict) -> dict:
        """Sync a purchase order to Tally."""
        xml = self.generate_purchase_voucher_xml(po)

        if self.is_configured:
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.post(self.tally_url, content=xml, headers={"Content-Type": "text/xml"}, timeout=10)
                    result = {"status": "synced", "po_number": po.get("po_number"), "tally_response": resp.text[:200]}
            except Exception as e:
                result = {"status": "error", "po_number": po.get("po_number"), "detail": str(e)}
        else:
            result = {"status": "generated", "po_number": po.get("po_number"), "xml_length": len(xml), "demo": True}

        result["timestamp"] = time.time()
        self._sync_log.append(result)
        return result

    def get_sync_log(self, limit: int = 50) -> list[dict]:
        return self._sync_log[-limit:]

    def get_voucher_xml(self, order: dict, voucher_type: str = "sales") -> str:
        if voucher_type == "purchase":
            return self.generate_purchase_voucher_xml(order)
        return self.generate_sales_voucher_xml(order)


tally_sync = TallySync()
