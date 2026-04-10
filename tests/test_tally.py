"""Tests for Tally ERP integration."""

import xml.etree.ElementTree as ET

from integrations.tally import TallySync


def test_tally_sync_init_demo_mode():
    tally = TallySync()
    assert tally.is_configured is False
    assert tally.is_configured is False
    # Demo mode: no tally_url configured
    assert tally.tally_url == ""


def test_generate_sales_voucher_xml():
    tally = TallySync()
    order = {
        "order_id": "ORD-2024-001",
        "date": "2024-10-15",
        "customer_name": "Ramesh Patel",
        "items": [
            {"product_name": "Basmati Rice 5kg", "qty": 2, "unit_price": 275.0, "total": 550.0},
            {"product_name": "Toor Dal 1kg", "qty": 1, "unit_price": 160.0, "total": 160.0},
        ],
        "total_amount": 710.0,
        "payment_method": "Cash",
    }
    xml_str = tally.generate_sales_voucher_xml(order)
    assert isinstance(xml_str, str)
    assert "ENVELOPE" in xml_str or "envelope" in xml_str.lower()

    # Verify valid XML
    root = ET.fromstring(xml_str)
    assert root is not None


def test_generate_purchase_voucher_xml():
    tally = TallySync()
    purchase = {
        "order_id": "PO-2024-001",
        "date": "2024-10-10",
        "supplier_name": "Gupta Wholesale",
        "items": [
            {"product_name": "Basmati Rice 25kg", "qty": 10, "unit_price": 1200.0, "total": 12000.0},
        ],
        "total_amount": 12000.0,
    }
    xml_str = tally.generate_purchase_voucher_xml(purchase)
    assert isinstance(xml_str, str)

    root = ET.fromstring(xml_str)
    assert root is not None


def test_ledger_mappings():
    tally = TallySync()
    mappings = tally.get_ledger_mappings()
    assert isinstance(mappings, dict)
    assert "Cash" in mappings or "cash" in str(mappings).lower()


def test_sync_log_starts_empty():
    tally = TallySync()
    log = tally.get_sync_log()
    assert isinstance(log, list)
    assert len(log) == 0
