"""PDFs rendered from order events (consumer.py): one file per event and kind, same file on redelivery.
"View and sign" (2026-11-17): the agreement comes with the quote (order.quoted / order.quote_revised)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import pytest
from reportlab.platypus import Paragraph, Table

from cimh_common.outbox import EventEnvelope
from document_svc import pdfs
from document_svc.consumer import make_handler

from .conftest import ADMIN, INVENTORY, STAFF, USER, Ctx, check_event, request_doc


def _event(etype: str, **payload: Any) -> EventEnvelope:
    return EventEnvelope(type=etype, correlationId="c1", actorId="USRSTAFF", payload={"orderId": "ORD1", **payload})


def _quoted(etype: str = "order.quoted", version: int = 1, cimh: list[str] | None = None, **kw: Any) -> EventEnvelope:
    payload = {
        "customer": "USRUSER",
        "quoteVersion": version,
        "expiresAt": "2026-12-08T00:00:00Z",
        "currency": "BBD",
        "total": "560.00",
        "lines": [],
        "cimhLineIds": ["L1"] if cimh is None else cimh,
    }
    return _event(etype, **(payload | kw))  # fmt: skip


def _run(ctx: Ctx, event: EventEnvelope) -> None:
    asyncio.run(make_handler(ctx.client.app.state.documents)(event))


def _generated(ctx: Ctx) -> list[EventEnvelope]:
    return [e for t, _, e in ctx.publisher.sent if e.type == "document.generated"]


def _text(req: dict[str, Any], render: Any) -> list[str]:
    """Every text drawn on the page (paragraphs, also inside tables), from the flowables handed to the layout."""
    seen: list[Any] = []
    real = pdfs._build

    def capture(title: str, r: dict[str, Any], body: list[Any], **kw: Any) -> bytes:
        seen.extend([title, kw.get("subtitle") or "", *body])
        return real(title, r, body, **kw)

    pdfs._build = capture  # type: ignore[assignment]
    try:
        render(req)
    finally:
        pdfs._build = real  # type: ignore[assignment]
    out: list[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, Paragraph):
            out.append(x.getPlainText())
        elif isinstance(x, Table):
            for row in x._cellvalues:
                for cell in row:
                    # layout turns cells into tuples (reportlab's _ExpandedCellTuple)
                    for item in cell if isinstance(cell, list | tuple) else [cell]:
                        walk(item)

    for x in seen:
        walk(x)
    return out


@pytest.mark.parametrize(
    ("event", "kinds"),
    [
        (_quoted(), ["agreement", "cimh_quote"]),
        (_quoted(cimh=[]), ["agreement"]),  # supplier-only quote: no CIMH stock quote
        (_event("order.delivered", orderType="PAID", customer="USRUSER", **{"from": "SHIPPED", "to": "DELIVERED"}),
         ["invoice"]),
        (_event("order.delivered", orderType="PROBONO", customer="USRUSER", **{"from": "SHIPPED", "to": "DELIVERED"}),
         ["probono_invoice"]),
    ],
)  # fmt: skip
def test_each_event_renders_its_pdfs(ctx: Ctx, event: EventEnvelope, kinds: list[str]) -> None:
    _run(ctx, event)
    gens = _generated(ctx)
    assert [g.payload["kind"] for g in gens] == kinds
    for gen in gens:
        check_event(gen)
        assert gen.payload["customer"] == "USRUSER"  # notification-svc mails the customer
        assert gen.payload["orderId"] == "ORD1"
        assert gen.correlationId == "c1"
        fid = gen.payload["fileId"]
        pdf = (ctx.root / "protected" / "orders" / "ORD1" / f"{fid}.pdf").read_bytes()
        assert pdf.startswith(b"%PDF")
        assert len(pdf) == gen.payload["size"]
        # customers download it like any other file; generated documents can't be deleted
        assert ctx.client.get(ctx.url(f"/files/{fid}"), headers=USER).status_code == 200
        r = ctx.client.request("DELETE", ctx.url(f"/files/{fid}"), headers=STAFF, json={"reason": "remove"})
        assert r.status_code == 409
    if "agreement" in kinds:
        assert gens[0].payload["quoteVersion"] == 1  # order-svc offers it for signing only for this version
        assert gens[0].payload["name"] == "Agreement-ORD1-v1.pdf"


def test_the_agreement_lists_every_item_shipping_the_total_and_a_signature_line() -> None:
    text = _text(request_doc("ORD1"), pdfs.agreement)
    page = " | ".join(text)
    assert text[0] == "Quote agreement"
    assert "quote version 1" in text[1]
    for want in (
        "Rain gauge — Acme",
        "CIMH stock",
        "Anemometer",
        "Vaisala (ships direct)",
        "150.00",
        "180.00",
        "Estimated shipping, CIMH stock",
        "BBD 20.00",
        "Estimated shipping, Vaisala",
        "BBD 35.00",
        "Administrative fee (once per request)",
        "Total to sign",
        "BBD 560.00",
        "Signature",
        "Name",
        "Date",
    ):
        assert want in page, want  # fmt: skip
    assert "Items | BBD 480.00" in page
    assert "choose" not in page.lower()  # nothing to choose: view and sign


def test_usd_supplier_rates_are_named_on_the_agreement() -> None:
    req = request_doc("ORD1")
    req["quotes"][0] |= {"sourceCurrency": "USD", "exchangeRate": "2.0225"}
    assert "Vaisala quoted in USD, converted at 1 USD = 2.0225 BBD." in _text(req, pdfs.agreement)


def test_automatic_invoice_charges_the_signed_total() -> None:
    """Estimated shipping from the agreement (20 + 35), not what the parcels cost: total = the signed 560.00."""
    req = request_doc("ORD1", "DELIVERED", shipments=[{"id": "S1", "cost": "99.00", "lineIds": ["L1"]}])
    data = pdfs.auto_invoice_data(req, "invoice")
    lines = sum(Decimal(x["unitPrice"]) * x["qty"] for x in data["lines"])
    assert (data["fees"], data["shipping"], data["discount"]) == ("25.00", "55.00", "0.00")
    assert lines + Decimal(data["fees"]) + Decimal(data["shipping"]) == Decimal("560.00")


def test_a_quote_revised_meanwhile_is_not_rendered(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] |= {"quoteVersion": 2}
    ctx.orders.requests["ORD1"]["agreement"]["quoteVersion"] = 2
    ctx.orders.requests["ORD1"]["cimhQuote"]["version"] = 2
    _run(ctx, _quoted(version=1))  # late event for version 1
    assert _generated(ctx) == []
    _run(ctx, _quoted("order.quote_revised", version=2, **{"from": "QUOTED", "to": "QUOTED"}))
    assert [e.payload["quoteVersion"] for e in _generated(ctx)] == [2, 2]


def test_redelivery_rewrites_the_same_files(ctx: Ctx) -> None:
    event = _quoted()
    _run(ctx, event)
    _run(ctx, event)
    first, second = _generated(ctx)[:2], _generated(ctx)[2:]
    assert [e.payload["fileId"] for e in first] == [e.payload["fileId"] for e in second]
    assert len(list((ctx.root / "protected" / "orders" / "ORD1").glob("*.pdf"))) == 2


def test_an_old_revision_event_reads_the_cimh_lines_from_the_request(ctx: Ctx) -> None:
    _run(ctx, _event("order.quote_revised", customer="USRUSER", **{"from": "QUOTED", "to": "QUOTED"}))
    assert [e.payload["kind"] for e in _generated(ctx)] == ["agreement", "cimh_quote"]


CIMH_BOX = {"id": "SHP1", "source": "CIMH", "lineIds": ["L1"], "carrier": "DHL", "tracking": "123"}


def _shipment_event(source: str = "CIMH", shipment: str = "SHP1") -> Any:
    return _event("order.shipment_recorded", customer="USRUSER", shipmentId=shipment, source=source,
                  lineIds=["L1"], carrier="DHL", tracking="123", notifyCustomer=True)  # fmt: skip


@pytest.mark.parametrize(
    ("country", "source", "expected"), [("BB", "CIMH", 0), ("TT", "CIMH", 1), ("TT", "SUPPLIER", 0)]
)
def test_commercial_invoice_only_for_cimh_parcels_leaving_barbados(
    ctx: Ctx, country: str, source: str, expected: int
) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "PURCHASING", shipments=[CIMH_BOX])
    ctx.orders.requests["ORD1"]["shipTo"]["country"] = country
    _run(ctx, _shipment_event(source))
    _run(ctx, _event("order.shipped", customer="USRUSER", shipments=1))  # no longer makes anything
    assert [e.payload["kind"] for e in _generated(ctx)] == ["commercial_invoice"] * expected


def test_commercial_invoice_lists_only_the_shipment_lines() -> None:
    req = request_doc("ORD1", "SHIPPED", shipments=[CIMH_BOX])
    data = pdfs.auto_invoice_data(req, "commercial_invoice", "SHP1")
    assert [x["lineId"] for x in data["lines"]] == ["L1"]  # the supplier ships L2 and invoices it
    assert pdfs.built_invoice(req, data | {"number": "C-1", "date": "2026-11-24"}).startswith(b"%PDF")


def test_probono_commercial_invoice(ctx: Ctx) -> None:
    box = {**CIMH_BOX, "carrier": "HAND", "tracking": None}
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "SHIPPED", type="PROBONO", shipments=[box])
    ctx.orders.requests["ORD1"]["shipTo"]["country"] = "GY"
    _run(ctx, _shipment_event())
    assert len(_generated(ctx)) == 1


def test_other_events_are_ignored_and_missing_ids_go_to_dlq(ctx: Ctx) -> None:
    _run(ctx, _event("order.submitted", type="PAID", customer="USRUSER", lines=[]))
    _run(ctx, _event("order.agreement_requested", customer="USRUSER", quoteVersion=1))  # old flow: no longer made
    assert ctx.publisher.sent == []
    with pytest.raises(ValueError, match="lacks orderId"):
        asyncio.run(make_handler(ctx.client.app.state.documents)(
            EventEnvelope(type="order.delivered", correlationId="c", payload={})))  # fmt: skip


def test_request_gone_renders_nothing(ctx: Ctx) -> None:
    del ctx.orders.requests["ORD1"]
    _run(ctx, _event("order.delivered", orderType="PAID", customer="USRUSER", **{"from": "SHIPPED", "to": "DELIVERED"}))
    assert _generated(ctx) == []


def test_text_is_not_interpreted_as_markup(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"]["customerName"] = "<b>Bobby</b> & <font size=90>Tables</font>"
    ctx.orders.requests["ORD1"]["lines"][0]["product"]["name"] = "<para>x</para>"
    _run(ctx, _quoted())
    assert len(_generated(ctx)) == 2


@pytest.mark.req("O5a")
def test_staff_preview_the_agreement_before_sending_the_quote(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "QUOTING")
    for who in (STAFF, ADMIN):
        r = ctx.client.get(ctx.url("/requests/ORD1/agreement-preview"), headers=who)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["cache-control"] == "private, no-store"
        assert r.headers["content-disposition"] == 'inline; filename="agreement-preview-ORD1.pdf"'
        assert r.content.startswith(b"%PDF")
    assert ctx.publisher.sent == []  # nothing announced
    assert ctx.orders.attached == []  # nothing attached to the request
    assert not [f for f in ctx.root.rglob("*") if f.is_file()]  # nothing stored


def test_the_preview_is_marked_and_says_so() -> None:
    text = _text(request_doc("ORD1"), lambda r: pdfs.agreement(r, preview=True))
    assert text[1].startswith("Preview, not sent · Request ORD1 · quote version 1")
    assert "BBD 560.00" in " | ".join(text)  # the same figures as the agreement that will be sent
    assert not _text(request_doc("ORD1"), pdfs.agreement)[1].startswith("Preview")


def test_only_staff_preview_and_order_svc_refusals_pass_through(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "QUOTING")
    url = ctx.url("/requests/ORD1/agreement-preview")
    assert ctx.client.get(url).status_code == 401
    assert ctx.client.get(url, headers=USER).status_code == 403  # the requester sees the real one once sent
    assert ctx.client.get(url, headers=INVENTORY).status_code == 403
    assert ctx.client.get(ctx.url("/requests/ORDnope/agreement-preview"), headers=STAFF).status_code == 404
    ctx.orders.requests["ORD1"]["draftProblem"] = "Enter the estimated shipping from Vaisala (0.00 if there is none)"
    r = ctx.client.get(url, headers=STAFF)
    assert (r.status_code, r.json()["code"]) == (422, "SHIPPING_ESTIMATE_REQUIRED")
    assert "Vaisala" in r.json()["detail"]
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "ACCEPTED")
    assert ctx.client.get(url, headers=STAFF).status_code == 409
    ctx.orders.down = True
    assert ctx.client.get(url, headers=STAFF).status_code == 503


def _delivered() -> EventEnvelope:
    return _event("order.delivered", orderType="PAID", customer="USRUSER", **{"from": "SHIPPED", "to": "DELIVERED"})


def test_automatic_invoice_is_recorded_and_skipped_when_one_exists(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "DELIVERED", invoice={"number": "D-7"})
    event = _delivered()
    _run(ctx, event)
    ((rid, kind, body),) = ctx.orders.recorded
    assert (rid, kind, body["source"], body["number"], body["rev"]) == ("ORD1", "invoice", "AUTO", "D-7", None)
    assert ctx.orders.requests["ORD1"]["invoices"]["invoice"]["source"] == "AUTO"
    _run(ctx, event)  # redelivered: the same file, published again, nothing recorded twice
    assert len(ctx.orders.recorded) == 1
    assert [e.payload["fileId"] for e in _generated(ctx)] == [body["file"]["id"]] * 2
    _run(ctx, _delivered())  # another event: an invoice exists, none made
    assert len(_generated(ctx)) == 2


def test_no_automatic_invoice_after_staff_voided_one(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "DELIVERED", voidedInvoices=[{"kind": "invoice"}])
    _run(ctx, _delivered())
    assert _generated(ctx) == []


def test_automatic_invoice_numbers_come_from_the_series_and_skip_a_taken_one(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "DELIVERED")
    ctx.orders.numbers.add("invoice:inv-0100")  # taken a moment ago by another request
    ctx.orders.next_number = "INV-0100"
    calls = iter(["INV-0100", "INV-0101"])

    async def nxt(kind: str) -> str | None:
        return next(calls)

    ctx.orders.next_invoice_number = nxt  # type: ignore[method-assign]
    _run(ctx, _delivered())
    assert ctx.orders.requests["ORD1"]["invoices"]["invoice"]["number"] == "INV-0101"
    assert len(list((ctx.root / "protected" / "orders" / "ORD1").glob("*.pdf"))) == 1
