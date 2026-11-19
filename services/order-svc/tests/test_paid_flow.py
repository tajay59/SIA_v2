"""Paid requests, "view and sign" (owner, 2026-11-17): staff fix the source of every line and the estimated
shipping when they send the quote (O5, O5a, O7, O15); the agreement comes with the quote; the customer signs and
uploads it, or cancels (O6, O6a); then purchasing, picking, shipping, delivery (O8-O11). TAD §7.2; the reservation
round trip with inventory is driven by its events."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from bson.decimal128 import Decimal128

from order_svc import upgrade
from order_svc.store import now

from .conftest import ADMIN, DOCUMENT, PEER, STAFF, USER, Ctx, check_event

SUPPLIER = "Campbell Scientific"


def draft(
    *,
    cimh: list[str] | None = None,
    rate: str | None = None,
    prices: Any = None,
    ship: str | None = "0.00",
    cimh_ship: str | None = "0.00",
    supplier: str = SUPPLIER,
) -> dict[str, Any]:
    """A quote draft: lines not taken from CIMH stock are priced by one supplier."""
    if prices is None:
        default = {"L1": "120.00", "L2": "50.00"}
        prices = [{"lineId": k, "unitPrice": v} for k, v in default.items() if k not in (cimh or [])]
    body: dict[str, Any] = {"supplierQuotes": []}
    if prices:
        sq: dict[str, Any] = {"supplier": supplier, "lines": prices, "fileIds": ["FILq1"]}
        if ship is not None:
            sq["shippingEstimate"] = ship
        body["supplierQuotes"].append(sq)
    if cimh is not None or rate:
        body["cimh"] = {"lineIds": cimh or [], "exchangeRate": rate}
        if cimh_ship is not None:
            body["cimh"]["shippingEstimate"] = cimh_ship
    return body


def quote(ctx: Ctx, rid: str, **kw: Any) -> dict[str, Any]:
    ctx.ok(rid, "quote-draft", draft(**kw), method="PUT")
    return ctx.ok(rid, "send-quote")


def reserve(ctx: Ctx, rid: str, line: str, units: list[str]) -> None:
    """What inventory does on order.quoted, reported back through stock.reserved."""
    ctx.run(ctx.svc.stock_reserved({"orderId": rid, "lines": [{"lineId": line, "units": units}]}))
    ctx.deps.reserved.setdefault(rid, set()).update(units)


def sign(ctx: Ctx, rid: str, version: int = 1) -> dict[str, Any]:
    """The customer uploads the signed agreement (document-svc stamps the quote version) and accepts."""
    signed = ctx.attach(rid, "signed_agreement", quote_version=version)
    return ctx.ok(rid, "accept", {"quoteVersion": version, "signedAgreementFileId": signed}, USER)


def to_quoting(ctx: Ctx, currency: str = "BBD") -> str:
    ctx.deps.stock = {"MET1": 5, "MET2": 0}
    rid = ctx.paid_request("MET1", "MET2", currency=currency)
    started = ctx.ok(rid, "start-quoting")
    assert [ln["cimhAvailable"] for ln in started["lines"]] == [True, False]
    return rid


@pytest.mark.req("O5a")
def test_view_and_sign_journey_with_cimh_and_supplier_lines(ctx: Ctx) -> None:
    ctx.deps.fee = Decimal("25.00")
    rid = to_quoting(ctx)
    q = quote(ctx, rid, cimh=["L1"], ship="30.00", cimh_ship="15.00")
    assert q["status"] == "QUOTED"
    assert q["quoteExpiresAt"]
    assert ctx.deps.availability_calls[-1] == rid  # stock re-checked at send, counting what this request holds
    # Staff fixed the source of every line: nothing is left for the customer to choose.
    assert [(ln["source"], ln["supplier"]) for ln in q["lines"]] == [("CIMH", None), ("SUPPLIER", SUPPLIER)]
    (sq,) = q["quotes"]
    assert (sq["supplier"], sq["total"], sq["shippingEstimate"]) == (SUPPLIER, "100.00", "30.00")
    assert q["cimhQuote"]["lines"] == [
        {"lineId": "L1", "unitPrice": "100.00", "total": "200.00", "unitCostBBD": "100.00"}
    ]
    assert q["cimhQuote"]["shippingEstimate"] == "15.00"
    assert q["adminFee"] == "25.00"
    # The agreement comes with the quote: 200 CIMH + 100 supplier + 30 + 15 shipping + 25 admin fee.
    assert q["agreement"]["quoteVersion"] == 1
    assert q["agreement"]["total"] == "370.00"
    assert q["agreement"]["fileId"] is None  # until document-svc has made the PDF
    (quoted,) = ctx.events(rid, "order.quoted")
    p = quoted["payload"]
    assert (p["quoteVersion"], p["total"], p["cimhLineIds"]) == (1, "370.00", ["L1"])
    assert [(x["lineId"], x["source"]) for x in p["lines"]] == [("L1", "CIMH"), ("L2", "SUPPLIER")]
    assert p["shippingEstimates"] == [
        {"source": "SUPPLIER", "supplier": SUPPLIER, "amount": "30.00"},
        {"source": "CIMH", "supplier": None, "amount": "15.00"},
    ]

    # The customer sees the supplier (they hold its quote) but not costs, purchase orders or the draft.
    mine = ctx.get(rid, USER)
    assert mine["quotes"][0]["supplier"] == SUPPLIER
    assert "unitCostBBD" not in mine["cimhQuote"]["lines"][0]
    assert "purchaseOrders" not in mine
    assert "quoteDraft" not in mine
    assert set(mine["allowedActions"]) == {"accept", "decline"}  # view and sign, or cancel
    assert ctx.get(rid, PEER)["allowedActions"] == []  # same organisation: read only
    assert mine["lines"][0]["reservation"] == {"status": "NONE"}

    # Inventory reserves the CIMH line on order.quoted; document-svc renders the agreement.
    reserve(ctx, rid, "L1", ["MET1_aa", "MET1_bb"])
    assert ctx.get(rid, USER)["lines"][0]["reservation"] == {"status": "RESERVED"}  # units are staff-only
    agreement_pdf = ctx.attach(rid, "agreement", quote_version=1)
    assert ctx.get(rid, USER)["agreement"]["fileId"] == agreement_pdf

    # Accepting needs the signed copy, not the generated PDF.
    r = ctx.act(rid, "accept", {"quoteVersion": 1, "signedAgreementFileId": agreement_pdf}, USER)
    assert r.status_code == 422
    assert r.json()["code"] == "AGREEMENT_REQUIRED"
    assert ctx.act(rid, "accept", {"quoteVersion": 1, "signedAgreementFileId": "FILx"}, PEER).status_code == 403
    signed = ctx.attach(rid, "signed_agreement", quote_version=1)
    v = ctx.get(rid)["version"]
    r = ctx.client.post(
        ctx.url(f"/requests/{rid}/accept"),
        headers={**USER, "If-Match": str(v), "X-Real-IP": "203.0.113.7"},
        json={"quoteVersion": 1, "signedAgreementFileId": signed},
    )
    assert r.status_code == 200, r.text
    acc = r.json()
    assert acc["status"] == "ACCEPTED"
    assert acc["acceptance"]["signedAgreementFileId"] == signed
    assert acc["agreement"]["signedFileId"] == signed
    assert ctx.doc(rid)["acceptance"]["ip"] == "203.0.113.7"
    (accepted,) = ctx.events(rid, "order.accepted")
    assert [(x["lineId"], x["source"]) for x in accepted["payload"]["lines"]] == [("L1", "CIMH"), ("L2", "SUPPLIER")]
    assert ctx.get(rid)["lines"][0]["reservation"] == {"status": "RESERVED", "units": ["MET1_aa", "MET1_bb"]}
    assert acc["lines"][1]["reservation"] is None

    # Staff verify the signature and order the supplier line.
    r = ctx.act(rid, "purchase-orders", {"agreementVerified": False, "purchaseOrders": []})
    assert r.status_code == 422
    assert r.json()["code"] == "AGREEMENT_NOT_VERIFIED"
    r = ctx.act(rid, "purchase-orders", {"agreementVerified": True, "purchaseOrders": [
        {"supplier": "Campbell", "poNumber": "PO-1", "lineIds": ["L1"]}]})  # fmt: skip
    assert r.status_code == 422  # L1 comes from stock, not a supplier
    po = ctx.ok(rid, "purchase-orders", {"agreementVerified": True, "purchaseOrders": [
        {"supplier": "Campbell", "poNumber": "PO-1", "lineIds": ["L2"]}]})  # fmt: skip
    assert po["status"] == "PURCHASING"
    assert po["agreement"]["verified"]["by"]["id"] == "USRSTAFF"
    assert po["purchaseOrders"][0]["poNumber"] == "PO-1"
    assert "pick" in po["allowedActions"]

    # Only the CIMH line is picked; supplier items ship direct.
    def pick(line: str, unit: str, key: str) -> Any:
        h = {**STAFF, "Idempotency-Key": key}
        return ctx.client.post(ctx.url(f"/requests/{rid}/picks"), headers=h, json={"lineId": line, "unit": unit})

    assert pick("L2", "MET2_xx", "k0").json()["code"] == "LINE_NOT_PICKABLE"
    assert pick("L1", "MET2_xx", "k1").json()["code"] == "UNIT_WRONG_PRODUCT"
    assert pick("L1", "MET1_zz", "k2").json()["code"] == "UNIT_NOT_RESERVED_FOR_ORDER"
    r = ctx.act(rid, "ship", {"carrier": "DHL", "tracking": "123", "date": "2026-11-09"})
    assert r.status_code == 409
    assert r.json()["code"] == "PICKING_INCOMPLETE"
    assert pick("L1", "MET1_aa", "k3").status_code == 200
    assert pick("L1", "MET1_aa", "k3").status_code == 200  # replayed key
    assert pick("L1", "MET1_bb", "k4").json()["lines"][0]["picked"][1]["barcode"] == "MET1_bb"
    assert ctx.deps.picks == [("MET1_aa", rid, "USRSTAFF"), ("MET1_bb", rid, "USRSTAFF")]

    r = ctx.act(rid, "ship", {"carrier": "DHL", "date": "2026-11-09"})
    assert r.status_code == 422
    assert r.json()["code"] == "TRACKING_REQUIRED"
    shipped = ctx.ok(rid, "ship", {"carrier": "DHL", "tracking": "JD0001", "date": "2026-11-09", "cost": "45.00"})
    assert shipped["status"] == "SHIPPED"
    assert "JD0001" in shipped["shipping"]["trackingUrl"]
    (evt,) = ctx.events(rid, "order.shipped")
    assert evt["payload"]["tracking"] == "JD0001"
    done = ctx.ok(rid, "deliver", {"invoiceNumber": "INV-2026-001"})
    assert done["status"] == "DELIVERED"
    assert done["invoice"]["number"] == "INV-2026-001"
    assert [h["to"] for h in done["history"]] == ["SUBMITTED", "QUOTING", "QUOTED", "ACCEPTED", "PURCHASING",
                                                  "SHIPPED", "DELIVERED"]  # fmt: skip
    ctx.events(rid)  # every event matches its schema


def test_supplier_only_request_ships_without_picking(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    q = quote(ctx, rid)
    assert q["cimhQuote"] is None
    assert q["agreement"]["total"] == "340.00"  # 240 + 100, shipping 0.00, no fee
    sign(ctx, rid)
    ctx.ok(rid, "purchase-orders", {"agreementVerified": True, "purchaseOrders": [
        {"supplier": "Campbell", "poNumber": "PO-9", "lineIds": ["L1", "L2"]}]})  # fmt: skip
    assert "pick" not in ctx.get(rid)["allowedActions"]
    assert (
        ctx.ok(rid, "ship", {"carrier": "HAND", "note": "Collected by Una", "date": "2026-11-09"})["status"]
        == "SHIPPED"
    )


def test_a_supplier_without_lines_is_left_out(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    body = draft()
    body["supplierQuotes"].append({"supplier": "Vaisala", "lines": [], "fileIds": ["FILq2"]})
    ctx.ok(rid, "quote-draft", body, method="PUT")
    q = ctx.ok(rid, "send-quote")
    assert [x["supplier"] for x in q["quotes"]] == [SUPPLIER]


@pytest.mark.req("O15")
def test_usd_needs_an_exchange_rate_for_cimh_lines_and_the_fee(ctx: Ctx) -> None:
    ctx.deps.fee = Decimal("20.00")
    rid = to_quoting(ctx, "USD")
    ctx.ok(rid, "quote-draft", draft(prices=[{"lineId": "L1", "unitPrice": "60.00"},
                                             {"lineId": "L2", "unitPrice": "25.00"}]), method="PUT")  # fmt: skip
    r = ctx.act(rid, "send-quote")
    assert r.status_code == 422
    assert r.json()["code"] == "EXCHANGE_RATE_REQUIRED"
    q = quote(ctx, rid, cimh=["L1"], rate="2.0", cimh_ship="10.00", prices=[{"lineId": "L2", "unitPrice": "25.00"}])
    assert q["cimhQuote"]["exchangeRate"] == "2.0"
    assert q["cimhQuote"]["lines"][0]["unitPrice"] == "50.00"  # 100 BBD / 2
    assert q["cimhQuote"]["shippingEstimate"] == "5.00"  # 10 BBD / 2
    assert q["adminFee"] == "10.00"
    assert q["agreement"]["total"] == "165.00"  # 100 CIMH + 5 shipping + 50 supplier + 0 shipping + 10 fee


@pytest.mark.req("O15")
def test_zero_exchange_rate_is_refused_not_a_500(ctx: Ctx) -> None:
    ctx.deps.fee = Decimal("20.00")
    rid = to_quoting(ctx, "USD")
    body = draft(prices=[{"lineId": "L1", "unitPrice": "60.00"}, {"lineId": "L2", "unitPrice": "25.00"}])
    body["cimh"] = {"lineIds": [], "exchangeRate": "0.000"}
    ctx.ok(rid, "quote-draft", body, method="PUT")
    r = ctx.act(rid, "send-quote")
    assert r.status_code == 422
    assert r.json()["code"] == "EXCHANGE_RATE_REQUIRED"


@pytest.mark.req("O15")
def test_usd_supplier_quote_and_its_shipping_are_converted_to_bbd(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    usd = {"supplier": "Vaisala", "currency": "USD", "fileIds": [], "shippingEstimate": "12.00", "lines": [
        {"lineId": "L1", "unitPrice": "10.25"}, {"lineId": "L2", "unitPrice": "3.33"}]}  # fmt: skip
    saved = ctx.ok(rid, "quote-draft", {"supplierQuotes": [usd]}, method="PUT")
    assert saved["quoteDraft"]["supplierQuotes"][0]["currency"] == "USD"
    assert saved["quoteDraft"]["supplierQuotes"][0]["shippingEstimate"] == "12.00"
    r = ctx.act(rid, "send-quote")
    assert r.status_code == 422
    assert r.json()["code"] == "EXCHANGE_RATE_REQUIRED"
    zero = ctx.act(rid, "quote-draft", {"supplierQuotes": [{**usd, "exchangeRate": "0"}]}, method="PUT")
    assert zero.json()["code"] == "EXCHANGE_RATE_REQUIRED"
    saved = ctx.ok(rid, "quote-draft", {"supplierQuotes": [{**usd, "exchangeRate": "2.0225"}]}, method="PUT")
    assert saved["quoteDraft"]["supplierQuotes"][0]["exchangeRate"] == "2.0225"
    q = ctx.ok(rid, "send-quote")
    (sq,) = q["quotes"]
    assert (sq["sourceCurrency"], sq["exchangeRate"]) == ("USD", "2.0225")
    # unit price rounded first (10.25 x 2.0225 = 20.730625 -> 20.73), then x qty 2
    assert sq["lines"][0] == {"lineId": "L1", "unitPrice": "20.73", "total": "41.46", "sourceUnitPrice": "10.25"}
    assert sq["lines"][1]["unitPrice"] == "6.73"  # 3.33 x 2.0225 = 6.734925
    assert sq["total"] == "54.92"
    assert (sq["shippingEstimate"], sq["sourceShippingEstimate"]) == ("24.27", "12.00")  # 12 x 2.0225 = 24.27
    assert q["agreement"]["total"] == "79.19"
    assert q["currency"] == "BBD"


@pytest.mark.req("O15")
def test_bbd_supplier_quote_is_not_converted(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    q = quote(ctx, rid, ship="18.50")
    assert q["quotes"][0]["sourceCurrency"] is None
    assert q["quotes"][0]["lines"][0]["sourceUnitPrice"] is None
    assert (q["quotes"][0]["shippingEstimate"], q["quotes"][0]["sourceShippingEstimate"]) == ("18.50", None)


def test_quote_must_cover_every_line(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    ctx.ok(rid, "quote-draft", draft(prices=[{"lineId": "L1", "unitPrice": "1.00"}]), method="PUT")
    r = ctx.act(rid, "send-quote")
    assert r.status_code == 422
    assert r.json()["code"] == "QUOTE_INCOMPLETE"


def test_every_source_needs_a_shipping_estimate(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    ctx.ok(rid, "quote-draft", draft(ship=None), method="PUT")
    r = ctx.act(rid, "send-quote")
    assert r.status_code == 422
    assert r.json()["code"] == "SHIPPING_ESTIMATE_REQUIRED"
    assert r.json()["errors"][0]["field"] == "supplierQuotes[0].shippingEstimate"
    ctx.ok(rid, "quote-draft", draft(cimh=["L1"], cimh_ship=None), method="PUT")
    r = ctx.act(rid, "send-quote")
    assert r.json()["code"] == "SHIPPING_ESTIMATE_REQUIRED"
    assert r.json()["errors"][0]["field"] == "cimh.shippingEstimate"
    assert ctx.get(rid)["status"] == "QUOTING"


def test_a_line_comes_from_one_place_only(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    r = ctx.act(rid, "quote-draft", {"supplierQuotes": [], "cimh": {"lineIds": ["L2"]}}, method="PUT")
    assert r.status_code == 422  # L2 is not fully in stock
    two = [{"supplier": s, "fileIds": [], "lines": [{"lineId": "L1", "unitPrice": "1.00"}]} for s in ("A", "B")]
    r = ctx.act(rid, "quote-draft", {"supplierQuotes": two}, method="PUT")
    assert r.json()["code"] == "LINE_SOURCE_CONFLICT"
    both = draft(cimh=["L1"], prices=[{"lineId": "L1", "unitPrice": "1.00"}, {"lineId": "L2", "unitPrice": "1.00"}])
    r = ctx.act(rid, "quote-draft", both, method="PUT")
    assert r.json()["code"] == "LINE_SOURCE_CONFLICT"
    one = [{"supplier": "A", "fileIds": [], "lines": [{"lineId": "L9", "unitPrice": "1.00"}]}]
    assert ctx.act(rid, "quote-draft", {"supplierQuotes": one}, method="PUT").status_code == 422
    bad = [{"supplier": "A", "fileIds": [], "lines": [{"lineId": "L1", "unitPrice": "1.5"}]}]
    assert ctx.act(rid, "quote-draft", {"supplierQuotes": bad}, method="PUT").status_code == 422
    # A draft saved before the rule (both places) is refused at send.
    one_bbd = Decimal128("1.00")
    priced = [{"lineId": "L1", "unitPrice": one_bbd}, {"lineId": "L2", "unitPrice": one_bbd}]
    sq = {"supplier": "A", "currency": "BBD", "fileIds": [], "shippingEstimate": one_bbd, "lines": priced}
    ctx.force(rid, quoteDraft={"supplierQuotes": [sq], "cimh": {"lineIds": ["L1"], "shippingEstimate": one_bbd}})
    r = ctx.act(rid, "send-quote")
    assert r.json()["code"] == "LINE_SOURCE_CONFLICT"


def test_a_cimh_line_needs_a_catalogue_cost(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    ctx.deps.catalog["MET1"]["cost"] = None
    ctx.ok(rid, "quote-draft", draft(cimh=["L1"]), method="PUT")
    r = ctx.act(rid, "send-quote")
    assert r.status_code == 422
    assert r.json()["code"] == "QUOTE_INCOMPLETE"
    assert "no catalogue cost" in r.json()["detail"]


def test_a_quote_sent_before_view_and_sign_cannot_be_accepted(ctx: Ctx) -> None:
    """A request quoted under the old flow has no agreement for its version: staff re-send it first."""
    rid = to_quoting(ctx)
    quote(ctx, rid)
    ctx.force(rid, agreement=None)
    signed = ctx.attach(rid, "signed_agreement", quote_version=1)
    r = ctx.act(rid, "accept", {"quoteVersion": 1, "signedAgreementFileId": signed}, USER)
    assert r.status_code == 409
    assert r.json()["code"] == "QUOTE_OUTDATED"


def test_pick_refuses_an_unknown_line_and_ignores_a_repeated_scan(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    quote(ctx, rid, cimh=["L1"])
    reserve(ctx, rid, "L1", ["MET1_aa", "MET1_bb"])
    sign(ctx, rid)
    ctx.ok(rid, "purchase-orders", {"agreementVerified": True, "purchaseOrders": [
        {"supplier": SUPPLIER, "poNumber": "PO-2", "lineIds": ["L2"]}]})  # fmt: skip

    def pick(line: str, unit: str) -> Any:
        h = {**STAFF, "Idempotency-Key": uuid.uuid4().hex}
        return ctx.client.post(ctx.url(f"/requests/{rid}/picks"), headers=h, json={"lineId": line, "unit": unit})

    assert pick("L9", "MET1_aa").status_code == 422
    assert pick("L1", "MET1_aa").status_code == 200
    again = pick("L1", "MET1_aa")  # the same unit scanned twice with a new key: nothing changes
    assert again.status_code == 200
    assert [x["barcode"] for x in again.json()["lines"][0]["picked"]] == ["MET1_aa"]


def test_stock_taken_since_quoting_started_is_refused(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    ctx.ok(rid, "quote-draft", draft(cimh=["L1"]), method="PUT")
    ctx.deps.stock["MET1"] = 1  # someone else took units meanwhile
    r = ctx.act(rid, "send-quote")
    assert r.status_code == 409
    assert r.json()["code"] == "CIMH_STOCK_SHORT"
    assert "Only 1 of 2" in r.json()["detail"]
    assert ctx.get(rid)["status"] == "QUOTING"


def test_revised_quote_voids_the_old_agreement(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    quote(ctx, rid, cimh=["L1"])
    reserve(ctx, rid, "L1", ["MET1_aa", "MET1_bb"])
    old_signed = ctx.attach(rid, "signed_agreement", quote_version=1)
    revised = quote(ctx, rid, cimh=["L1"], prices=[{"lineId": "L2", "unitPrice": "45.00"}], ship="5.00")
    assert revised["status"] == "QUOTED"
    assert [q["version"] for q in revised["quotes"]] == [1, 2]
    assert revised["agreement"] == {**revised["agreement"], "quoteVersion": 2, "total": "295.00", "fileId": None}
    # The line stayed CIMH: its reservation is kept (inventory sees the same need and changes nothing).
    assert ctx.get(rid)["lines"][0]["reservation"] == {"status": "RESERVED", "units": ["MET1_aa", "MET1_bb"]}
    (rev,) = ctx.events(rid, "order.quote_revised")
    assert (rev["payload"]["quoteVersion"], rev["payload"]["from"], rev["payload"]["to"]) == (2, "QUOTED", "QUOTED")
    assert rev["payload"]["total"] == "295.00"
    # A late PDF made for version 1 is kept as a file but never offered for signing.
    ctx.attach(rid, "agreement", "FILv1", quote_version=1)
    assert ctx.get(rid, USER)["agreement"]["fileId"] is None
    ctx.attach(rid, "agreement", "FILv2", quote_version=2)
    assert ctx.get(rid, USER)["agreement"]["fileId"] == "FILv2"

    r = ctx.act(rid, "accept", {"quoteVersion": 1, "signedAgreementFileId": old_signed}, USER)
    assert r.status_code == 409
    assert r.json()["code"] == "QUOTE_OUTDATED"
    r = ctx.act(rid, "accept", {"quoteVersion": 2, "signedAgreementFileId": old_signed}, USER)
    assert r.status_code == 409  # signed for version 1
    assert r.json()["code"] == "QUOTE_OUTDATED"
    assert sign(ctx, rid, 2)["status"] == "ACCEPTED"


def test_a_revision_that_drops_a_cimh_line_releases_it(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    quote(ctx, rid, cimh=["L1"])
    reserve(ctx, rid, "L1", ["MET1_aa", "MET1_bb"])
    revised = quote(ctx, rid)  # everything from the supplier now
    assert [ln["source"] for ln in revised["lines"]] == ["SUPPLIER", "SUPPLIER"]
    assert revised["lines"][0]["reservation"] is None
    (rev,) = ctx.events(rid, "order.quote_revised")
    assert rev["payload"]["cimhLineIds"] == []  # inventory releases what it held for the request


def test_expired_quote_cannot_be_accepted_and_the_job_cancels_it(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    quote(ctx, rid)
    ctx.force(rid, quoteExpiresAt=now() - timedelta(minutes=1))
    signed = ctx.attach(rid, "signed_agreement", quote_version=1)
    r = ctx.act(rid, "accept", {"quoteVersion": 1, "signedAgreementFileId": signed}, USER)
    assert r.status_code == 409
    assert r.json()["code"] == "QUOTE_EXPIRED"
    assert ctx.run(ctx.svc.expire_quotes()) == 1
    doc = ctx.get(rid, USER)
    assert doc["status"] == "CANCELLED"
    assert doc["cancellation"]["auto"] is True
    (evt,) = ctx.events(rid, "order.expired")
    assert evt["payload"]["from"] == "QUOTED"
    assert ctx.run(ctx.svc.expire_quotes()) == 0


def test_quote_reminder_once_per_expiry(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    quote(ctx, rid)
    assert ctx.run(ctx.svc.remind_quotes(3)) == 0  # 30 days left
    ctx.force(rid, quoteExpiresAt=now() + timedelta(days=2))
    assert ctx.run(ctx.svc.remind_quotes(3)) == 1
    assert ctx.run(ctx.svc.remind_quotes(3)) == 0  # once
    (evt,) = ctx.events(rid, "order.quote_expiring")
    assert evt["payload"]["quoteVersion"] == 1
    assert evt["payload"]["customer"] == "USRUSER"
    check_event(evt)
    ctx.force(rid, quoteExpiresAt=now() + timedelta(days=1))  # revised quote, new expiry: remind again
    assert ctx.run(ctx.svc.remind_quotes(3)) == 1


def test_staff_reject_the_signature(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    quote(ctx, rid, cimh=["L1"])
    reserve(ctx, rid, "L1", ["MET1_aa", "MET1_bb"])
    accepted = sign(ctx, rid)
    rejected_file = accepted["acceptance"]["signedAgreementFileId"]
    ctx.force(rid, quoteExpiresAt=now() + timedelta(days=1))
    back = ctx.ok(rid, "reject-agreement", {"reason": "Not signed by an authorised person"})
    assert back["status"] == "QUOTED"
    assert back["acceptance"] is None
    assert back["agreement"]["signedFileId"] is None
    assert back["agreement"]["rejections"][0]["reason"].startswith("Not")
    left = ctx.doc(rid)["quoteExpiresAt"]
    left = left if left.tzinfo else left.replace(tzinfo=now().tzinfo)
    assert left > now() + timedelta(days=6)  # at least 7 days to upload a correct copy
    # The quote stays live, so the stock stays held.
    assert ctx.get(rid)["lines"][0]["reservation"]["status"] == "RESERVED"
    assert ctx.events(rid, "order.agreement_rejected")
    assert set(ctx.get(rid, USER)["allowedActions"]) == {"accept", "decline"}
    # The rejected copy can't be sent again; a new one is accepted.
    r = ctx.act(rid, "accept", {"quoteVersion": 1, "signedAgreementFileId": rejected_file}, USER)
    assert r.status_code == 422
    assert r.json()["code"] == "AGREEMENT_REQUIRED"
    assert sign(ctx, rid)["status"] == "ACCEPTED"
    assert len(ctx.events(rid, "order.accepted")) == 2


def test_cancel_request_on_a_quote_closes_it(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    quote(ctx, rid)
    assert ctx.act(rid, "decline", {"reason": "Too expensive"}, PEER).status_code == 403  # same org: read only
    out = ctx.ok(rid, "decline", {"reason": "Too expensive"}, USER)
    assert out["status"] == "CANCELLED"
    assert out["decline"]["reason"] == "Too expensive"
    assert [h["to"] for h in out["history"]][-2:] == ["DECLINED", "CANCELLED"]
    assert ctx.events(rid, "order.declined")  # inventory releases the stock held for the quote


def test_cancel_rules(ctx: Ctx) -> None:
    rid = ctx.paid_request()
    out = ctx.ok(rid, "cancel", {"reason": "Ordered by mistake"}, USER)
    assert out["status"] == "CANCELLED"
    assert out["cancellation"]["auto"] is False
    (evt,) = ctx.events(rid, "order.cancelled")
    assert evt["payload"]["auto"] is False
    # After acceptance only staff/admin may cancel.
    rid = to_quoting(ctx)
    quote(ctx, rid)
    sign(ctx, rid)
    assert ctx.act(rid, "cancel", {"reason": "Changed my mind"}, USER).status_code == 403
    assert "cancel" not in ctx.get(rid, USER)["allowedActions"]
    assert ctx.ok(rid, "cancel", {"reason": "Budget withdrawn"}, ADMIN)["status"] == "CANCELLED"


def test_stale_version_is_a_conflict(ctx: Ctx) -> None:
    rid = ctx.paid_request()
    r = ctx.client.post(ctx.url(f"/requests/{rid}/start-quoting"), headers={**STAFF, "If-Match": "99"})
    assert r.status_code == 409
    assert r.json()["code"] == "VERSION_CONFLICT"
    r = ctx.client.post(ctx.url(f"/requests/{rid}/start-quoting"), headers=STAFF)
    assert r.status_code == 428


def test_reservation_failure_flags_the_line(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    quote(ctx, rid, cimh=["L1"])
    ctx.run(
        ctx.svc.stock_reservation_failed({"orderId": rid, "lines": [{"lineId": "L1", "requested": 2, "available": 1}]})
    )
    assert ctx.get(rid)["lines"][0]["reservation"]["status"] == "FAILED"
    reserve(ctx, rid, "L1", ["MET1_aa", "MET1_bb"])
    ctx.run(ctx.svc.stock_released({"orderId": rid, "units": ["MET1_aa", "MET1_bb"]}))
    assert ctx.get(rid)["lines"][0]["reservation"]["status"] == "RELEASED"


def test_dependency_outage_is_503(ctx: Ctx) -> None:
    rid = ctx.paid_request()
    ctx.deps.down = True
    r = ctx.act(rid, "start-quoting")
    assert r.status_code == 503
    assert ctx.get(rid)["status"] == "SUBMITTED"


def test_upgrade_moves_old_requests_to_view_and_sign(ctx: Ctx) -> None:
    """Requests written under "choose and sign": choices become sources, AWAITING_AGREEMENT becomes QUOTED."""
    old = to_quoting(ctx)
    quote(ctx, old, cimh=["L1"])
    raw = ctx.doc(old)
    lines = [
        {**{k: v for k, v in ln.items() if k not in ("source", "supplier")}, "choice": None} for ln in raw["lines"]
    ]
    agreement = {
        **raw["agreement"],
        "choices": [{"lineId": "L1", "choice": "CIMH"}, {"lineId": "L2", "choice": "SUPPLIER"}],
    }
    ctx.force(old, status="AWAITING_AGREEMENT", lines=lines, agreement=agreement)
    done = ctx.paid_request("MET1", qty=1)
    ctx.force(done, status="DELIVERED", lines=[{**ln, "choice": "SUPPLIER"} for ln in ctx.doc(done)["lines"]])

    out = ctx.run(upgrade.view_and_sign(ctx.db["orders"]))
    assert (out["linesRenamed"], out["movedToQuoted"]) == (2, 1)
    assert out["needResend"] == [old]  # its agreement still lists "your choices"
    after = ctx.get(old)
    assert after["status"] == "QUOTED"
    assert [ln["source"] for ln in after["lines"]] == ["CIMH", "SUPPLIER"]
    assert after["history"][-1]["reason"] == "Flow change: view and sign"
    assert "choice" not in ctx.doc(done)["lines"][0]
    assert ctx.get(done)["lines"][0]["source"] == "SUPPLIER"
    again = ctx.run(upgrade.view_and_sign(ctx.db["orders"]))
    assert (again["linesRenamed"], again["movedToQuoted"]) == (0, 0)


@pytest.mark.req("O5a")
def test_staff_preview_the_quote_before_sending_it(ctx: Ctx) -> None:
    """document-svc draws the agreement preview from this: the same figures Send quote fixes, nothing saved."""
    ctx.deps.fee = Decimal("25.00")
    rid = to_quoting(ctx)
    before = ctx.get(rid)
    url = ctx.url(f"/internal/requests/{rid}/quote-preview")
    ctx.ok(rid, "quote-draft", draft(cimh=["L1"], ship="30.00", cimh_ship="15.00"), method="PUT")
    after_draft = ctx.get(rid)
    r = ctx.client.get(url, headers=DOCUMENT)
    assert r.status_code == 200, r.text
    pv = r.json()
    assert pv["status"] == "QUOTED"  # as Send quote would leave it (the stored request stays QUOTING)
    assert pv["agreement"]["quoteVersion"] == 1
    assert pv["agreement"]["total"] == "370.00"  # 200 CIMH + 100 supplier + 30 + 15 shipping + 25 admin fee
    assert [(ln["source"], ln["supplier"]) for ln in pv["lines"]] == [("CIMH", None), ("SUPPLIER", SUPPLIER)]
    assert pv["quoteExpiresAt"]
    stored = ctx.get(rid)
    assert (stored["status"], stored["version"]) == ("QUOTING", after_draft["version"])  # the preview saved nothing
    assert after_draft["version"] > before["version"]
    assert ctx.events(rid, "order.quoted") == []
    assert ctx.client.get(url, headers=DOCUMENT).json()["agreement"]["total"] == "370.00"  # repeatable

    # The figures match what Send quote then fixes.
    sent = ctx.ok(rid, "send-quote")
    assert sent["agreement"]["total"] == pv["agreement"]["total"]
    assert sent["cimhQuote"]["lines"] == pv["cimhQuote"]["lines"]
    # A revision previews as the next version.
    assert ctx.client.get(url, headers=DOCUMENT).json()["agreement"]["quoteVersion"] == 2


def test_quote_preview_says_why_the_draft_cannot_be_sent(ctx: Ctx) -> None:
    rid = to_quoting(ctx)
    url = ctx.url(f"/internal/requests/{rid}/quote-preview")
    ctx.ok(rid, "quote-draft", draft(ship=None), method="PUT")
    r = ctx.client.get(url, headers=DOCUMENT)
    assert (r.status_code, r.json()["code"]) == (422, "SHIPPING_ESTIMATE_REQUIRED")
    assert ctx.client.get(ctx.url("/internal/requests/ORDnope/quote-preview"), headers=DOCUMENT).status_code == 404
    submitted = ctx.paid_request("MET1")
    r = ctx.client.get(ctx.url(f"/internal/requests/{submitted}/quote-preview"), headers=DOCUMENT)
    assert (r.status_code, r.json()["code"]) == (409, "ORDER_ILLEGAL_TRANSITION")
    assert ctx.client.get(url, headers=STAFF).status_code == 403  # internal: document-svc only
