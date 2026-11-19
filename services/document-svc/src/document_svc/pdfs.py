"""Generated PDFs (PRD D*): CIMH quote, quote agreement, invoice, Pro Bono invoice, commercial invoice, unit labels.

Rendered from order-svc's staff view of the request (GET /internal/requests/{id}). Values are drawn as text, never
interpreted as markup (reportlab Paragraph markup is escaped). Brand: logo blue #0084C8 for the header rule only;
body text is ink (Design Brief: the logo blue is not a text colour).
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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
PREVIEW_MARK = colors.Color(0.80, 0.11, 0.09, alpha=0.16)  # expiring red, faint: readable figures stay on top
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


def _build(
    title: str, req: dict[str, Any], body: list[Any], *, subtitle: str | None = None, mark: str | None = None
) -> bytes:
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
        if mark:  # a preview: across every page, under the content, so a printed copy can't pass for the real one
            c.setFillColor(PREVIEW_MARK)
            c.setFont("Helvetica-Bold", 54)
            c.translate(A4[0] / 2, A4[1] / 2)
            c.rotate(35)
            c.drawCentredString(0, 0, mark)
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


def _version(req: dict[str, Any]) -> int | None:
    """The quote version the agreement belongs to (else the latest sent)."""
    v = (req.get("agreement") or {}).get("quoteVersion")
    if v is None:
        v = max((q.get("version") or 0 for q in req.get("quotes") or []), default=None)
    return v if v is not None else (req.get("cimhQuote") or {}).get("version")


def _latest_quotes(req: dict[str, Any]) -> list[dict[str, Any]]:
    """Every supplier quote of the agreed (else the latest) quote version."""
    version = _version(req)
    return [q for q in req.get("quotes") or [] if q.get("version") == version]


def _source(line: dict[str, Any]) -> str | None:
    return line.get("source") or line.get("choice")  # `choice`: requests written before 2026-11-17


def _priced(req: dict[str, Any]) -> list[tuple[dict[str, Any], str, str, str, str | None]]:
    """(line, where it comes from, unit price, total, source) for every line, as staff fixed it in the quote."""
    supplier: dict[str, tuple[dict[str, Any], str | None]] = {}
    for q in _latest_quotes(req):
        for x in q.get("lines") or []:
            supplier[x["lineId"]] = (x, q.get("supplier"))
    cimh = {x["lineId"]: x for x in (req.get("cimhQuote") or {}).get("lines") or []}
    out = []
    for line in req.get("lines") or []:
        src = _source(line)
        if src == "CIMH" and line["lineId"] in cimh:
            price, where = cimh[line["lineId"]], "CIMH stock"
        else:
            price, name = supplier.get(line["lineId"], ({}, None))
            name = name or line.get("supplier")
            where = f"{name} (ships direct)" if name else "Supplier (ships direct)"
        out.append((line, where, price.get("unitPrice") or "—", price.get("total") or "—", src))
    return out


def _shipping(req: dict[str, Any]) -> list[tuple[str, str]]:
    """Estimated shipping per source: (label, amount)."""
    rows = []
    cq = req.get("cimhQuote") or {}
    if cq.get("lines") and cq.get("shippingEstimate") is not None:
        rows.append(("Estimated shipping, CIMH stock", cq["shippingEstimate"]))
    for q in _latest_quotes(req):
        if q.get("lines") and q.get("shippingEstimate") is not None:
            rows.append((f"Estimated shipping, {q.get('supplier') or 'supplier'}", q["shippingEstimate"]))
    return rows


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _price_table(req: dict[str, Any], cur: str) -> Table:
    rows = [[_product(ln), where, str(ln.get("qty", "")), unit, total] for ln, where, unit, total, _ in _priced(req)]
    return _table(["Item", "From", "Qty", f"Unit ({cur})", f"Total ({cur})"], rows, [70, 40, 12, 26, 26])


def _price_totals(req: dict[str, Any], cur: str, last: str) -> Table:
    items = sum((_money(t) for _, _, _, t, _ in _priced(req)), Decimal("0"))
    rows = [("Items", f"{cur} {items:.2f}")]
    rows += [(label, f"{cur} {_money(amount):.2f}") for label, amount in _shipping(req)]
    if req.get("adminFee") and _money(req["adminFee"]) > 0:
        rows.append(("Administrative fee (once per request)", f"{cur} {req['adminFee']}"))
    rows.append((last, f"{cur} {(req.get('agreement') or {}).get('total', '0.00')}"))
    return _totals(rows)


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
    body: list[Any] = [_parties(req), Spacer(1, 6 * mm), _p("Items supplied from CIMH stock", H2)]
    body.append(_table(["Item", "Qty", f"Unit ({cur})", f"Total ({cur})"], rows, [104, 14, 28, 28]))
    totals = [("CIMH stock items", f"{cur} {cq.get('total', '0.00')}")]
    if cq.get("shippingEstimate") is not None:
        totals.append(("Estimated shipping from CIMH", f"{cur} {cq['shippingEstimate']}"))
    body += [Spacer(1, 3 * mm), _totals(totals)]
    if cq.get("exchangeRate"):
        body.append(_p(f"Exchange rate used: 1 USD = {cq['exchangeRate']} BBD", SMALL))
    expires = _date(req.get("quoteExpiresAt"))
    held = f"These items are held for this request until the quote expires ({expires or '30 days from issue'}). "
    rest = "The quote agreement lists every item of the request, the admin fee and the total to sign."
    body += [Spacer(1, 6 * mm), _p(held + rest, SMALL)]
    return _build("CIMH stock quote", req, body)


def agreement(req: dict[str, Any], *, preview: bool = False) -> bytes:
    """The one page the customer signs ("view and sign"): every item, its price and source, estimated shipping,
    the total, and a signature line. `preview`: staff check it before sending; marked, never emailed."""
    cur = req.get("currency") or "BBD"
    ag = req.get("agreement") or {}
    version = ag.get("quoteVersion", _version(req))
    expires = _date(req.get("quoteExpiresAt"))
    body: list[Any] = [_parties(req), Spacer(1, 6 * mm), _p("Items in this request", H2), _price_table(req, cur)]
    body += [Spacer(1, 3 * mm), _price_totals(req, cur, "Total to sign")]
    # Supplier quotes priced in USD were converted to BBD per supplier; name each rate so the customer can
    # check the converted prices against the supplier's own quote attached to the request.
    for q in _latest_quotes(req):
        if q.get("sourceCurrency") == "USD" and q.get("exchangeRate"):
            body.append(_p(f"{q.get('supplier') or 'Supplier'} quoted in USD, converted at 1 USD = "
                           f"{q['exchangeRate']} BBD.", SMALL))  # fmt: skip
    body += [Spacer(1, 8 * mm), _p("Agreement", H2)]
    body.append(_p(
        f"By signing, the customer agrees to pay CIMH the total above for request {req.get('id', '')} "
        f"(quote version {version}). Items from CIMH stock are held for this request until the quote expires"
        f"{' on ' + expires if expires else ''} and are shipped by CIMH. Supplier items are ordered by CIMH once the "
        "signed agreement is received and are shipped directly to the customer by the supplier. Shipping amounts "
        "are estimates; the total above is the amount CIMH invoices."
    ))  # fmt: skip
    body.append(Spacer(1, 2 * mm))
    body.append(_p("Sign below and upload the signed copy (a scan or a phone photo is fine) on the CIMH Stores "
                   "website, where you can also cancel the request.", SMALL))  # fmt: skip
    sig = Table(
        [[_p("Signature"), _p("Name"), _p("Date")], ["", "", ""], [_p("Position / organisation"), "", ""]],
        colWidths=[70 * mm, 64 * mm, 40 * mm], rowHeights=[6 * mm, 16 * mm, 6 * mm],
    )  # fmt: skip
    sig.setStyle(TableStyle([("LINEBELOW", (0, 1), (-1, 1), 0.6, INK), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    body += [Spacer(1, 10 * mm), sig]
    subtitle = f"Request {req.get('id', '')} · quote version {version} · {_today()}"
    subtitle += f" · valid until {expires}" if expires else ""
    if preview:
        subtitle = "Preview, not sent · " + subtitle
    return _build("Quote agreement", req, body, subtitle=subtitle, mark="PREVIEW · NOT SENT" if preview else None)


def invoice(req: dict[str, Any]) -> bytes:
    cur = req.get("currency") or "BBD"
    inv = req.get("invoice") or {}
    number = inv.get("number") or req.get("id", "")
    body: list[Any] = [_parties(req, "Bill to"), Spacer(1, 6 * mm), _price_table(req, cur)]
    body += [Spacer(1, 3 * mm), _price_totals(req, cur, "Amount due")]  # the signed total (owner, 2026-11-17)
    return _build("Invoice", req, body, subtitle=f"Invoice {number} · request {req.get('id', '')} · "
                  f"{_date(inv.get('date')) or _today()}")  # fmt: skip


def probono_invoice(req: dict[str, Any]) -> bytes:
    rows = [[_product(ln), str(ln.get("qty", "")), "No charge"] for ln in req.get("lines") or []]
    body: list[Any] = [_parties(req, "Recipient"), Spacer(1, 6 * mm)]
    body.append(_table(["Item", "Qty", "Value"], rows, [130, 16, 28], money_cols=1))
    body += [Spacer(1, 6 * mm), _p("Pro Bono items are supplied free of charge by CIMH.", SMALL)]
    return _build("Pro Bono delivery note", req, body)


def commercial_invoice(req: dict[str, Any], shipment_id: str | None = None) -> bytes:
    """For customs on a CIMH parcel leaving Barbados: the lines of that one shipment (all CIMH lines without one)."""
    cur = req.get("currency") or "BBD"
    ship = next((s for s in req.get("shipments") or [] if s.get("id") == shipment_id), None) or {}
    keep = set(ship.get("lineIds") or []) or None
    if req.get("type") == "PROBONO":
        rows = [[_product(ln), str(ln.get("qty", "")), "0.00", "0.00"] for ln in req.get("lines") or []
                if keep is None or ln.get("lineId") in keep]  # fmt: skip
        note = "No commercial value: Pro Bono items donated by CIMH."
    else:
        rows = [[_product(ln), str(ln.get("qty", "")), u, t] for ln, _, u, t, src in _priced(req)
                if src == "CIMH" and (keep is None or ln.get("lineId") in keep)]  # fmt: skip
        note = "Supplier items ship directly from the supplier and are invoiced by them."
    shipper = [_p("Shipper", H2), _p(ORG), _p(ORG_ADDRESS)]
    consignee = [_p("Consignee", H2)] + [_p(x) for x in _address(req.get("shipTo"))]
    parties = Table([[shipper, consignee]], colWidths=[87 * mm, 87 * mm])
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    body: list[Any] = [parties, Spacer(1, 4 * mm)]
    if ship:
        code = str(ship.get("carrier") or "")
        carrier = ship.get("carrierName") or {
            "FEDEX": "FedEx",
            "DHL": "DHL",
            "UPS": "UPS",
            "HAND": "Hand delivery",
        }.get(code, code)
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
