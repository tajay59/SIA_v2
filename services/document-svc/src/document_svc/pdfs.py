"""Generated PDFs (PRD D*): CIMH quote, agreement, invoice, Pro Bono invoice, commercial invoice, unit labels.

Rendered from order-svc's staff view of the request (GET /internal/requests/{id}). Values are drawn as text, never
interpreted as markup (reportlab Paragraph markup is escaped). Brand: logo blue #0084C8 for the header rule only;
body text is ink (Design Brief: the logo blue is not a text colour).
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from datetime import UTC, datetime
from html import escape
from typing import Any

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BRAND = colors.HexColor("#0084C8")
INK = colors.HexColor("#1A1C1E")
MUTED = colors.HexColor("#5B6168")
RULE = colors.HexColor("#D0D5DB")
ORG = "Caribbean Institute for Meteorology and Hydrology"
ORG_ADDRESS = "Husbands, St. James, Barbados"

_styles = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=_styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10.5, textColor=MUTED)
TITLE = ParagraphStyle("title", parent=BODY, fontName="Helvetica-Bold", fontSize=16, leading=20)
H2 = ParagraphStyle("h2", parent=BODY, fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=6)


def _p(text: Any, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(escape(str(text if text is not None else ""), quote=False), style)


def _today() -> str:
    return datetime.now(UTC).strftime("%d %B %Y")


def _date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d %B %Y")
    except ValueError:
        return value


def _address(a: dict[str, Any] | None) -> list[str]:
    if not a:
        return ["—"]
    name = " ".join(x for x in (a.get("firstname"), a.get("lastname")) if x)
    rows = [
        name,
        a.get("attention") and f"Attn: {a['attention']}",
        a.get("organisation"),
        a.get("line1"),
        a.get("line2"),
        ", ".join(x for x in (a.get("city"), a.get("parish"), a.get("zip")) if x),
        a.get("country"),
        a.get("email"),
        a.get("tel"),
    ]
    return [str(r) for r in rows if r]


def _product(line: dict[str, Any]) -> str:
    prod = line.get("product") or {}
    bits = [prod.get("name") or line.get("productId") or ""]
    model = " ".join(x for x in (prod.get("make"), prod.get("modelname"), prod.get("modelnumber")) if x)
    if model:
        bits.append(model)
    return " — ".join(bits)


def _build(title: str, req: dict[str, Any], body: list[Any], *, subtitle: str | None = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=18 * mm,
        title=f"{title} {req.get('id', '')}", author="CIMH Stores", creator="CIMH Stores document-svc",
    )  # fmt: skip

    def frame(c: Canvas, d: Any) -> None:
        c.saveState()
        c.setFillColor(BRAND)
        c.rect(0, A4[1] - 8 * mm, A4[0], 8 * mm, stroke=0, fill=1)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(18 * mm, 10 * mm, f"{ORG} · {ORG_ADDRESS}")
        c.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{req.get('id', '')} · page {d.page}")
        c.restoreState()

    head = [
        _p(ORG, SMALL),
        _p(title, TITLE),
        _p(subtitle or f"Request {req.get('id', '')} · {_today()}", SMALL),
        Spacer(1, 6 * mm),
    ]
    doc.build(head + body, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


def _parties(req: dict[str, Any], left: str = "Customer", right: str = "Ship to") -> Table:
    cust = req.get("billTo") or req.get("shipTo")
    who = [req.get("customerName") or "", req.get("organisationName") or ""]
    lcol = [_p(left, H2)] + [_p(x) for x in (who + _address(cust)[1:]) if x]
    rcol = [_p(right, H2)] + [_p(x) for x in _address(req.get("shipTo"))]
    t = Table([[lcol, rcol]], colWidths=[87 * mm, 87 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _table(header: list[str], rows: Iterable[list[Any]], widths: list[float], money_cols: int = 2) -> Table:
    data = [[_p(h, SMALL) for h in header]]
    data += [[c if isinstance(c, Paragraph) else _p(c) for c in r] for r in rows]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    style = [
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    if money_cols:
        style.append(("ALIGN", (-money_cols, 0), (-1, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def _totals(rows: list[tuple[str, str]]) -> Table:
    t = Table([[_p(k, H2 if i == len(rows) - 1 else BODY), _p(v, H2 if i == len(rows) - 1 else BODY)]
               for i, (k, v) in enumerate(rows)], colWidths=[140 * mm, 34 * mm])  # fmt: skip
    t.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK)]))
    return t


def _lines_by_id(req: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {ln["lineId"]: ln for ln in req.get("lines") or []}


def _quote(req: dict[str, Any], version: int | None) -> dict[str, Any] | None:
    quotes = req.get("quotes") or []
    for q in quotes:
        if version is not None and q.get("version") == version:
            return dict(q)
    return dict(quotes[-1]) if quotes else None


def _chosen_prices(req: dict[str, Any]) -> list[tuple[dict[str, Any], str, str, str]]:
    """(line, source, unit price, total) for the agreed choices."""
    ag = req.get("agreement") or req.get("acceptance") or {}
    choices = {c["lineId"]: c["choice"] for c in ag.get("choices") or []}
    supplier = {x["lineId"]: x for x in (_quote(req, ag.get("quoteVersion")) or {}).get("lines") or []}
    cimh = {x["lineId"]: x for x in (req.get("cimhQuote") or {}).get("lines") or []}
    out = []
    for line in req.get("lines") or []:
        choice = choices.get(line["lineId"]) or line.get("choice") or "SUPPLIER"
        price = (cimh if choice == "CIMH" else supplier).get(line["lineId"]) or {}
        src = "CIMH stock" if choice == "CIMH" else "Supplier (ships direct)"
        out.append((line, src, price.get("unitPrice") or "—", price.get("total") or "—"))
    return out


# ---------------------------------------------------------------- documents


def cimh_quote(req: dict[str, Any], line_ids: list[str] | None = None) -> bytes:
    cq = req.get("cimhQuote") or {}
    cur = req.get("currency") or "BBD"
    lines = _lines_by_id(req)
    wanted = set(line_ids or [x["lineId"] for x in cq.get("lines") or []])
    rows = [
        [
            _product(lines.get(x["lineId"], {})),
            str(lines.get(x["lineId"], {}).get("qty", "")),
            x["unitPrice"],
            x["total"],
        ]
        for x in cq.get("lines") or []
        if x["lineId"] in wanted
    ]
    body: list[Any] = [_parties(req), Spacer(1, 6 * mm), _p("Items offered from CIMH stock", H2)]
    body.append(_table(["Item", "Qty", f"Unit ({cur})", f"Total ({cur})"], rows, [104, 14, 28, 28]))
    totals = []
    if req.get("adminFee"):
        totals.append(("Administrative fee (once per request)", f"{cur} {req['adminFee']}"))
    totals.append(("CIMH stock total", f"{cur} {cq.get('total', '0.00')}"))
    body += [Spacer(1, 3 * mm), _totals(totals)]
    if cq.get("exchangeRate"):
        body.append(_p(f"Exchange rate used: 1 USD = {cq['exchangeRate']} BBD", SMALL))
    expires = _date(req.get("quoteExpiresAt"))
    body += [Spacer(1, 6 * mm), _p(f"This quote is valid until {expires or '30 days from issue'}. "
             "Stock is reserved only when you accept the quote with a signed agreement.", SMALL)]  # fmt: skip
    return _build("CIMH stock quote", req, body)


def agreement(req: dict[str, Any]) -> bytes:
    cur = req.get("currency") or "BBD"
    ag = req.get("agreement") or {}
    rows = [[_product(ln), src, str(ln.get("qty", "")), unit, total] for ln, src, unit, total in _chosen_prices(req)]
    body: list[Any] = [_parties(req), Spacer(1, 6 * mm), _p("Your choices", H2)]
    body.append(_table(["Item", "Source", "Qty", f"Unit ({cur})", f"Total ({cur})"], rows, [74, 36, 12, 26, 26]))
    totals = []
    if req.get("adminFee"):
        totals.append(("Administrative fee", f"{cur} {req['adminFee']}"))
    totals.append(("Agreed total", f"{cur} {ag.get('total', '0.00')}"))
    body += [Spacer(1, 3 * mm), _totals(totals), Spacer(1, 8 * mm), _p("Agreement", H2)]
    body.append(_p(
        f"By signing, the customer agrees to pay CIMH the agreed total above for request {req.get('id', '')} "
        f"(quote version {ag.get('quoteVersion', '')}). Supplier items are shipped directly by the supplier. "
        "CIMH stock is reserved when this signed agreement is accepted. Return the signed copy through the "
        "CIMH Stores website."
    ))  # fmt: skip
    sig = Table(
        [[_p("Signature"), _p("Name"), _p("Date")], ["", "", ""], [_p("Position / organisation"), "", ""]],
        colWidths=[70 * mm, 64 * mm, 40 * mm], rowHeights=[6 * mm, 16 * mm, 6 * mm],
    )  # fmt: skip
    sig.setStyle(TableStyle([("LINEBELOW", (0, 1), (-1, 1), 0.6, INK), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    body += [Spacer(1, 10 * mm), sig]
    return _build("Agreement", req, body)


def invoice(req: dict[str, Any]) -> bytes:
    cur = req.get("currency") or "BBD"
    inv = req.get("invoice") or {}
    number = inv.get("number") or req.get("id", "")
    rows = [[_product(ln), src, str(ln.get("qty", "")), unit, total] for ln, src, unit, total in _chosen_prices(req)]
    body: list[Any] = [_parties(req, "Bill to"), Spacer(1, 6 * mm)]
    body.append(_table(["Item", "Source", "Qty", f"Unit ({cur})", f"Total ({cur})"], rows, [74, 36, 12, 26, 26]))
    totals = []
    if req.get("adminFee"):
        totals.append(("Administrative fee", f"{cur} {req['adminFee']}"))
    totals.append(("Amount due", f"{cur} {(req.get('agreement') or {}).get('total', '0.00')}"))
    body += [Spacer(1, 3 * mm), _totals(totals)]
    return _build("Invoice", req, body, subtitle=f"Invoice {number} · request {req.get('id', '')} · "
                  f"{_date(inv.get('date')) or _today()}")  # fmt: skip


def probono_invoice(req: dict[str, Any]) -> bytes:
    rows = [[_product(ln), str(ln.get("qty", "")), "No charge"] for ln in req.get("lines") or []]
    body: list[Any] = [_parties(req, "Recipient"), Spacer(1, 6 * mm)]
    body.append(_table(["Item", "Qty", "Value"], rows, [130, 16, 28], money_cols=1))
    body += [Spacer(1, 6 * mm), _p("Pro Bono items are supplied free of charge by CIMH.", SMALL)]
    return _build("Pro Bono delivery note", req, body)


def commercial_invoice(req: dict[str, Any]) -> bytes:
    """For customs on international shipments (ship-to country is not Barbados)."""
    cur = req.get("currency") or "BBD"
    ship = req.get("shipping") or {}
    if req.get("type") == "PROBONO":
        rows = [[_product(ln), str(ln.get("qty", "")), "0.00", "0.00"] for ln in req.get("lines") or []]
        note = "No commercial value: Pro Bono items donated by CIMH."
    else:
        rows = [[_product(ln), str(ln.get("qty", "")), u, t] for ln, src, u, t in _chosen_prices(req)
                if src == "CIMH stock"]  # fmt: skip
        note = "Supplier items ship directly from the supplier and are invoiced by them."
    shipper = [_p("Shipper", H2), _p(ORG), _p(ORG_ADDRESS)]
    consignee = [_p("Consignee", H2)] + [_p(x) for x in _address(req.get("shipTo"))]
    parties = Table([[shipper, consignee]], colWidths=[87 * mm, 87 * mm])
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    body: list[Any] = [parties, Spacer(1, 4 * mm)]
    if ship:
        code = str(ship.get("carrier") or "")
        carrier = {"FEDEX": "FedEx", "DHL": "DHL", "HAND": "Hand delivery"}.get(code, code)
        body.append(_p(f"Carrier: {carrier}" + (f" · tracking {ship['tracking']}" if ship.get("tracking") else "")))
    body += [
        Spacer(1, 4 * mm),
        _table(["Description", "Qty", f"Unit ({cur})", f"Total ({cur})"], rows, [104, 14, 28, 28]),
    ]
    body += [
        Spacer(1, 4 * mm),
        _p(note, SMALL),
        _p("Country of origin: as marked on goods. Reason for export: sale.", SMALL),
    ]
    return _build("Commercial invoice", req, body)


def _chop(text: str, font: str, size: float, width: float) -> list[str]:
    rows, cur = [], ""
    for ch in text:
        if cur and stringWidth(cur + ch, font, size) > width:
            rows.append(cur)
            cur = ""
        cur += ch
    return [*rows, cur] if cur else rows


def labels(product_id: str, product_name: str | None, barcodes: list[str]) -> bytes:
    """A4 sheet, 3 x 8 labels (70 x 37 mm): QR of the unit barcode, the code and the product name."""
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    c.setTitle(f"Labels {product_id}")
    cols, rows, w, h = 3, 8, 70 * mm, 37.125 * mm
    for i, code in enumerate(barcodes):
        slot = i % (cols * rows)
        if i and slot == 0:
            c.showPage()
        x = (slot % cols) * w
        y = A4[1] - (slot // cols + 1) * h
        qr = QrCodeWidget(code, barLevel="M")
        b = qr.getBounds()
        size = 28 * mm
        d = Drawing(size, size, transform=[size / (b[2] - b[0]), 0, 0, size / (b[3] - b[1]), 0, 0])
        d.add(qr)
        renderPDF.draw(d, c, x + 3 * mm, y + (h - size) / 2)
        c.setFillColor(INK)
        tx, width = x + 33 * mm, w - 36 * mm
        ty = y + h - 8 * mm
        # Codes have no spaces: break them by width, character by character (a 35-character product id).
        for font, size, text in (("Helvetica-Bold", 7, code), ("Helvetica", 7, product_name or "")):
            c.setFont(font, size)
            wrapped = simpleSplit(text, font, size, width) if " " in text else _chop(text, font, size, width)
            for row in wrapped[:4]:
                c.drawString(tx, ty, row)
                ty -= 3.2 * mm
            ty -= 1.5 * mm
    c.showPage()
    c.save()
    return buf.getvalue()
