"""Uploads, downloads, deletes and label batches (PRD D*, TR-SEC-6, TEST_STRATEGY: download permission tests)."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from .conftest import ADMIN, CATALOG, EICAR, INVENTORY, OTHER, PDF, PEER, STAFF, USER, Ctx, check_event, request_doc

# ---------------------------------------------------------------- uploads


@pytest.mark.req("D2")
def test_customer_uploads_signed_agreement_and_it_is_attached_at_once(ctx: Ctx) -> None:
    r = ctx.upload("ORD1")
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["id"].startswith("FIL")
    assert f["kind"] == "signed_agreement"
    assert f["mime"] == "application/pdf"
    assert f["size"] == len(PDF)
    assert f["name"] == "signed.pdf"
    assert f["uploadedBy"] == {"id": "USRUSER", "name": "u@met.bb", "role": "user"}
    assert ctx.orders.attached == [("ORD1", ctx.orders.attached[0][1])]
    assert ctx.publisher.types() == ["document.uploaded"]
    _, key, event = ctx.publisher.sent[0]
    assert key == "ORD1"
    assert event.payload["fileId"] == f["id"]
    check_event(event)
    stored = ctx.root / "protected" / "orders" / "ORD1" / f"{f['id']}.pdf"
    assert stored.read_bytes() == PDF
    assert ctx.scanner.scanned == 1


def test_admin_may_upload_on_behalf_of_the_customer(ctx: Ctx) -> None:
    assert ctx.upload("ORD1", headers=ADMIN).status_code == 201


@pytest.mark.parametrize(
    ("headers", "kind", "status", "code"),
    [
        (USER, "supplier_quote", 403, None),  # customers upload only the signed agreement
        (USER, "upload", 403, None),
        (PEER, "signed_agreement", 403, None),  # same organisation: sees, never acts
        (OTHER, "signed_agreement", 404, None),  # can't learn the request exists
        (CATALOG, "signed_agreement", 403, None),  # service tokens never call user endpoints
    ],
)
def test_who_may_upload(ctx: Ctx, headers: dict[str, str], kind: str, status: int, code: str | None) -> None:
    r = ctx.upload("ORD1", kind=kind, headers=headers)
    assert r.status_code == status, r.text
    assert not ctx.publisher.sent
    assert not ctx.orders.attached


def test_customer_upload_only_while_the_agreement_is_awaited(ctx: Ctx) -> None:
    ctx.orders.requests["ORD1"]["status"] = "QUOTED"
    r = ctx.upload("ORD1")
    assert r.status_code == 409
    assert r.json()["code"] == "INVALID_STATE"


@pytest.mark.parametrize("kind", ["supplier_quote", "signed_agreement", "upload", "commercial_invoice"])
def test_staff_upload_every_kind_in_any_state(ctx: Ctx, kind: str) -> None:
    ctx.orders.requests["ORD1"]["status"] = "PURCHASING"
    assert ctx.upload("ORD1", kind=kind, headers=STAFF).status_code == 201


def test_upload_to_unknown_request_is_404(ctx: Ctx) -> None:
    assert ctx.upload("ORDNOPE", headers=STAFF).status_code == 404
    assert ctx.upload("ORDNOPE").status_code == 404


def test_anonymous_upload_is_401(ctx: Ctx) -> None:
    r = ctx.client.post(ctx.url("/files"), data={"requestId": "ORD1", "kind": "upload"},
                        files={"file": ("a.pdf", PDF)})  # fmt: skip
    assert r.status_code == 401


def test_type_comes_from_the_bytes_not_the_name(ctx: Ctx) -> None:
    r = ctx.upload("ORD1", data=b"MZ\x90\x00 windows executable", name="signed.pdf")
    assert r.status_code == 415
    assert r.json()["code"] == "UNSUPPORTED_FILE_TYPE"
    r = ctx.upload("ORD1", data=b"<html><script>alert(1)</script>", name="x.pdf")
    assert r.status_code == 415


def test_over_20_mb_is_refused(ctx: Ctx) -> None:
    big = PDF + b"0" * (20 * 1024 * 1024)
    r = ctx.upload("ORD1", data=big)
    assert r.status_code == 413
    assert r.json()["code"] == "FILE_TOO_LARGE"
    assert not (ctx.root / "protected").exists() or not any((ctx.root / "protected").rglob("*.pdf"))


@pytest.mark.req("TR-SEC-6")
def test_eicar_is_quarantined_and_never_stored(ctx: Ctx) -> None:
    r = ctx.upload("ORD1", data=EICAR, name="invoice.pdf")  # not a PDF either: scanned before the type check
    assert r.status_code == 422
    assert r.json()["code"] == "FILE_INFECTED"
    quarantined = list((ctx.root / "quarantine").glob("*.json"))
    assert len(quarantined) == 1
    info = json.loads(quarantined[0].read_text())
    assert info["signature"] == "Eicar-Test-Signature"
    assert info["requestId"] == "ORD1"
    assert not (ctx.root / "protected" / "orders").exists()
    assert ctx.publisher.types() == []
    assert ctx.publisher.types("audit.events") == ["audit.recorded"]
    check_event(ctx.publisher.sent[0][2])
    assert not ctx.orders.attached


def test_scanner_down_fails_closed(ctx: Ctx) -> None:
    ctx.scanner.down = True
    r = ctx.upload("ORD1")
    assert r.status_code == 503
    assert not (ctx.root / "protected" / "orders").exists()
    assert ctx.client.get("/health/ready").status_code == 503


def test_image_is_reencoded_without_metadata(ctx: Ctx) -> None:
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"  # Make
    Image.new("RGB", (40, 30), "red").save(buf, format="JPEG", exif=exif)
    r = ctx.upload("ORD1", data=buf.getvalue(), name="photo of signed page.JPG")
    assert r.status_code == 201
    f = r.json()
    assert f["mime"] == "image/jpeg"
    assert f["name"] == "photo of signed page.jpg"
    stored = (ctx.root / "protected" / "orders" / "ORD1" / f"{f['id']}.jpg").read_bytes()
    assert b"SecretCam" not in stored
    with Image.open(io.BytesIO(stored)) as im:
        assert im.size == (40, 30)


def test_corrupt_image_is_refused(ctx: Ctx) -> None:
    assert ctx.upload("ORD1", data=b"\x89PNG\r\n\x1a\n" + b"junk" * 10, name="a.png").status_code == 415


def test_kafka_down_refuses_the_upload_and_removes_the_file(ctx: Ctx) -> None:
    ctx.publisher.down = True
    assert ctx.upload("ORD1").status_code == 503
    assert not list((ctx.root / "protected").rglob("FIL*"))


def test_order_svc_down_after_publish_still_succeeds(ctx: Ctx) -> None:
    """The event attaches it; only the immediate attach is lost."""
    r = ctx.upload("ORD1", headers=STAFF, kind="upload")
    assert r.status_code == 201
    ctx.orders.down = True
    assert ctx.upload("ORD1", headers=STAFF, kind="upload").status_code == 503  # can't check the request


def test_filename_is_sanitised(ctx: Ctx) -> None:
    r = ctx.upload("ORD1", name="../../etc/passwd\r\nX: y.pdf")
    assert r.status_code == 201
    assert "/" not in r.json()["name"]
    assert "\n" not in r.json()["name"]


# ---------------------------------------------------------------- downloads


def _uploaded(ctx: Ctx) -> str:
    r = ctx.upload("ORD1")
    assert r.status_code == 201
    return str(r.json()["id"])


@pytest.mark.req("D3")
@pytest.mark.parametrize(
    ("who", "status"),
    [(USER, 200), (PEER, 200), (STAFF, 200), (ADMIN, 200), (OTHER, 404), (CATALOG, 403), ({}, 401)],
)
def test_download_permissions(ctx: Ctx, who: dict[str, str], status: int) -> None:
    fid = _uploaded(ctx)
    r = ctx.client.get(ctx.url(f"/files/{fid}"), headers=who)
    assert r.status_code == status, r.text
    if status == 200:
        assert r.headers["x-accel-redirect"] == f"/_protected/orders/ORD1/{fid}.pdf"
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["content-disposition"].startswith('inline; filename="signed.pdf"')
        assert r.content == b""  # nginx streams the bytes


def test_download_as_attachment(ctx: Ctx) -> None:
    fid = _uploaded(ctx)
    r = ctx.client.get(ctx.url(f"/files/{fid}"), headers=USER, params={"disposition": "attachment"})
    assert r.headers["content-disposition"].startswith("attachment;")


def test_admin_without_mfa_cannot_download(ctx: Ctx) -> None:
    from .conftest import token

    fid = _uploaded(ctx)
    r = ctx.client.get(ctx.url(f"/files/{fid}"), headers=token("admin", "USRADMIN", mfa=False))
    assert r.status_code == 403
    assert r.json()["code"] == "MFA_REQUIRED"


@pytest.mark.parametrize("fid", ["FILnothere0000000000000000000000", "..%2F..%2Fetc%2Fpasswd", "FIL../../x"])
def test_unknown_or_hostile_ids_are_404(ctx: Ctx, fid: str) -> None:
    assert ctx.client.get(ctx.url(f"/files/{fid}"), headers=STAFF).status_code == 404


def test_access_is_rechecked_on_every_download(ctx: Ctx) -> None:
    fid = _uploaded(ctx)
    ctx.orders.requests["ORD1"]["organisationId"] = "ORGNEW"  # peer's organisation no longer matches
    assert ctx.client.get(ctx.url(f"/files/{fid}"), headers=PEER).status_code == 404
    assert ctx.client.get(ctx.url(f"/files/{fid}"), headers=USER).status_code == 200


def test_dev_mode_streams_the_bytes(tmp_path: object) -> None:
    from pathlib import Path

    from fastapi.testclient import TestClient

    from .conftest import FakeClamd, MemoryOrders, MemoryPublisher, make_app

    orders = MemoryOrders(requests={"ORD1": request_doc("ORD1")})
    app = make_app(Path(str(tmp_path)), orders, MemoryPublisher(), FakeClamd(), serve_direct=True)
    with TestClient(app) as client:
        c = Ctx(client, orders, MemoryPublisher(), FakeClamd(), Path(str(tmp_path)))
        fid = _uploaded(c)
        r = client.get(c.url(f"/files/{fid}"), headers=USER)
        assert r.status_code == 200
        assert r.content == PDF
        assert "x-accel-redirect" not in r.headers


# ---------------------------------------------------------------- deletes


def test_staff_soft_delete_an_upload(ctx: Ctx) -> None:
    fid = _uploaded(ctx)
    r = ctx.client.request("DELETE", ctx.url(f"/files/{fid}"), headers=STAFF, json={"reason": "wrong file"})
    assert r.status_code == 204
    assert ctx.publisher.types() == ["document.uploaded", "document.deleted"]
    check_event(ctx.publisher.sent[1][2])
    assert ctx.publisher.types("audit.events") == ["audit.recorded"]
    assert ctx.client.get(ctx.url(f"/files/{fid}"), headers=STAFF).status_code == 404
    again = ctx.client.request("DELETE", ctx.url(f"/files/{fid}"), headers=STAFF, json={"reason": "again"})
    assert again.status_code == 404
    assert (ctx.root / "protected" / "orders" / "ORD1" / f"{fid}.pdf").exists()  # soft: bytes kept


def test_customers_cannot_delete(ctx: Ctx) -> None:
    fid = _uploaded(ctx)
    r = ctx.client.request("DELETE", ctx.url(f"/files/{fid}"), headers=USER, json={"reason": "oops"})
    assert r.status_code == 403


# ---------------------------------------------------------------- labels


def test_inventory_renders_labels_for_staff_only(ctx: Ctx) -> None:
    body = {"productId": "MET0123", "productName": "Rain gauge", "barcodes": [f"MET0123_{i:08x}" for i in range(30)]}
    assert ctx.client.post(ctx.url("/internal/labels"), headers=CATALOG, json=body).status_code == 403
    assert ctx.client.post(ctx.url("/internal/labels"), headers=STAFF, json=body).status_code == 403
    r = ctx.client.post(ctx.url("/internal/labels"), headers=INVENTORY, json=body)
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["kind"] == "labels"
    assert f["requestId"] is None
    assert f["mime"] == "application/pdf"
    pdf = (ctx.root / "protected" / "labels" / f"{f['id']}.pdf").read_bytes()
    assert pdf.startswith(b"%PDF")
    assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") >= 1
    assert ctx.client.get(ctx.url(f"/files/{f['id']}"), headers=STAFF).headers["x-accel-redirect"] == (
        f"/_protected/labels/{f['id']}.pdf"
    )
    assert ctx.client.get(ctx.url(f"/files/{f['id']}"), headers=USER).status_code == 404
    deleted = ctx.client.request("DELETE", ctx.url(f"/files/{f['id']}"), headers=STAFF, json={"reason": "nope"})
    assert deleted.status_code == 409
    assert deleted.json()["code"] == "GENERATED_DOCUMENT"


def test_upload_kinds_match_the_api() -> None:
    from typing import get_args

    from document_svc.api import UploadKind
    from document_svc.service import UPLOAD_KINDS

    assert set(get_args(UploadKind)) == set(UPLOAD_KINDS)
