"""Paid requests: quoting (O5, O5a, O7, O15), agreement + signed acceptance (O6, O6a), purchasing, picking,
shipping, delivery (O8-O11). TAD §7.2; the reservation round trip with inventory is driven by its events."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from order_svc.store import now

from .conftest import ADMIN, PEER, STAFF, USER, Ctx


def quote(
    ctx: Ctx, rid: str, *, cimh: list[str] | None = None, rate: str | None = None, prices: Any = None
) -> dict[str, Any]:
    lines = prices or [{"lineId": "L1", "unitPrice": "120.00"}, {"lineId": "L2", "unitPrice": "50.00"}]
    body: dict[str, Any] = {
        "supplierQuotes": [{"supplier": "Campbell Scientific", "lines": lines, "fileIds": ["FILq1"]}]
    }
    if cimh is not None or rate:
        body["cimh"] = {"lineIds": cimh or [], "exchangeRate": rate}
    ctx.ok(rid, "quote-draft", body, method="PUT")
    return ctx.ok(rid, "send-quote")


def reserve(ctx: Ctx, rid: str, line: str, units: list[str]) -> None:
    """What inventory does on order.accepted, reported back through stock.reserved."""
    ctx.run(ctx.svc.stock_reserved({"orderId": rid, "lines": [{"lineId": line, "units": units}]}))
    ctx.deps.reserved.setdefault(rid, set()).update(units)


def to_quoted(ctx: Ctx, currency: str = "BBD") -> str:
    ctx.deps.stock = {"MET1": 5, "MET2": 0}
    rid = ctx.paid_request("MET1", "MET2", currency=currency)
    started = ctx.ok(rid, "start-quoting")
    assert [ln["cimhAvailable"] for ln in started["lines"]] == [True, False]
    return rid


@pytest.mark.req("O5a")
def test_paid_journey_with_cimh_and_supplier_lines(ctx: Ctx) -> None:
    ctx.deps.fee = Decimal("25.00")
    rid = to_quoted(ctx)
    q = quote(ctx, rid, cimh=["L1"])
    assert q["status"] == "QUOTED"
    assert q["quoteExpiresAt"]
    assert q["quotes"][0]["total"] == "340.00"
    assert q["quotes"][0]["supplier"] == "Campbell Scientific"
    assert q["cimhQuote"]["lines"] == [
        {"lineId": "L1", "unitPrice": "100.00", "total": "200.00", "unitCostBBD": "100.00"}
    ]
    assert q["adminFee"] == "25.00"
    (quoted,) = ctx.events(rid, "order.quoted")
    assert quoted["payload"]["cimhLineIds"] == ["L1"]
    assert quoted["payload"]["quoteVersion"] == 1

    # The customer sees the quote without supplier names or costs.
    mine = ctx.get(rid, USER)
    assert "supplier" not in mine["quotes"][0]
    assert "unitCostBBD" not in mine["cimhQuote"]["lines"][0]
    assert "purchaseOrders" not in mine
    assert "quoteDraft" not in mine
    assert set(mine["allowedActions"]) == {"agreement", "decline"}

    # L1 is offered both ways, so the customer must choose.
    r = ctx.act(rid, "agreement", {"quoteVersion": 1, "choices": []}, USER)
    assert r.status_code == 422
    assert r.json()["code"] == "CHOICE_REQUIRED"
    ag = ctx.ok(rid, "agreement", {"quoteVersion": 1, "choices": [{"lineId": "L1", "choice": "CIMH"}]}, USER)
    assert ag["status"] == "AWAITING_AGREEMENT"
    assert ag["agreement"]["total"] == "325.00"  # 200 CIMH + 100 supplier (L2) + 25 admin fee
    assert [c["choice"] for c in ag["agreement"]["choices"]] == ["CIMH", "SUPPLIER"]
    (req_evt,) = ctx.events(rid, "order.agreement_requested")
    assert req_evt["payload"]["total"] == "325.00"

    # document-svc renders the agreement; the customer signs and uploads it.
    agreement_pdf = ctx.attach(rid, "agreement")
    assert ctx.get(rid, USER)["agreement"]["fileId"] == agreement_pdf
    r = ctx.act(rid, "accept", {"quoteVersion": 1, "signedAgreementFileId": agreement_pdf}, USER)
    assert r.status_code == 422
    assert r.json()["code"] == "AGREEMENT_REQUIRED"
    signed = ctx.attach(rid, "signed_agreement")
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
    assert ctx.doc(rid)["acceptance"]["ip"] == "203.0.113.7"
    (accepted,) = ctx.events(rid, "order.accepted")
    assert [(x["lineId"], x["choice"]) for x in accepted["payload"]["lines"]] == [("L1", "CIMH"), ("L2", "SUPPLIER")]
    assert acc["lines"][0]["reservation"] == {"status": "NONE"}
    assert acc["lines"][1]["reservation"] is None

    reserve(ctx, rid, "L1", ["MET1_aa", "MET1_bb"])
    assert ctx.get(rid)["lines"][0]["reservation"] == {"status": "RESERVED", "units": ["MET1_aa", "MET1_bb"]}
    assert ctx.get(rid, USER)["lines"][0]["reservation"] == {"status": "RESERVED"}  # units are staff-only

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
    assert [h["to"] for h in done["history"]] == ["SUBMITTED", "QUOTING", "QUOTED", "AWAITING_AGREEMENT", "ACCEPTED",
                                                  "PURCHASING", "SHIPPED", "DELIVERED"]  # fmt: skip
    ctx.events(rid)  # every event matches its schema


def test_supplier_only_request_ships_without_picking(ctx: Ctx) -> None:
    rid = to_quoted(ctx)
    quote(ctx, rid)
    ctx.ok(rid, "agreement", {"quoteVersion": 1, "choices": []}, USER)  # one option per line: defaults
    signed = ctx.attach(rid, "signed_agreement")
    ctx.ok(rid, "accept", {"quoteVersion": 1, "signedAgreementFileId": signed}, USER)
    ctx.ok(rid, "purchase-orders", {"agreementVerified": True, "purchaseOrders": [
        {"supplier": "Campbell", "poNumber": "PO-9", "lineIds": ["L1", "L2"]}]})  # fmt: skip
    assert "pick" not in ctx.get(rid)["allowedActions"]
    assert (
        ctx.ok(rid, "ship", {"carrier": "HAND", "note": "Collected by Una", "date": "2026-11-09"})["status"]
        == "SHIPPED"
    )


@pytest.mark.req("O15")
def test_usd_needs_an_exchange_rate_for_cimh_lines_and_the_fee(ctx: Ctx) -> None:
    ctx.deps.fee = Decimal("20.00")
    rid = to_quoted(ctx, "USD")
    ctx.ok(rid, "quote-draft", {"supplierQuotes": [{"supplier": "S", "fileIds": [], "lines": [
        {"lineId": "L1", "unitPrice": "60.00"}, {"lineId": "L2", "unitPrice": "25.00"}]}]}, method="PUT")  # fmt: skip
    r = ctx.act(rid, "send-quote")
    assert r.status_code == 422
    assert r.json()["code"] == "EXCHANGE_RATE_REQUIRED"
    q = quote(ctx, rid, cimh=["L1"], rate="2.0", prices=[{"lineId": "L1", "unitPrice": "60.00"},
                                                         {"lineId": "L2", "unitPrice": "25.00"}])  # fmt: skip
    assert q["cimhQuote"]["exchangeRate"] == "2.0"
    assert q["cimhQuote"]["lines"][0]["unitPrice"] == "50.00"  # 100 BBD / 2
    assert q["adminFee"] == "10.00"


def test_quote_must_cover_every_line(ctx: Ctx) -> None:
    rid = to_quoted(ctx)
    only_l1 = [{"supplier": "S", "fileIds": [], "lines": [{"lineId": "L1", "unitPrice": "1.00"}]}]
    ctx.ok(rid, "quote-draft", {"supplierQuotes": only_l1}, method="PUT")
    r = ctx.act(rid, "send-quote")
    assert r.status_code == 422
    assert r.json()["code"] == "QUOTE_INCOMPLETE"


def test_draft_validation(ctx: Ctx) -> None:
    rid = to_quoted(ctx)
    r = ctx.act(rid, "quote-draft", {"supplierQuotes": [], "cimh": {"lineIds": ["L2"]}}, method="PUT")
    assert r.status_code == 422  # L2 is not fully in stock
    two = [{"supplier": s, "fileIds": [], "lines": [{"lineId": "L1", "unitPrice": "1.00"}]} for s in ("A", "B")]
    assert ctx.act(rid, "quote-draft", {"supplierQuotes": two}, method="PUT").status_code == 422
    one = [{"supplier": "A", "fileIds": [], "lines": [{"lineId": "L9", "unitPrice": "1.00"}]}]
    assert ctx.act(rid, "quote-draft", {"supplierQuotes": one}, method="PUT").status_code == 422
    bad = [{"supplier": "A", "fileIds": [], "lines": [{"lineId": "L1", "unitPrice": "1.5"}]}]
    assert ctx.act(rid, "quote-draft", {"supplierQuotes": bad}, method="PUT").status_code == 422


def test_revised_quote_outdates_the_old_version(ctx: Ctx) -> None:
    rid = to_quoted(ctx)
    quote(ctx, rid)
    revised = quote(ctx, rid, prices=[{"lineId": "L1", "unitPrice": "110.00"}, {"lineId": "L2", "unitPrice": "50.00"}])
    assert revised["status"] == "QUOTED"
    assert [q["version"] for q in revised["quotes"]] == [1, 2]
    assert ctx.events(rid, "order.quote_revised")
    r = ctx.act(rid, "agreement", {"quoteVersion": 1, "choices": []}, USER)
    assert r.status_code == 409
    assert r.json()["code"] == "QUOTE_OUTDATED"
    assert ctx.ok(rid, "agreement", {"quoteVersion": 2, "choices": []}, USER)["agreement"]["total"] == "320.00"


def test_choices_can_change_while_awaiting_agreement(ctx: Ctx) -> None:
    rid = to_quoted(ctx)
    quote(ctx, rid, cimh=["L1"])
    ctx.ok(rid, "agreement", {"quoteVersion": 1, "choices": [{"lineId": "L1", "choice": "CIMH"}]}, USER)
    ctx.attach(rid, "agreement")
    again = ctx.ok(rid, "agreement", {"quoteVersion": 1, "choices": [{"lineId": "L1", "choice": "SUPPLIER"}]}, USER)
    assert again["status"] == "AWAITING_AGREEMENT"
    assert again["agreement"]["fileId"] is None
    assert again["agreement"]["total"] == "340.00"
    r = ctx.act(rid, "agreement", {"quoteVersion": 1, "choices": [{"lineId": "L2", "choice": "CIMH"}]}, USER)
    assert r.status_code == 422  # not offered


def test_expired_quote_cannot_be_accepted_and_the_job_cancels_it(ctx: Ctx) -> None:
    rid = to_quoted(ctx)
    quote(ctx, rid)
    ctx.force(rid, quoteExpiresAt=now() - timedelta(minutes=1))
    r = ctx.act(rid, "agreement", {"quoteVersion": 1, "choices": []}, USER)
    assert r.status_code == 409
    assert r.json()["code"] == "QUOTE_EXPIRED"
    assert ctx.run(ctx.svc.expire_quotes()) == 1
    doc = ctx.get(rid, USER)
    assert doc["status"] == "CANCELLED"
    assert doc["cancellation"]["auto"] is True
    (evt,) = ctx.events(rid, "order.expired")
    assert evt["payload"]["from"] == "QUOTED"
    assert ctx.run(ctx.svc.expire_quotes()) == 0


def test_staff_reject_the_signature(ctx: Ctx) -> None:
    rid = to_quoted(ctx)
    quote(ctx, rid, cimh=["L1"])
    ctx.ok(rid, "agreement", {"quoteVersion": 1, "choices": [{"lineId": "L1", "choice": "CIMH"}]}, USER)
    ctx.ok(rid, "accept", {"quoteVersion": 1, "signedAgreementFileId": ctx.attach(rid, "signed_agreement")}, USER)
    reserve(ctx, rid, "L1", ["MET1_aa", "MET1_bb"])
    back = ctx.ok(rid, "reject-agreement", {"reason": "Not signed by an authorised person"})
    assert back["status"] == "AWAITING_AGREEMENT"
    assert back["acceptance"] is None
    assert back["agreement"]["signedFileId"] is None
    assert back["agreement"]["rejections"][0]["reason"].startswith("Not")
    assert ctx.events(rid, "order.agreement_rejected")  # inventory releases the units on this event
    # The customer uploads a correct copy and accepts again.
    again = ctx.ok(
        rid, "accept", {"quoteVersion": 1, "signedAgreementFileId": ctx.attach(rid, "signed_agreement")}, USER
    )
    assert again["status"] == "ACCEPTED"
    assert len(ctx.events(rid, "order.accepted")) == 2


def test_decline_closes_the_request(ctx: Ctx) -> None:
    rid = to_quoted(ctx)
    quote(ctx, rid)
    assert ctx.act(rid, "decline", {"reason": "Too expensive"}, PEER).status_code == 403  # same org: read only
    out = ctx.ok(rid, "decline", {"reason": "Too expensive"}, USER)
    assert out["status"] == "CANCELLED"
    assert out["decline"]["reason"] == "Too expensive"
    assert [h["to"] for h in out["history"]][-2:] == ["DECLINED", "CANCELLED"]
    assert ctx.events(rid, "order.declined")


def test_cancel_rules(ctx: Ctx) -> None:
    rid = ctx.paid_request()
    out = ctx.ok(rid, "cancel", {"reason": "Ordered by mistake"}, USER)
    assert out["status"] == "CANCELLED"
    assert out["cancellation"]["auto"] is False
    (evt,) = ctx.events(rid, "order.cancelled")
    assert evt["payload"]["auto"] is False
    # After acceptance only staff/admin may cancel.
    rid = to_quoted(ctx)
    quote(ctx, rid)
    ctx.ok(rid, "agreement", {"quoteVersion": 1, "choices": []}, USER)
    ctx.ok(rid, "accept", {"quoteVersion": 1, "signedAgreementFileId": ctx.attach(rid, "signed_agreement")}, USER)
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
    rid = to_quoted(ctx)
    quote(ctx, rid, cimh=["L1"])
    ctx.ok(rid, "agreement", {"quoteVersion": 1, "choices": [{"lineId": "L1", "choice": "CIMH"}]}, USER)
    ctx.ok(rid, "accept", {"quoteVersion": 1, "signedAgreementFileId": ctx.attach(rid, "signed_agreement")}, USER)
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
