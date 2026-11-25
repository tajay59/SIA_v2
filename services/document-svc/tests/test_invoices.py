"""Staff-built invoices and commercial invoices (SIA invoice builder): draft, preview, create."""

from __future__ import annotations

from typing import Any

import pytest

from document_svc import pdfs

from .conftest import ADMIN, INVENTORY, STAFF, USER, Ctx, check_event, request_doc


def _body(kind: str = "invoice", **kw: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        "number": "0190125",
        "date": "2026-11-20",
        "lines": [{"lineId": "L1", "description": "00000 - Register", "qty": 2, "unitPrice": "255.56"}],
        "fees": "0.00",
        "discount": "0.00",
        "shipping": "451.64",
        **kw,
    }


@pytest.mark.req("D3")
def test_draft_invoice_has_every_priced_line_fee_and_parcel_costs(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc(
        "ORD1", "SHIPPED", shipments=[{"id": "S1", "cost": "40.00"}, {"id": "S2", "cost": None}]
    )
    r = ctx.client.get(ctx.url("/requests/ORD1/invoice-draft?kind=invoice"), headers=STAFF)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [(x["lineId"], x["description"], x["qty"], x["unitPrice"]) for x in d["lines"]] == [
        ("L1", "Rain gauge", 2, "150.00"),
        ("L2", "Anemometer", 1, "180.00"),
    ]
    assert (d["fees"], d["shipping"], d["discount"]) == ("25.00", "40.00", "0.00")
    assert d["recipient"][0] == "Una User"


def test_draft_commercial_invoice_keeps_cimh_stock_lines_only(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "SHIPPED")
    d = ctx.client.get(ctx.url("/requests/ORD1/invoice-draft?kind=commercial_invoice"), headers=ADMIN).json()
    assert [x["lineId"] for x in d["lines"]] == ["L1"]
    assert (d["fees"], d["shipping"]) == ("0.00", "0.00")


def test_description_uses_the_model_number_like_legacy() -> None:
    assert pdfs.line_description({"product": {"name": "Still Well", "modelnumber": "246"}}) == "246 - Still Well"


def test_preview_is_a_pdf_and_stores_nothing(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "SHIPPED")
    for kind in ("invoice", "commercial_invoice"):
        r = ctx.client.post(ctx.url("/requests/ORD1/invoice-preview"), json=_body(kind), headers=STAFF)
        assert r.status_code == 200, r.text
        assert r.content.startswith(b"%PDF")
    assert ctx.publisher.sent == []
    assert ctx.orders.attached == []
    assert not [f for f in ctx.root.rglob("*") if f.is_file()]


def test_create_stores_attaches_and_says_who_to_email(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "DELIVERED")
    body = _body("commercial_invoice", number="0080926", emailCustomer=True, emailStaff=False)
    r = ctx.client.post(ctx.url("/requests/ORD1/invoices"), json=body, headers=STAFF)
    assert r.status_code == 201, r.text
    f = r.json()
    assert (f["kind"], f["name"]) == ("commercial_invoice", "Commercial-invoice-0080926.pdf")
    assert [rid for rid, _ in ctx.orders.attached] == ["ORD1"]
    gen = [e for _, _, e in ctx.publisher.sent if e.type == "document.generated"]
    assert len(gen) == 1
    check_event(gen[0])
    assert gen[0].payload["notify"] == {"customer": True, "staff": False}
    assert gen[0].payload["customer"] == "USRUSER"
    assert gen[0].payload["number"] == "0080926"
    assert any(e.type == "audit.recorded" for _, _, e in ctx.publisher.sent)
    got = ctx.client.get(ctx.url(f"/files/{f['id']}"), headers=STAFF)
    assert got.status_code == 200


def test_only_staff_and_bodies_are_strict(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "SHIPPED")
    url = ctx.url("/requests/ORD1/invoices")
    assert ctx.client.post(url, json=_body()).status_code == 401
    assert ctx.client.post(url, json=_body(), headers=USER).status_code == 403
    assert ctx.client.post(url, json=_body(), headers=INVENTORY).status_code == 403
    assert ctx.client.post(ctx.url("/requests/ORDnope/invoices"), json=_body(), headers=STAFF).status_code == 404
    assert ctx.client.post(url, json=_body(lines=[]), headers=STAFF).status_code == 422
    assert ctx.client.post(url, json=_body(shipping="12.345"), headers=STAFF).status_code == 422
    assert ctx.client.post(url, json=_body(date="2026-02-30"), headers=STAFF).status_code == 422
    assert ctx.client.post(url, json=_body(extra=1), headers=STAFF).status_code == 422


# ---------------------------------------------------------------- open, change, void (plan 2026-11-24-invoice-crud)


def _pdfs(ctx: Ctx) -> list[str]:
    return sorted(f.name for f in (ctx.root / "protected" / "orders" / "ORD1").glob("*.pdf"))


def test_create_then_open_change_and_void(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "DELIVERED")
    url = ctx.url("/requests/ORD1/invoices/invoice")
    assert ctx.client.get(url, headers=STAFF).status_code == 404  # none yet: the builder starts a new one
    first = ctx.client.post(ctx.url("/requests/ORD1/invoices"), json=_body(), headers=STAFF).json()
    assert first["invoice"]["rev"] == 1
    got = ctx.client.get(url, headers=STAFF)
    assert got.status_code == 200
    assert got.headers["ETag"] == '"1"'
    assert got.json()["lines"][0]["description"] == "00000 - Register"
    assert got.json()["recipient"][0] == "Una User"

    # A second create is refused and leaves no file behind.
    again = ctx.client.post(ctx.url("/requests/ORD1/invoices"), json=_body(number="0190126"), headers=STAFF)
    assert again.status_code == 409
    assert again.json()["code"] == "INVOICE_EXISTS"
    assert len(_pdfs(ctx)) == 1

    # Change it: If-Match is the revision; a new PDF, the old one becomes staff-only.
    assert ctx.client.put(url, json=_body(discount="10.00"), headers=STAFF).status_code == 428
    stale = ctx.client.put(url, json=_body(), headers={**STAFF, "If-Match": "5"})
    assert stale.status_code == 409
    r = ctx.client.put(url, json=_body(discount="10.00", emailCustomer=True), headers={**STAFF, "If-Match": '"1"'})
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["rev"] == 2
    assert second["name"] == "Invoice-0190125-rev2.pdf"
    assert len(_pdfs(ctx)) == 2
    gen = [e for _, _, e in ctx.publisher.sent if e.type == "document.generated"][-1]
    check_event(gen)
    assert gen.payload["rev"] == 2
    assert gen.payload["notify"] == {"customer": True, "staff": False}
    assert ctx.client.get(ctx.url(f"/files/{first['id']}"), headers=USER).status_code == 404  # replaced
    assert ctx.client.get(ctx.url(f"/files/{first['id']}"), headers=STAFF).status_code == 200
    assert ctx.client.get(ctx.url(f"/files/{second['id']}"), headers=USER).status_code == 200
    wrong_kind = ctx.client.put(url, json=_body("commercial_invoice"), headers={**STAFF, "If-Match": "2"})
    assert wrong_kind.status_code == 422

    # Void it: a reason, the revision; the customer loses the PDF, staff keep it; audited, nobody emailed.
    sent = len(ctx.publisher.sent)
    assert (
        ctx.client.request("DELETE", url, json={"reason": "No"}, headers={**STAFF, "If-Match": "2"}).status_code == 422
    )
    r = ctx.client.request("DELETE", url, json={"reason": "Wrong prices"}, headers={**STAFF, "If-Match": "2"})
    assert r.status_code == 204, r.text
    assert [e.type for _, _, e in ctx.publisher.sent[sent:]] == ["audit.recorded"]
    assert ctx.client.get(ctx.url(f"/files/{second['id']}"), headers=USER).status_code == 404
    assert ctx.client.get(ctx.url(f"/files/{second['id']}"), headers=STAFF).status_code == 200
    assert ctx.client.get(url, headers=STAFF).status_code == 404


def test_refusals_from_order_svc_are_passed_on_and_remove_the_file(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "DELIVERED")
    ctx.orders.requests["ORD2"] = request_doc("ORD2", "DELIVERED")
    assert ctx.client.post(ctx.url("/requests/ORD2/invoices"), json=_body(), headers=STAFF).status_code == 201
    taken = ctx.client.post(ctx.url("/requests/ORD1/invoices"), json=_body(), headers=STAFF)
    assert taken.status_code == 409
    assert taken.json()["code"] == "INVOICE_NUMBER_TAKEN"
    assert _pdfs(ctx) == []
    # Locked once paid; voiding then needs an administrator.
    assert ctx.client.post(ctx.url("/requests/ORD1/invoices"), json=_body(number="9"), headers=STAFF).status_code == 201
    ctx.orders.requests["ORD1"]["paid"] = True
    url = ctx.url("/requests/ORD1/invoices/invoice")
    locked = ctx.client.put(url, json=_body(number="9"), headers={**STAFF, "If-Match": "1"})
    assert locked.json()["code"] == "INVOICE_LOCKED"
    void = {"reason": "Paid twice"}
    assert ctx.client.request("DELETE", url, json=void, headers={**STAFF, "If-Match": "1"}).status_code == 403
    assert ctx.client.request("DELETE", url, json=void, headers={**ADMIN, "If-Match": "1"}).status_code == 204


def test_draft_suggests_the_next_number(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "DELIVERED")
    ctx.orders.next_number = "INV-0100"
    d = ctx.client.get(ctx.url("/requests/ORD1/invoice-draft?kind=invoice"), headers=STAFF).json()
    assert d["suggestedNumber"] == "INV-0100"


def test_customers_cannot_open_change_or_void(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"] = request_doc("ORD1", "DELIVERED")
    url = ctx.url("/requests/ORD1/invoices/invoice")
    assert ctx.client.get(url, headers=USER).status_code == 403
    assert ctx.client.put(url, json=_body(), headers={**USER, "If-Match": "1"}).status_code == 403
    assert (
        ctx.client.request("DELETE", url, json={"reason": "abc"}, headers={**USER, "If-Match": "1"}).status_code == 403
    )
