"""Announcements (plan 2026-11-23): admin CRUD, TTL, live list, audit, and the catalog-push socket."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from catalog_svc.config import Settings
from catalog_svc.main import BASE, build_push_app

from .conftest import ADMIN, STAFF, USER, Ctx, check_event, token

URL = "/admin/announcements"


def body(**over: Any) -> dict[str, Any]:
    return {"message": "New radar spares in stock", "tone": "INFO", "audience": "BOTH", "ttl": {"preset": "1d"}, **over}


def make(ctx: Ctx, **over: Any) -> dict[str, Any]:
    r = ctx.client.post(ctx.url(URL), headers=ADMIN, json=body(**over))
    assert r.status_code == 201, r.text
    return dict(r.json())


def iso(d: datetime) -> str:
    return d.isoformat().replace("+00:00", "Z")


def test_create_list_and_live(ctx: Ctx) -> None:
    a = make(ctx, link={"label": "See the radar parts", "url": "/catalogue?type=RAD"})
    assert a["id"].startswith("ANN")
    assert a["version"] == 1
    assert a["dismissible"] is True
    exp = datetime.fromisoformat(a["expiresAt"].replace("Z", "+00:00"))
    assert timedelta(hours=23, minutes=59) < exp - datetime.now(UTC) <= timedelta(days=1)
    assert a["createdBy"]["id"] == "USRADMIN"
    # Anyone sees a SHOP/BOTH message; no Actors in the public view.
    live = ctx.client.get(ctx.url("/announcements")).json()["items"]
    assert [i["id"] for i in live] == [a["id"]]
    assert "createdBy" not in live[0]
    assert ctx.client.get(ctx.url("/announcements")).headers["cache-control"] == "no-store"
    assert [i["id"] for i in ctx.client.get(ctx.url(URL), headers=ADMIN).json()["items"]] == [a["id"]]
    # Audit on the misc carrier.
    audit = ctx.misc("announcements")["outbox"][0]
    check_event(audit)
    assert audit["payload"]["action"] == "announcement.created"
    assert audit["payload"]["entity"] == {"type": "announcement", "id": a["id"]}


def test_audience_and_sia_needs_staff(ctx: Ctx) -> None:
    shop = make(ctx, audience="SHOP")
    sia = make(ctx, audience="SIA", message="Stocktake Friday")
    assert [i["id"] for i in ctx.client.get(ctx.url("/announcements?app=shop")).json()["items"]] == [shop["id"]]
    assert ctx.client.get(ctx.url("/announcements?app=sia")).status_code == 401
    assert ctx.client.get(ctx.url("/announcements?app=sia"), headers=USER).status_code == 403
    staff = ctx.client.get(ctx.url("/announcements?app=sia"), headers=STAFF).json()["items"]
    assert [i["id"] for i in staff] == [sia["id"]]
    assert ctx.client.get(ctx.url("/announcements?app=other")).status_code == 422


def test_alerts_first_and_never_dismissible(ctx: Ctx) -> None:
    info = make(ctx)
    alert = make(ctx, tone="ALERT", dismissible=True, message="Prices change 1 December")
    assert alert["dismissible"] is False
    assert [i["id"] for i in ctx.client.get(ctx.url("/announcements")).json()["items"]] == [alert["id"], info["id"]]


def test_scheduled_and_expired_are_not_live(ctx: Ctx) -> None:
    later = datetime.now(UTC) + timedelta(hours=2)
    s = make(ctx, startsAt=iso(later), ttl={"preset": "1h"})
    assert s["startsAt"].startswith(iso(later)[:16])
    assert ctx.client.get(ctx.url("/announcements")).json()["items"] == []
    assert len(ctx.client.get(ctx.url(URL), headers=ADMIN).json()["items"]) == 1
    # TTL ran out (Mongo's monitor may not have deleted it yet): gone everywhere.
    a = make(ctx)
    ctx.run(ctx.db["announcements"].update_one({"id": a["id"]}, {"$set": {"expiresAt": datetime.now(UTC)}}))
    assert ctx.client.get(ctx.url("/announcements")).json()["items"] == []
    assert ctx.client.get(ctx.url(f"{URL}/{a['id']}"), headers=ADMIN).status_code == 404


def test_validation(ctx: Ctx) -> None:
    def code(**over: Any) -> tuple[int, str | None]:
        r = ctx.client.post(ctx.url(URL), headers=ADMIN, json=body(**over))
        return r.status_code, r.json().get("code")

    assert code(message="x" * 281)[0] == 422
    assert code(message="   ") == (422, "VALIDATION_FAILED")
    assert code(link={"label": "x", "url": "javascript:alert(1)"}) == (422, "LINK_NOT_ALLOWED")
    assert code(link={"label": "x", "url": "//evil.example"}) == (422, "LINK_NOT_ALLOWED")
    assert code(link={"label": "x", "url": "http://plain.example"}) == (422, "LINK_NOT_ALLOWED")
    assert code(link={"label": "x", "url": "https://wmo.int/news"})[0] == 201
    soon = datetime.now(UTC)
    assert code(ttl={"until": iso(soon + timedelta(days=91))}) == (422, "TTL_OUT_OF_RANGE")
    assert code(ttl={"until": iso(soon - timedelta(hours=1))})[1] in ("TTL_OUT_OF_RANGE", "STARTS_AFTER_EXPIRY")
    assert code(ttl={"preset": "1d", "until": iso(soon + timedelta(days=1))})[0] == 422
    assert code(ttl={"preset": "2y"})[0] == 422
    assert code(ttl={"until": "2026-12-01T10:00:00"})[0] == 422  # no offset
    assert code(startsAt=iso(soon + timedelta(days=2)), ttl={"until": iso(soon + timedelta(days=1))}) == (
        422,
        "STARTS_AFTER_EXPIRY",
    )
    assert code(extra=1)[0] == 422
    assert ctx.client.post(ctx.url(URL), headers=STAFF, json=body()).status_code == 403


def test_update_and_end_now(ctx: Ctx) -> None:
    a = make(ctx)
    url = ctx.url(f"{URL}/{a['id']}")
    assert ctx.client.patch(url, headers=ADMIN, json={"message": "Edited"}).status_code == 428
    assert ctx.client.patch(url, headers={**ADMIN, "If-Match": "9"}, json={"message": "Edited"}).status_code == 409
    r = ctx.client.patch(url, headers={**ADMIN, "If-Match": "1"}, json={"message": "Edited", "ttl": {"preset": "30d"}})
    assert r.status_code == 200, r.text
    assert r.headers["etag"] == '"2"'
    assert r.json()["message"] == "Edited"
    assert datetime.fromisoformat(r.json()["expiresAt"].replace("Z", "+00:00")) - datetime.now(UTC) > timedelta(days=29)
    # Turning it into an alert removes the close button.
    r = ctx.client.patch(url, headers={**ADMIN, "If-Match": "2"}, json={"tone": "ALERT"})
    assert r.json()["dismissible"] is False
    assert ctx.client.patch(url, headers={**ADMIN, "If-Match": "3"}, json={}).status_code == 422
    assert ctx.client.delete(url, headers={**ADMIN, "If-Match": "1"}).status_code == 409
    assert ctx.client.delete(url, headers={**ADMIN, "If-Match": "3"}).status_code == 204
    assert ctx.client.get(url, headers=ADMIN).status_code == 404
    assert ctx.client.delete(url, headers={**ADMIN, "If-Match": "3"}).status_code == 404
    actions = [e["payload"]["action"] for e in ctx.misc("announcements")["outbox"]]
    assert actions == ["announcement.created", "announcement.updated", "announcement.updated", "announcement.ended"]


def test_ttl_index_exists(ctx: Ctx) -> None:
    info = ctx.db["announcements"]._c.index_information()  # the mock wraps a sync collection
    ttl = info["announcement_ttl"]
    assert ttl["key"] == [("expiresAt", 1)]
    assert ttl.get("expireAfterSeconds") == 0


def test_admin_without_mfa_refused(ctx: Ctx) -> None:
    r = ctx.client.get(ctx.url(URL), headers=token("admin", "USRA", "a@cimh.edu.bb", mfa=False))
    assert r.json()["code"] == "MFA_REQUIRED"


def test_writes_publish_a_change(ctx: Ctx) -> None:
    sent: list[str] = []

    async def publish(ann_id: str) -> None:
        sent.append(ann_id)

    ctx.app.state.announcements._publish = publish
    a = make(ctx)
    ctx.client.patch(ctx.url(f"{URL}/{a['id']}"), headers={**ADMIN, "If-Match": "1"}, json={"message": "x"})
    ctx.client.delete(ctx.url(f"{URL}/{a['id']}"), headers={**ADMIN, "If-Match": "2"})
    assert sent == [a["id"]] * 3

    async def broken(_: str) -> None:
        raise ConnectionError("redis down")

    ctx.app.state.announcements._publish = broken
    make(ctx)  # still 201: push is best effort


# ---------------------------------------------------------------- catalog-push socket


class Push:
    def __init__(self, ctx: Ctx, **settings: Any) -> None:
        from .conftest import verifier

        self.app = build_push_app(Settings(**settings), db=ctx.db, token_verifier=verifier(), configure_logs=False)
        self.client = TestClient(self.app)
        self.hub = self.app.state.push_hub

    def sync(self) -> None:
        # The test client runs the app on its own loop thread; run sync there.
        self.client.portal.call(self.hub.sync)  # type: ignore[union-attr]


@pytest.fixture
def push(ctx: Ctx) -> Iterator[Push]:
    p = Push(ctx, push_reconcile_seconds=3600)
    with p.client:
        yield p


def frame(ws: Any) -> dict[str, Any]:
    return dict(json.loads(ws.receive_text()))


def stream(path: str = "") -> str:
    return BASE + "/announcements/stream" + path


def test_snapshot_then_changes(ctx: Ctx, push: Push) -> None:
    a = make(ctx)
    with push.client.websocket_connect(stream(), headers={"origin": "http://testserver"}) as ws:
        snap = frame(ws)
        assert snap["type"] == "snapshot"
        assert [i["id"] for i in snap["items"]] == [a["id"]]
        assert snap["serverTime"]
        b = make(ctx, message="Second")
        push.sync()
        up = frame(ws)
        assert up == {"type": "upsert", "item": up["item"]}
        assert up["item"]["id"] == b["id"]
        ctx.client.patch(ctx.url(f"{URL}/{a['id']}"), headers={**ADMIN, "If-Match": "1"}, json={"message": "Edited"})
        push.sync()
        assert frame(ws)["item"]["message"] == "Edited"
        ctx.client.delete(ctx.url(f"{URL}/{b['id']}"), headers={**ADMIN, "If-Match": "1"})
        push.sync()
        assert frame(ws) == {"type": "remove", "id": b["id"]}
        # Expiry: the reconcile removes it even before Mongo's TTL monitor deletes the document.
        ctx.run(ctx.db["announcements"].update_one({"id": a["id"]}, {"$set": {"expiresAt": datetime.now(UTC)}}))
        push.sync()
        assert frame(ws) == {"type": "remove", "id": a["id"]}


def test_shop_socket_never_gets_sia_messages(ctx: Ctx, push: Push) -> None:
    with push.client.websocket_connect(stream("?app=shop")) as ws:
        assert frame(ws)["items"] == []
        make(ctx, audience="SIA")
        s = make(ctx, audience="SHOP")
        push.sync()
        assert frame(ws)["item"]["id"] == s["id"]


def test_origin_guard(ctx: Ctx, push: Push) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        push.client.websocket_connect(stream(), headers={"origin": "https://evil.example"}),
    ):
        pass
    assert exc.value.code == 1008


def test_configured_origins(ctx: Ctx) -> None:
    p = Push(ctx, push_origins=("https://store.example",), push_reconcile_seconds=3600)
    with p.client:
        with p.client.websocket_connect(stream(), headers={"origin": "https://store.example"}) as ws:
            assert frame(ws)["type"] == "snapshot"
        with (
            pytest.raises(WebSocketDisconnect),
            p.client.websocket_connect(stream(), headers={"origin": "http://testserver"}),
        ):
            pass


def cookie(headers: dict[str, str]) -> dict[str, str]:
    return {"cookie": "access_token=" + headers["Authorization"].removeprefix("Bearer ")}


def test_sia_socket_needs_staff(ctx: Ctx, push: Push) -> None:
    for headers, code in (({}, 4401), (cookie(USER), 4403), (cookie(token("admin", "A", mfa=False)), 4401)):
        with push.client.websocket_connect(stream("?app=sia"), headers=headers) as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_text()
            assert exc.value.code == code
    s = make(ctx, audience="SIA")
    with push.client.websocket_connect(stream("?app=sia"), headers=cookie(STAFF)) as ws:
        assert [i["id"] for i in frame(ws)["items"]] == [s["id"]]


def test_socket_cap(ctx: Ctx) -> None:
    p = Push(ctx, push_max_sockets=1, push_reconcile_seconds=3600)
    with p.client, p.client.websocket_connect(stream()) as first:
        assert frame(first)["type"] == "snapshot"
        with p.client.websocket_connect(stream()) as second:
            with pytest.raises(WebSocketDisconnect) as exc:
                second.receive_text()
            assert exc.value.code == 1013


def test_oversize_frame_closes(ctx: Ctx, push: Push) -> None:
    with push.client.websocket_connect(stream()) as ws:
        frame(ws)
        ws.send_text("x" * 2000)
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
        assert exc.value.code == 1009
    # The hub forgot the socket.
    assert push.hub.clients == set()


def test_push_metrics(ctx: Ctx, push: Push) -> None:
    with push.client.websocket_connect(stream()) as ws:
        frame(ws)
        text = push.client.get("/metrics").text
        assert 'push_sockets{app="shop"} 1.0' in text
        assert "push_sockets_max 5000.0" in text


def test_redis_listener_pokes_sync(ctx: Ctx) -> None:
    """A pub/sub message makes the worker sync (fake pubsub; the real one is in the integration suite)."""

    class FakePubSub:
        def __init__(self) -> None:
            self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def subscribe(self, _: str) -> None: ...

        async def get_message(self, ignore_subscribe_messages: bool, timeout: float) -> dict[str, Any] | None:  # noqa: ASYNC109
            try:
                return await asyncio.wait_for(self.queue.get(), timeout)
            except TimeoutError:
                return None

        async def aclose(self) -> None: ...

    ps = FakePubSub()

    class FakeRedis:
        def pubsub(self) -> FakePubSub:
            return ps

    p = Push(ctx, push_reconcile_seconds=3600)
    p.app.state.push_hub.redis = FakeRedis()
    with p.client, p.client.websocket_connect(stream()) as ws:
        frame(ws)
        a = make(ctx)
        p.client.portal.call(ps.queue.put, {"type": "message", "data": a["id"]})  # type: ignore[union-attr]
        assert frame(ws)["item"]["id"] == a["id"]


def test_product_link(ctx: Ctx) -> None:
    """A banner about a product change links to that product (owner 2026-11-23); each app builds its own page."""
    shop_item = ctx.create(name="WXT536 weather station")  # MET + sellable: on SHOP
    staff_only = ctx.create(name="Bench multimeter", type="EQUIP", sn="SN-0002")
    a = make(ctx, link={"productId": shop_item["id"]})
    assert a["link"] == {"label": "WXT536 weather station", "productId": shop_item["id"]}
    live = ctx.client.get(ctx.url("/announcements")).json()["items"]
    assert live[0]["link"]["productId"] == shop_item["id"]
    named = make(ctx, link={"productId": shop_item["id"], "label": "See the new price"})
    assert named["link"]["label"] == "See the new price"

    def code(**over: Any) -> tuple[int, str | None]:
        r = ctx.client.post(ctx.url(URL), headers=ADMIN, json=body(**over))
        return r.status_code, r.json().get("code")

    assert code(link={"productId": "NOPE"}) == (422, "PRODUCT_NOT_FOUND")
    assert code(link={"productId": staff_only["id"]}) == (422, "PRODUCT_NOT_ON_SHOP")
    assert code(link={"productId": staff_only["id"]}, audience="SIA")[0] == 201
    assert code(link={"productId": shop_item["id"], "url": "/x", "label": "x"})[0] == 422
    assert code(link={"label": "x"})[0] == 422
    assert code(link={"url": "/catalogue"})[1] == "VALIDATION_FAILED"  # a web address needs a label

    # Moving an SIA-only product banner onto SHOP checks the product again.
    sia = make(ctx, audience="SIA", link={"productId": staff_only["id"]})
    r = ctx.client.patch(ctx.url(f"{URL}/{sia['id']}"), headers={**ADMIN, "If-Match": "1"}, json={"audience": "BOTH"})
    assert r.json()["code"] == "PRODUCT_NOT_ON_SHOP"
    # A deactivated product can't be linked any more.
    ctx.client.delete(ctx.url(f"/products/{shop_item['id']}"), headers={**STAFF, "If-Match": str(shop_item["version"])})
    assert code(link={"productId": shop_item["id"]}) == (422, "PRODUCT_NOT_FOUND")
