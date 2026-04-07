"""Tests for GST return generation and P&L reports."""

import io
from openpyxl import load_workbook

from reports.gst_returns import (
    generate_gstr1_excel,
    generate_gstr3b_excel,
    generate_pnl_excel,
)


def _make_orders():
    return [
        {
            "order_id": "ORD-001",
            "date": "2024-10-15",
            "customer_name": "Ramesh Patel",
            "customer_gstin": "27AABCU9603R1ZM",
            "items": [
                {"sku": "RICE-5KG", "product_name": "Basmati Rice 5kg", "qty": 10, "unit_price": 275.0, "hsn": "1006", "gst_rate": 5},
                {"sku": "OIL-1L", "product_name": "Sunflower Oil 1L", "qty": 5, "unit_price": 180.0, "hsn": "1512", "gst_rate": 5},
            ],
            "total_amount": 3650.0,
        },
        {
            "order_id": "ORD-002",
            "date": "2024-10-18",
            "customer_name": "Sunita Devi",
            "customer_gstin": "",
            "items": [
                {"sku": "SOAP-100G", "product_name": "Soap Bar 100g", "qty": 3, "unit_price": 45.0, "hsn": "3401", "gst_rate": 18},
            ],
            "total_amount": 135.0,
        },
    ]


def test_gstr1_excel_generates():
    orders = _make_orders()
    buf = generate_gstr1_excel(orders, "2024-10", "27AABCU9603R1ZM")
    assert isinstance(buf, io.BytesIO)
    wb = load_workbook(buf)
    assert "B2B" in wb.sheetnames
    assert "B2C" in wb.sheetnames
    assert "HSN Summary" in wb.sheetnames


def test_gstr1_b2b_has_gstin_entries():
    orders = _make_orders()
    buf = generate_gstr1_excel(orders, "2024-10", "27AABCU9603R1ZM")
    wb = load_workbook(buf)
    b2b = wb["B2B"]
    # Header + at least 1 data row (order with GSTIN)
    assert b2b.max_row >= 2


def test_gstr1_b2c_has_non_gstin_entries():
    orders = _make_orders()
    buf = generate_gstr1_excel(orders, "2024-10", "27AABCU9603R1ZM")
    wb = load_workbook(buf)
    b2c = wb["B2C"]
    assert b2c.max_row >= 2


def test_gstr3b_excel_generates():
    orders = _make_orders()
    purchases = [
        {
            "order_id": "PO-001",
            "date": "2024-10-10",
            "items": [
                {"sku": "RICE-5KG", "qty": 100, "unit_price": 250.0, "gst_rate": 5},
            ],
        }
    ]
    buf = generate_gstr3b_excel(orders, purchases, "2024-10")
    assert isinstance(buf, io.BytesIO)
    wb = load_workbook(buf)
    assert "GSTR-3B" in wb.sheetnames


def test_pnl_excel_generates():
    revenue_data = {
        "total_sales": 150000.0,
        "total_returns": 5000.0,
        "cost_of_goods": 90000.0,
        "expenses": {
            "rent": 15000.0,
            "salaries": 25000.0,
            "utilities": 3000.0,
            "marketing": 2000.0,
        },
    }
    buf = generate_pnl_excel(revenue_data, "2024-10")
    assert isinstance(buf, io.BytesIO)
    wb = load_workbook(buf)
    assert "P&L Statement" in wb.sheetnames


def test_gstr1_empty_orders():
    buf = generate_gstr1_excel([], "2024-10", "27AABCU9603R1ZM")
    assert isinstance(buf, io.BytesIO)
    wb = load_workbook(buf)
    assert "B2B" in wb.sheetnames
