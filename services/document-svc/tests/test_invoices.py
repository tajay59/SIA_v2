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
