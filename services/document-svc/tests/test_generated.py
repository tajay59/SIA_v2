"""PDFs rendered from order events (consumer.py): one file per event, same file on redelivery."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from cimh_common.outbox import EventEnvelope
from document_svc.consumer import make_handler

from .conftest import STAFF, USER, Ctx, check_event, request_doc


def _event(etype: str, **payload: Any) -> EventEnvelope:
    return EventEnvelope(type=etype, correlationId="c1", actorId="USRSTAFF", payload={"orderId": "ORD1", **payload})


def _run(ctx: Ctx, event: EventEnvelope) -> None:
    asyncio.run(make_handler(ctx.client.app.state.documents)(event))


def _generated(ctx: Ctx) -> list[EventEnvelope]:
    return [e for t, _, e in ctx.publisher.sent if e.type == "document.generated"]


@pytest.mark.parametrize(
    ("event", "kind"),
    [
        (_event("order.quoted", customer="USRUSER", quoteVersion=1, expiresAt="2026-12-08T00:00:00Z",
                currency="BBD", cimhLineIds=["L1"]), "cimh_quote"),
        (_event("order.agreement_requested", customer="USRUSER", quoteVersion=1, lines=[], total="505.00",
                currency="BBD"), "agreement"),
        (_event("order.delivered", orderType="PAID", customer="USRUSER", **{"from": "SHIPPED", "to": "DELIVERED"}),
         "invoice"),
        (_event("order.delivered", orderType="PROBONO", customer="USRUSER", **{"from": "SHIPPED", "to": "DELIVERED"}),
         "probono_invoice"),
    ],
)  # fmt: skip
def test_each_event_renders_one_pdf(ctx: Ctx, event: EventEnvelope, kind: str) -> None:
    _run(ctx, event)
    [gen] = _generated(ctx)
    check_event(gen)
    assert gen.payload["kind"] == kind
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


def test_redelivery_rewrites_the_same_file(ctx: Ctx) -> None:
    event = _event("order.agreement_requested", customer="USRUSER", quoteVersion=1, lines=[], total="505.00",
                   currency="BBD")  # fmt: skip
    _run(ctx, event)
    _run(ctx, event)
    a, b = _generated(ctx)
    assert a.payload["fileId"] == b.payload["fileId"]
    assert len(list((ctx.root / "protected" / "orders" / "ORD1").glob("*.pdf"))) == 1


def test_supplier_only_quote_renders_nothing(ctx: Ctx) -> None:
    _run(ctx, _event("order.quoted", customer="USRUSER", quoteVersion=1, expiresAt="2026-12-08T00:00:00Z",
                     currency="BBD", cimhLineIds=[]))  # fmt: skip
    assert _generated(ctx) == []


@pytest.mark.parametrize(("country", "expected"), [("BB", 0), ("TT", 1)])
def test_commercial_invoice_only_for_international_shipments(ctx: Ctx, country: str, expected: int) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "SHIPPED", shipping={"carrier": "DHL", "tracking": "123"})
    ctx.orders.requests["ORD1"]["shipTo"]["country"] = country
    _run(ctx, _event("order.shipped", customer="USRUSER", carrier="DHL", tracking="123", notifyCustomer=True))
    assert [e.payload["kind"] for e in _generated(ctx)] == ["commercial_invoice"] * expected


def test_probono_commercial_invoice(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "SHIPPED", type="PROBONO", shipping={"carrier": "HAND"})
    ctx.orders.requests["ORD1"]["shipTo"]["country"] = "GY"
    _run(ctx, _event("order.shipped", customer="USRUSER", carrier="HAND", tracking=None, notifyCustomer=True))
    assert len(_generated(ctx)) == 1


def test_other_events_are_ignored_and_missing_ids_go_to_dlq(ctx: Ctx) -> None:
    _run(ctx, _event("order.submitted", type="PAID", customer="USRUSER", lines=[]))
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
    _run(ctx, _event("order.agreement_requested", customer="USRUSER", quoteVersion=1, lines=[], total="505.00",
                     currency="BBD"))  # fmt: skip
    assert len(_generated(ctx)) == 1


def test_revised_quote_renders_a_new_cimh_quote(ctx: Ctx) -> None:
    _run(ctx, _event("order.quote_revised", customer="USRUSER", **{"from": "QUOTED", "to": "QUOTED"}))
    assert [e.payload["kind"] for e in _generated(ctx)] == ["cimh_quote"]
