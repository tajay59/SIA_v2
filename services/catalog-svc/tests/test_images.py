"""Product images (PRD C6): upload -> media.jobs, media.results -> images[], primary, delete."""

from __future__ import annotations

from pathlib import Path

import pytest

from catalog_svc.consumer import make_handler
from cimh_common.outbox import new_event

from .conftest import STAFF, USER, Ctx, check_event

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64


def processed(ctx: Ctx, pid: str, fid: str, ok: bool = True) -> None:
    payload = {"jobId": "JOB1", "productId": pid, "ok": ok}
    if ok:
        payload.update(fileId=fid, url=f"/media/products/{fid}.webp", w=800, h=600)
    evt = new_event("image.processed", payload, correlation_id="c1")
    check_event(evt.model_dump(mode="python"))
    ctx.run(make_handler(ctx.app.state.catalog)(evt))


@pytest.mark.req("C6")
def test_upload_queues_one_job_per_image(ctx: Ctx) -> None:
    p = ctx.create()
    files = [("files", ("a.jpg", JPEG, "image/jpeg")), ("files", ("b.png", PNG, "image/png")),
             ("files", ("c.webp", WEBP, "image/webp"))]  # fmt: skip
    r = ctx.client.post(
        ctx.url(f"/products/{p['id']}/images"), headers=STAFF, files=files, data={"removeBackground": "true"}
    )
    assert r.status_code == 202, r.text
    jobs = r.json()["jobIds"]
    assert len(jobs) == 3
    events = [e for e in ctx.product(p["id"])["outbox"] if e["type"] == "image.process"]
    assert [e["payload"]["jobId"] for e in events] == jobs
    for e in events:
        check_event(e)
        assert e["payload"]["removeBackground"] is True
        src = Path(ctx.media) / e["payload"]["sourcePath"]
        assert src.parent.name == "incoming"
        assert src.exists()
    assert sorted(Path(ctx.media, e["payload"]["sourcePath"]).suffix for e in events) == [".jpg", ".png", ".webp"]


def test_upload_checks_the_bytes_size_and_product(tmp_path: Path) -> None:
    ctx = Ctx(tmp_path, max_image_bytes=100)
    with ctx.client:
        p = ctx.create()
        url = ctx.url(f"/products/{p['id']}/images")
        r = ctx.client.post(url, headers=STAFF, files=[("files", ("evil.jpg", b"<?php echo 1;", "image/jpeg"))])
        assert r.status_code == 422
        assert r.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"
        r = ctx.client.post(url, headers=STAFF, files=[("files", ("big.jpg", JPEG + b"\x00" * 200, "image/jpeg"))])
        assert r.status_code == 413
        r = ctx.client.post(
            ctx.url("/products/NOPE/images"), headers=STAFF, files=[("files", ("a.jpg", JPEG, "image/jpeg"))]
        )
        assert r.status_code == 404
        r = ctx.client.post(url, headers=USER, files=[("files", ("a.jpg", JPEG, "image/jpeg"))])
        assert r.status_code == 403
        many = [("files", (f"{i}.jpg", JPEG, "image/jpeg")) for i in range(11)]
        assert ctx.client.post(url, headers=STAFF, files=many).status_code == 422
        incoming = tmp_path / "incoming"
        assert not incoming.exists() or not any(incoming.iterdir())  # nothing left behind
    ctx.loop.close()


@pytest.mark.req("C6")
def test_processed_images_are_attached_once_and_the_first_is_primary(ctx: Ctx) -> None:
    p = ctx.create()
    processed(ctx, p["id"], "IMG1")
    processed(ctx, p["id"], "IMG1")  # redelivery
    processed(ctx, p["id"], "IMG2")
    processed(ctx, p["id"], "IMG3", ok=False)
    processed(ctx, "NOPE", "IMG9")
    images = ctx.client.get(ctx.url(f"/products/{p['id']}")).json()["images"]
    assert [(i["fileId"], i["primary"]) for i in images] == [("IMG1", True), ("IMG2", False)]
    added = [e for e in ctx.product(p["id"])["outbox"] if e["type"] == "product.image_added"]
    assert [e["payload"]["fileId"] for e in added] == ["IMG1", "IMG2"]
    for e in added:
        check_event(e)


def test_primary_and_delete(ctx: Ctx) -> None:
    p = ctx.create()
    processed(ctx, p["id"], "IMG1")
    processed(ctx, p["id"], "IMG2")
    products = Path(ctx.media) / "products"
    products.mkdir()
    for name in ("IMG1.webp", "IMG1-400.webp", "IMG2.webp"):
        (products / name).write_bytes(b"x")

    base = ctx.url(f"/products/{p['id']}/images")
    r = ctx.client.patch(f"{base}/IMG2", headers=STAFF, json={"primary": True})
    assert [(i["fileId"], i["primary"]) for i in r.json()["images"]] == [("IMG1", False), ("IMG2", True)]
    assert ctx.client.patch(f"{base}/NOPE", headers=STAFF, json={"primary": True}).status_code == 404

    assert ctx.client.delete(f"{base}/IMG2", headers=STAFF).status_code == 204
    images = ctx.client.get(ctx.url(f"/products/{p['id']}"), headers=STAFF).json()["images"]
    assert [(i["fileId"], i["primary"]) for i in images] == [("IMG1", True)]  # primary moves to what is left
    assert sorted(f.name for f in products.iterdir()) == ["IMG1-400.webp", "IMG1.webp"]
    assert ctx.client.delete(f"{base}/IMG2", headers=STAFF).status_code == 404
    assert ctx.client.delete(ctx.url("/products/NOPE/images/IMG1"), headers=STAFF).status_code == 404
