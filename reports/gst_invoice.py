"""GST-compliant invoice PDF generator.

Generates tax invoices per Indian GST law requirements:
- Seller & buyer GSTIN, name, address
- HSN/SAC codes per line item
- CGST/SGST/IGST breakdowns
- Invoice number, date, place of supply
"""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def generate_gst_invoice(
    invoice_number: str,
    invoice_date: str,
    seller: dict,
    buyer: dict,
    items: list[dict],
    place_of_supply: str = "",
    reverse_charge: bool = False,
    notes: str = "",
) -> bytes:
    """Generate a GST-compliant invoice PDF.

    Args:
        invoice_number: Unique invoice number (e.g., "INV-2026-0001")
        invoice_date: Date string (e.g., "2026-04-06")
        seller: {"name", "address", "gstin", "state", "phone"}
        buyer: {"name", "address", "gstin", "state", "phone"}
        items: List of {"description", "hsn_code", "qty", "unit", "rate", "gst_rate"}
        place_of_supply: State name or code
        reverse_charge: Whether reverse charge applies
        notes: Additional notes

    Returns:
        PDF bytes
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("InvoiceTitle", parent=styles["Heading1"], fontSize=16, alignment=1)
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=8, alignment=1)
    bold_style = ParagraphStyle("Bold", parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold")
    normal_style = ParagraphStyle("NormalSmall", parent=styles["Normal"], fontSize=8)

    elements = []

    # ── Header ──
    elements.append(Paragraph("TAX INVOICE", title_style))
    elements.append(Spacer(1, 3 * mm))

    # ── Seller / Buyer Info ──
    is_igst = seller.get("state", "") != buyer.get("state", "") and buyer.get("state", "")

    info_data = [
        [
            Paragraph(f"<b>Seller</b><br/>"
                       f"{seller.get('name', '')}<br/>"
                       f"{seller.get('address', '')}<br/>"
                       f"GSTIN: {seller.get('gstin', 'N/A')}<br/>"
                       f"State: {seller.get('state', '')}<br/>"
                       f"Phone: {seller.get('phone', '')}", normal_style),
            Paragraph(f"<b>Buyer</b><br/>"
                       f"{buyer.get('name', '')}<br/>"
                       f"{buyer.get('address', '')}<br/>"
                       f"GSTIN: {buyer.get('gstin', 'N/A')}<br/>"
                       f"State: {buyer.get('state', '')}<br/>"
                       f"Phone: {buyer.get('phone', '')}", normal_style),
        ],
        [
            Paragraph(f"<b>Invoice No:</b> {invoice_number}<br/>"
                       f"<b>Date:</b> {invoice_date}<br/>"
                       f"<b>Place of Supply:</b> {place_of_supply or buyer.get('state', '')}<br/>"
                       f"<b>Reverse Charge:</b> {'Yes' if reverse_charge else 'No'}", normal_style),
            "",
        ],
    ]
    info_table = Table(info_data, colWidths=[270, 270])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 5 * mm))

    # ── Items Table ──
    if is_igst:
        header = ["#", "Description", "HSN", "Qty", "Unit", "Rate (₹)", "Taxable (₹)", "IGST %", "IGST (₹)", "Total (₹)"]
    else:
        header = ["#", "Description", "HSN", "Qty", "Unit", "Rate (₹)", "Taxable (₹)", "CGST %", "CGST (₹)", "SGST %", "SGST (₹)", "Total (₹)"]

    rows = [header]
    total_taxable = 0.0
    total_cgst = 0.0
    total_sgst = 0.0
    total_igst = 0.0
    grand_total = 0.0

    for i, item in enumerate(items, 1):
        qty = item.get("qty", 1)
        rate = item.get("rate", 0.0)
        gst_rate = item.get("gst_rate", 18.0)
        taxable = qty * rate
        total_taxable += taxable

        if is_igst:
            igst = round(taxable * gst_rate / 100, 2)
            total_igst += igst
            line_total = round(taxable + igst, 2)
            row = [
                str(i),
                item.get("description", ""),
                item.get("hsn_code", ""),
                str(qty),
                item.get("unit", "pcs"),
                f"{rate:.2f}",
                f"{taxable:.2f}",
                f"{gst_rate:.1f}%",
                f"{igst:.2f}",
                f"{line_total:.2f}",
            ]
        else:
            half_rate = gst_rate / 2
            cgst = round(taxable * half_rate / 100, 2)
            sgst = round(taxable * half_rate / 100, 2)
            total_cgst += cgst
            total_sgst += sgst
            line_total = round(taxable + cgst + sgst, 2)
            row = [
                str(i),
                item.get("description", ""),
                item.get("hsn_code", ""),
                str(qty),
                item.get("unit", "pcs"),
                f"{rate:.2f}",
                f"{taxable:.2f}",
                f"{half_rate:.1f}%",
                f"{cgst:.2f}",
                f"{half_rate:.1f}%",
                f"{sgst:.2f}",
                f"{line_total:.2f}",
            ]

        grand_total += line_total
        rows.append(row)

    # Totals row
    if is_igst:
        rows.append(["", "", "", "", "", "Total", f"{total_taxable:.2f}", "", f"{total_igst:.2f}", f"{grand_total:.2f}"])
    else:
        rows.append(["", "", "", "", "", "Total", f"{total_taxable:.2f}", "", f"{total_cgst:.2f}", "", f"{total_sgst:.2f}", f"{grand_total:.2f}"])

    items_table = Table(rows, repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        # Bold totals row
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ecf0f1")),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 5 * mm))

    # ── Tax Summary ──
    elements.append(Paragraph("<b>Tax Summary</b>", bold_style))
    tax_summary = [["Component", "Amount (₹)"]]
    tax_summary.append(["Taxable Value", f"{total_taxable:.2f}"])
    if is_igst:
        tax_summary.append(["IGST", f"{total_igst:.2f}"])
    else:
        tax_summary.append(["CGST", f"{total_cgst:.2f}"])
        tax_summary.append(["SGST", f"{total_sgst:.2f}"])
    tax_summary.append(["Grand Total", f"{grand_total:.2f}"])

    tax_table = Table(tax_summary, colWidths=[200, 100])
    tax_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ecf0f1")),
    ]))
    elements.append(tax_table)
    elements.append(Spacer(1, 5 * mm))

    # ── Amount in words ──
    elements.append(Paragraph(f"<b>Amount in Words:</b> {_amount_in_words(grand_total)}", normal_style))
    elements.append(Spacer(1, 3 * mm))

    # ── Notes / Terms ──
    if notes:
        elements.append(Paragraph(f"<b>Notes:</b> {notes}", normal_style))
        elements.append(Spacer(1, 3 * mm))

    elements.append(Paragraph("Terms: Goods once sold will not be taken back or exchanged. "
                               "Subject to local jurisdiction.", normal_style))
    elements.append(Spacer(1, 10 * mm))

    # ── Signature ──
    elements.append(Paragraph(f"For {seller.get('name', 'RetailOS Store')}", bold_style))
    elements.append(Spacer(1, 15 * mm))
    elements.append(Paragraph("Authorised Signatory", normal_style))

    # ── Footer ──
    elements.append(Spacer(1, 5 * mm))
    elements.append(Paragraph("This is a computer-generated invoice.", subtitle_style))

    doc.build(elements)
    return buffer.getvalue()


def _amount_in_words(amount: float) -> str:
    """Convert amount to words (Indian style: lakhs, crores)."""
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def _convert(n: int) -> str:
        if n < 20:
            return ones[n]
        if n < 100:
            return tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")
        if n < 1000:
            return ones[n // 100] + " Hundred" + (" and " + _convert(n % 100) if n % 100 else "")
        if n < 100000:
            return _convert(n // 1000) + " Thousand" + (" " + _convert(n % 1000) if n % 1000 else "")
        if n < 10000000:
            return _convert(n // 100000) + " Lakh" + (" " + _convert(n % 100000) if n % 100000 else "")
        return _convert(n // 10000000) + " Crore" + (" " + _convert(n % 10000000) if n % 10000000 else "")

    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))

    result = "Rupees " + _convert(rupees)
    if paise:
        result += " and " + _convert(paise) + " Paise"
    result += " Only"
    return result
