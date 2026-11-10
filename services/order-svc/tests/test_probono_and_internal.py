"""Pro Bono flow (O12-O14), document-svc internal endpoints, the order consumer and the cart job."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest

from cimh_common.outbox import EventEnvelope
from order_svc.consumer import make_handler
from order_svc.store import now

from .conftest import DOCUMENT, OTHER, PEER, STAFF, USER, Ctx, token


def probono(ctx: Ctx, qty: int = 2) -> str:
    ctx.cart_add("PRO1", qty)
    (req,) = ctx.submit(currency=None)
    return str(req["id"])


@pytest.mark.req("O12")
def test_probono_journey(ctx: Ctx) -> None:
    rid = probono(ctx)
    assert set(ctx.get(rid)["allowedActions"]) == {"approve", "reject", "cancel"}
    out = ctx.ok(rid, "approve")
    assert out["status"] == "APPROVED"
    assert out["approval"]["by"]["id"] == "USRSTAFF"
    (evt,) = ctx.events(rid, "order.probono_approved")
    assert evt["payload"]["lines"] == [{"lineId": "L1", "productId": "PRO1", "qty": 2, "choice": None}]
    assert "cancel" not in ctx.get(rid, USER)["allowedActions"]  # after approval only staff cancel

    ctx.run(ctx.svc.stock_reserved({"orderId": rid, "lines": [{"lineId": "L1", "units": ["PRO1_a", "PRO1_b"]}]}))
    ctx.deps.reserved[rid] = {"PRO1_a", "PRO1_b"}

    def pick(unit: str) -> Any:
        h = {**STAFF, "Idempotency-Key": uuid.uuid4().hex}
        return ctx.client.post(ctx.url(f"/requests/{rid}/picks"), headers=h, json={"lineId": "L1", "unit": unit})

    first = pick("PRO1_a")
    assert first.status_code == 200
    assert first.json()["status"] == "PICKING"
    assert [h["to"] for h in first.json()["history"]][-1] == "PICKING"
    assert pick("PRO1_b").json()["lines"][0]["picked"][1]["barcode"] == "PRO1_b"
    r = pick("PRO1_c")
    assert r.status_code == 409
    assert r.json()["code"] == "LINE_FULLY_PICKED"
    shipped = ctx.ok(
        rid, "ship", {"carrier": "FEDEX", "tracking": "7712", "date": "2026-11-10", "notifyCustomer": False}
    )
    assert shipped["shipping"]["trackingUrl"].endswith("7712")
    assert ctx.ok(rid, "deliver")["status"] == "DELIVERED"
    ctx.events(rid)


def test_probono_reject_needs_a_reason(ctx: Ctx) -> None:
    rid = probono(ctx)
    assert ctx.act(rid, "reject", {"reason": ""}).status_code == 422
    out = ctx.ok(rid, "reject", {"reason": "Not for research use"})
    assert out["status"] == "REJECTED"
    assert out["rejection"]["reason"] == "Not for research use"
    assert ctx.events(rid, "order.probono_rejected")


def test_customers_cannot_take_staff_actions(ctx: Ctx) -> None:
    rid = probono(ctx)
    assert ctx.act(rid, "approve", None, USER).status_code == 403


# ---------------------------------------------------------------- internal endpoints (document-svc)


def test_file_access_answers(ctx: Ctx) -> None:
    rid = probono(ctx)

    def allowed(user: str) -> bool:
        r = ctx.client.get(ctx.url(f"/internal/requests/{rid}/access"), headers=DOCUMENT, params={"user": user})
        assert r.status_code == 200
        return bool(r.json()["allowed"])

    assert allowed("USRUSER")
    assert allowed("USRPEER")
    assert allowed("USRSTAFF")
    assert not allowed("USROTHER")
    assert not allowed("USRNOBODY")
    r = ctx.client.get(ctx.url(f"/internal/requests/{rid}/access"), headers=token("service", "svc:catalog", ""),
                       params={"user": "USRUSER"})  # fmt: skip
    assert r.status_code == 403  # only document-svc


def test_access_tells_who_may_act_and_the_state(ctx: Ctx) -> None:
    rid = probono(ctx)

    def ask(user: str) -> dict[str, Any]:
        r = ctx.client.get(ctx.url(f"/internal/requests/{rid}/access"), headers=DOCUMENT, params={"user": user})
        assert r.status_code == 200
        return dict(r.json())

    assert ask("USRUSER") == {"allowed": True, "canAct": True, "status": "SUBMITTED", "type": "PROBONO"}
    assert ask("USRPEER")["canAct"] is False
    assert ask("USRSTAFF")["canAct"] is False
    assert ask("USRSTAFF")["allowed"] is True
    r = ctx.client.get(ctx.url("/internal/requests/ORDnope/access"), headers=DOCUMENT, params={"user": "USRUSER"})
    assert r.status_code == 404


def test_internal_staff_view_for_pdfs(ctx: Ctx) -> None:
    rid = probono(ctx)
    r = ctx.client.get(ctx.url(f"/internal/requests/{rid}"), headers=DOCUMENT)
    assert r.status_code == 200
    assert r.json()["id"] == rid
    assert r.json()["shipTo"]["country"] == "BB"
    assert ctx.client.get(ctx.url(f"/internal/requests/{rid}"), headers=STAFF).status_code == 403
    assert ctx.client.get(ctx.url("/internal/requests/ORDnope"), headers=DOCUMENT).status_code == 404


def test_files_attach_once_and_show_download_paths(ctx: Ctx) -> None:
    rid = probono(ctx)
    fid = ctx.attach(rid, "upload", "FILabc")
    ctx.attach(rid, "upload", "FILabc")
    files = ctx.get(rid, PEER)["files"]
    assert [f["id"] for f in files] == [fid]
    assert files[0]["url"] == f"/api/documents/v1/files/{fid}"
    assert ctx.client.get(ctx.url(f"/requests/{rid}"), headers=OTHER).status_code == 404


# ---------------------------------------------------------------- consumer


def envelope(etype: str, payload: dict[str, Any]) -> EventEnvelope:
    return EventEnvelope(type=etype, correlationId="c", payload=payload)


def test_consumer_routes_stock_and_document_events(ctx: Ctx) -> None:
    rid = probono(ctx)
    ctx.ok(rid, "approve")
    handle = make_handler(ctx.svc)
    ctx.run(handle(envelope("stock.reserved", {"orderId": rid, "lines": [{"lineId": "L1", "units": ["PRO1_a"]}]})))
    assert ctx.get(rid)["lines"][0]["reservation"]["status"] == "RESERVED"
    ctx.run(handle(envelope("stock.released", {"orderId": rid, "units": ["PRO1_a"]})))
    assert ctx.get(rid)["lines"][0]["reservation"]["status"] == "RELEASED"
    doc = {"orderId": rid, "fileId": "FILpdf", "kind": "probono_invoice", "name": "inv.pdf", "mime": "application/pdf",
           "size": 99, "sha256": "0" * 64}  # fmt: skip
    ctx.run(handle(envelope("document.generated", doc)))
    ctx.run(handle(envelope("document.generated", doc)))  # redelivery
    assert [f["id"] for f in ctx.get(rid)["files"]] == ["FILpdf"]
    ctx.run(handle(envelope("document.deleted", {"orderId": rid, "fileId": "FILpdf", "reason": "wrong"})))
    ctx.run(handle(envelope("document.deleted", {"orderId": rid, "fileId": "FILpdf", "reason": "wrong"})))
    assert ctx.get(rid)["files"] == []
    with pytest.raises(ValueError, match="lacks orderId"):
        ctx.run(handle(envelope("document.deleted", {"fileId": "FILpdf"})))
    ctx.run(handle(envelope("stock.changed", {"productId": "PRO1"})))  # ignored
    ctx.run(handle(envelope("stock.reserved", {"orderId": "ORDmissing", "lines": []})))  # unknown order: no-op
    with pytest.raises(ValueError, match="lacks orderId"):
        ctx.run(handle(envelope("stock.reserved", {"lines": []})))  # -> DLQ


def test_agreement_pdf_before_and_after_the_agreement(ctx: Ctx) -> None:
    rid = probono(ctx)
    ctx.attach(rid, "agreement", "FILearly")  # no agreement yet: the file is kept, nothing points at it
    assert [f["id"] for f in ctx.get(rid)["files"]] == ["FILearly"]


# ---------------------------------------------------------------- jobs


def test_old_carts_are_emptied(ctx: Ctx) -> None:
    ctx.cart_add("MET1")
    ctx.cart_add("MET1", who=PEER)
    ctx.run(ctx.db["orders"].update_one({"cartOf": "USRUSER"}, {"$set": {"updatedAt": now() - timedelta(days=181)}}))
    assert ctx.run(ctx.svc.purge_carts()) == 1
    assert ctx.client.get(ctx.url("/cart"), headers=USER).json()["lines"] == []
    assert ctx.client.get(ctx.url("/cart"), headers=PEER).json()["lines"]


def _raw(ctx: Ctx, rid: str) -> dict[str, Any]:
    doc: dict[str, Any] = ctx.run(ctx.db["orders"].find_one({"id": rid}))
    return doc


@pytest.mark.req("TR-PRIV-1")
def test_user_deleted_cancels_open_requests_and_forgets_the_person(ctx: Ctx) -> None:
    """BSD §8 right to erasure: open requests cancelled, personal data "[deleted]", financial fields kept."""
    pro = probono(ctx)
    ctx.ok(pro, "approve")  # staff acted: USRSTAFF in history
    paid = ctx.paid_request("MET1", qty=1)
    ctx.cart_add("MET2")  # a cart with lines
    handle = make_handler(ctx.svc)
    ctx.run(handle(envelope("user.deleted", {"userId": "USRUSER"})))

    for rid in (pro, paid):
        doc = _raw(ctx, rid)
        assert doc["status"] == "CANCELLED"
        assert doc["cancellation"]["auto"] is True
        assert doc["history"][-1]["reason"] == "Account deleted"
        assert doc["customerSnapshot"] == {"firstname": "[deleted]", "lastname": "[deleted]", "email": "[deleted]"}
        assert doc["shipTo"]["line1"] == "[deleted]"
        assert doc["shipTo"]["country"] == "BB"  # kept for customs
        assert doc["lines"]  # the request itself stays (financial record)
        cancelled = [e for e in doc["outbox"] if e["type"] == "order.cancelled"]
        assert cancelled[-1]["payload"] == {
            "orderId": rid,
            "customer": "USRUSER",
            "reason": "Account deleted",
            "auto": True,
        }
    assert "Una" not in str(_raw(ctx, paid))
    assert "u@met.bb" not in str(_raw(ctx, paid))
    assert ctx.run(ctx.db["orders"].count_documents({"customer": "USRUSER", "status": "CART"})) == 0

    before = _raw(ctx, pro)["version"]
    ctx.run(handle(envelope("user.deleted", {"userId": "USRUSER"})))  # redelivery changes nothing
    assert _raw(ctx, pro)["version"] == before


def test_user_deleted_staff_name_removed_where_they_acted(ctx: Ctx) -> None:
    rid = probono(ctx)
    ctx.ok(rid, "approve")
    approver = [h["by"] for h in _raw(ctx, rid)["history"] if h["by"]["id"] == "USRSTAFF"]
    assert approver
    assert approver[0]["name"] != "[deleted]"
    ctx.run(make_handler(ctx.svc)(envelope("user.deleted", {"userId": "USRSTAFF"})))
    doc = _raw(ctx, rid)
    assert all(h["by"]["name"] == "[deleted]" for h in doc["history"] if h["by"]["id"] == "USRSTAFF")
    assert doc["status"] == "APPROVED"  # someone else's request: not cancelled
    assert doc["customerSnapshot"]["firstname"] != "[deleted]"


def test_user_deleted_leaves_requests_past_the_point_of_no_return(ctx: Ctx) -> None:
    rid = probono(ctx)
    ctx.ok(rid, "approve")
    ctx.run(ctx.db["orders"].update_one({"id": rid}, {"$set": {"status": "SHIPPED"}}))
    ctx.run(make_handler(ctx.svc)(envelope("user.deleted", {"userId": "USRUSER"})))
    doc = _raw(ctx, rid)
    assert doc["status"] == "SHIPPED"  # goods are on their way: staff finish it
    assert doc["customerSnapshot"]["email"] == "[deleted]"
