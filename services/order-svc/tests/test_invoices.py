"""Invoice records (docs/plans/2026-11-24-invoice-crud.md): one current invoice per kind per request, revisions,
void, lock once paid, unique numbers, the amount owed and the start-up upgrade of older PDFs."""

from __future__ import annotations

import uuid
from typing import Any

from order_svc import upgrade

from .conftest import DOCUMENT, USER, Ctx

STAFF_ACTOR = {"id": "USRSTAFF", "name": "S Taff", "role": "staff"}


def body(number: str = "2026-014", rev: int | None = None, **kw: Any) -> dict[str, Any]:
    fid = kw.pop("fid", None) or "FIL" + uuid.uuid4().hex
    out = {
        "rev": rev,
        "number": number,
        "date": "2026-11-24",
        "lines": [{"lineId": None, "description": "MK1 - Rain gauge", "qty": 2, "unitPrice": "150.00"}],
        "fees": "25.00",
        "discount": "10.00",
        "shipping": "40.00",
        "by": STAFF_ACTOR,
        "file": {
            "id": fid,
            "kind": kw.pop("kind", "invoice"),
            "name": f"Invoice-{number}.pdf",
            "mime": "application/pdf",
            "size": 10,
        },
    }
    out.update(kw)
    return out


def put(ctx: Ctx, rid: str, b: dict[str, Any], kind: str = "invoice") -> Any:
    return ctx.client.put(ctx.url(f"/internal/requests/{rid}/invoices/{kind}"), headers=DOCUMENT, json=b)


def void(ctx: Ctx, rid: str, rev: int, kind: str = "invoice", admin: bool = False) -> Any:
    b = {"rev": rev, "reason": "Wrong prices", "by": STAFF_ACTOR, "admin": admin}
    return ctx.client.post(ctx.url(f"/internal/requests/{rid}/invoices/{kind}/void"), headers=DOCUMENT, json=b)


def test_create_revise_and_void_one_invoice(ctx: Ctx) -> None:
    rid = ctx.paid_request("MET1", qty=1)
    r = put(ctx, rid, body(fid="FILA"))
    assert r.status_code == 200, r.text
    inv = r.json()["invoice"]
    assert inv["rev"] == 1
    assert inv["total"] == "355.00"
    assert inv["source"] == "STAFF"
    assert inv["locked"] is False
    assert r.json()["replacedFileId"] is None
    view = ctx.get(rid)
    assert view["invoices"]["invoice"]["number"] == "2026-014"
    assert [f["id"] for f in view["files"] if f["kind"] == "invoice"] == ["FILA"]

    # A second "create" is refused: one current invoice per kind.
    again = put(ctx, rid, body("2026-099"))
    assert again.status_code == 409
    assert again.json()["code"] == "INVOICE_EXISTS"

    # A revision: needs the current rev; the old PDF leaves the files list but stays in the revisions.
    stale = put(ctx, rid, body(rev=7))
    assert stale.status_code == 409
    r = put(ctx, rid, body(rev=1, fid="FILB", discount="0.00"))
    assert r.status_code == 200, r.text
    assert r.json()["replacedFileId"] == "FILA"
    inv = ctx.get(rid)["invoices"]["invoice"]
    assert inv["rev"] == 2
    assert inv["fileId"] == "FILB"
    assert inv["total"] == "365.00"
    assert [x["fileId"] for x in inv["revisions"]] == ["FILA", "FILB"]
    assert [f["id"] for f in ctx.get(rid)["files"] if f["kind"] == "invoice"] == ["FILB"]
    # Customers see which PDF it is, never the builder's lines or earlier copies.
    mine = ctx.get(rid, USER)["invoices"]["invoice"]
    assert set(mine) == {"number", "rev", "fileId", "date", "total"}

    # Void: the PDF goes, the record moves to the staff-only voided list, its number stays taken.
    assert void(ctx, rid, 1).status_code == 409
    r = void(ctx, rid, 2)
    assert r.status_code == 200, r.text
    assert r.json()["voidedFileId"] == "FILB"
    view = ctx.get(rid)
    assert view["invoices"] == {}
    assert [f["id"] for f in view["files"] if f["kind"] == "invoice"] == []
    assert view["voidedInvoices"][0]["number"] == "2026-014"
    assert "voidedInvoices" not in ctx.get(rid, USER)
    reuse = put(ctx, rid, body("2026-014"))
    assert reuse.status_code == 409
    assert reuse.json()["code"] == "INVOICE_NUMBER_TAKEN"
    assert put(ctx, rid, body("2026-015")).status_code == 200  # a new invoice after the void


def test_numbers_are_unique_per_kind_and_suggested(ctx: Ctx) -> None:
    a = ctx.paid_request("MET1", qty=1)
    b = ctx.paid_request("MET1", qty=1)
    nxt = ctx.client.get(ctx.url("/internal/invoice-numbers/next"), headers=DOCUMENT, params={"kind": "invoice"})
    assert nxt.json() == {"number": None}  # nothing to count from yet
    assert put(ctx, a, body("INV-0099")).status_code == 200
    taken = put(ctx, b, body("inv-0099 "))  # case and spaces do not make a new number
    assert taken.status_code == 409
    assert taken.json()["code"] == "INVOICE_NUMBER_TAKEN"
    # Another kind may share it (a commercial invoice is numbered on its own).
    assert put(ctx, b, body("INV-0099", kind="commercial_invoice"), "commercial_invoice").status_code == 200
    nxt = ctx.client.get(ctx.url("/internal/invoice-numbers/next"), headers=DOCUMENT, params={"kind": "invoice"})
    assert nxt.json() == {"number": "INV-0100"}
    # A revision may keep its own number, or change it; the old one stays taken.
    assert put(ctx, a, body("INV-0099", rev=1)).status_code == 200
    assert put(ctx, a, body("INV-0105", rev=2)).status_code == 200
    assert put(ctx, b, body("INV-0099")).json()["code"] == "INVOICE_NUMBER_TAKEN"


def test_invoice_total_is_what_the_customer_owes_and_locks_once_paid(ctx: Ctx) -> None:
    rid = ctx.paid_request("MET1", qty=1)
    ctx.force(rid, status="DELIVERED")
    ctx.force(rid, total="752.00")
    assert ctx.get(rid, USER)["amountDue"] == "752.00"
    assert put(ctx, rid, body()).status_code == 200
    assert ctx.get(rid, USER)["amountDue"] == "355.00"
    listed = ctx.client.get(ctx.url("/requests"), headers=USER, params={"payment": "due"}).json()["items"]
    assert listed[0]["amountDue"] == "355.00"  # the list projection carries it too
    # A commercial invoice is for customs: it never changes the amount owed.
    put(ctx, rid, body("C-1", kind="commercial_invoice", discount="300.00"), "commercial_invoice")
    assert ctx.get(rid, USER)["amountDue"] == "355.00"

    ctx.ok(rid, "mark-paid", {})
    assert ctx.get(rid)["invoices"]["invoice"]["locked"] is True
    locked = put(ctx, rid, body(rev=1))
    assert locked.status_code == 409
    assert locked.json()["code"] == "INVOICE_LOCKED"
    assert void(ctx, rid, 1).status_code == 403  # staff: no
    assert void(ctx, rid, 1, admin=True).status_code == 200  # an administrator, with a reason


def test_internal_routes_are_for_document_svc_only(ctx: Ctx) -> None:
    rid = ctx.paid_request("MET1", qty=1)
    r = ctx.client.put(ctx.url(f"/internal/requests/{rid}/invoices/invoice"), headers=USER, json=body())
    assert r.status_code == 403
    assert put(ctx, "ORDnope", body()).status_code == 404
    assert put(ctx, rid, body(), "probono_invoice").status_code == 422


def test_upgrade_turns_older_pdfs_into_records(ctx: Ctx) -> None:
    a = ctx.paid_request("MET1", qty=1)
    b = ctx.paid_request("MET1", qty=1)
    ctx.attach(a, "invoice", "FILOLD")
    ctx.attach(a, "invoice", "FILNEW")
    ctx.force(a, invoice={"number": "77"})
    ctx.attach(b, "invoice", "FILB")
    ctx.run(ctx.db["orders"].update_one({"id": b, "files.id": "FILB"}, {"$set": {"files.$.name": "Invoice-77.pdf"}}))
    ctx.attach(b, "commercial_invoice", "FILC")  # name "commercial_invoice.pdf": no number

    out = ctx.run(upgrade.invoices(ctx.db["orders"]))
    assert out["recordsMade"] == 3
    assert out["numberClashes"] == [b]  # "77" already belongs to request a
    inv = ctx.get(a)["invoices"]["invoice"]
    assert inv["fileId"] == "FILNEW"
    assert inv["number"] == "77"
    assert inv["source"] == "LEGACY"
    assert inv["lines"] is None
    assert inv["total"] is None
    assert [f["id"] for f in ctx.get(a)["files"] if f["kind"] == "invoice"] == ["FILNEW"]
    assert ctx.get(b)["invoices"]["commercial_invoice"]["number"] is None
    # Idempotent; and a LEGACY record without a total leaves the amount owed alone.
    assert ctx.run(upgrade.invoices(ctx.db["orders"]))["recordsMade"] == 0
    ctx.force(a, status="DELIVERED", total="10.00")
    assert ctx.get(a, USER)["amountDue"] == "10.00"
    # Saving over a legacy record issues rev 2 with lines (and a number when it had none).
    assert put(ctx, b, body("C-9", rev=1, kind="commercial_invoice"), "commercial_invoice").status_code == 200
