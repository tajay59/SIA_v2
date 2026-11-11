"""Service-to-service endpoints (TAD §6) and the stock consumer (inventory.stock.events)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from catalog_svc.consumer import make_handler
from cimh_common.outbox import new_event

from .conftest import INVENTORY, ORDER, STAFF, USER, Ctx, check_event


def test_order_svc_gets_staff_summaries(ctx: Ctx) -> None:
    a = ctx.create()
    b = ctx.create(name="Hidden", sellable=False)
    r = ctx.client.post(
        ctx.url("/internal/products/summaries"), headers=ORDER, json={"ids": [a["id"], b["id"], "NOPE"]}
    )
    items = {i["id"]: i for i in r.json()["items"]}
    assert set(items) == {a["id"], b["id"]}
    assert items[a["id"]]["cost"] == "1250.00"
    assert ctx.client.post(ctx.url("/internal/products/summaries"), headers=STAFF, json={"ids": []}).status_code == 403


def test_places_are_written_by_inventory_only(ctx: Ctx) -> None:
    site = {"kind": "site", "barcode": "SITE1", "name": "Husbands", "country": "BB", "active": True}
    loc = {"kind": "location", "barcode": "LOC1", "name": "Store A", "site": "SITE1", "active": True}
    shelf = {"kind": "shelf", "barcode": "SHF1", "name": "Shelf 1", "site": "SITE1", "location": "LOC1", "number": 1,
             "active": True}  # fmt: skip
    for body in (site, loc, shelf):
        r = ctx.client.put(ctx.url("/internal/places"), headers=INVENTORY, json=body)
        assert r.status_code == 200, r.text
    assert ctx.client.put(ctx.url("/internal/places"), headers=ORDER, json=site).status_code == 403
    assert ctx.client.put(ctx.url("/internal/places"), headers=USER, json=site).status_code == 403
    bad = {**shelf, "location": None}
    assert ctx.client.put(ctx.url("/internal/places"), headers=INVENTORY, json=bad).status_code == 422
    assert ctx.client.put(ctx.url("/internal/places"), headers=INVENTORY, json={**loc, "site": None}).status_code == 422

    assert ctx.client.get(ctx.url("/internal/places"), headers=ORDER).status_code == 403  # inventory only
    every = ctx.client.get(ctx.url("/internal/places"), headers=INVENTORY).json()["items"]
    assert [p["barcode"] for p in every] == ["LOC1", "SHF1", "SITE1"]  # by kind, then id
    shelves = ctx.client.get(
        ctx.url("/internal/places"), headers=INVENTORY, params={"kind": "shelf", "location": "LOC1"}
    )
    assert shelves.json()["items"][0]["number"] == 1
    renamed = ctx.client.put(ctx.url("/internal/places"), headers=INVENTORY, json={**site, "name": "Husbands HQ"})
    assert renamed.json()["name"] == "Husbands HQ"
    assert ctx.misc("SITE1")["updatedBy"]["id"] == "svc:inventory"


def stock(ctx: Ctx, pid: str, available: int, at: datetime) -> None:
    evt = new_event("stock.changed", {"productId": pid, "available": available, "reserved": 0}, correlation_id="c")
    evt.occurredAt = at
    check_event(evt.model_dump(mode="python"))
    ctx.run(make_handler(ctx.app.state.catalog)(evt))


def test_stock_events_drive_in_stock_and_never_go_back_in_time(ctx: Ctx) -> None:
    p = ctx.create()
    t0 = datetime(2026, 11, 7, 12, tzinfo=UTC)
    stock(ctx, p["id"], 3, t0)
    view = ctx.client.get(ctx.url(f"/products/{p['id']}"), headers=STAFF).json()
    assert (view["inStock"], view["stockCount"]) == (True, 3)
    stock(ctx, p["id"], 9, t0 - timedelta(minutes=1))  # late, older event
    assert ctx.product(p["id"])["stockCount"] == 3
    stock(ctx, p["id"], 0, t0 + timedelta(minutes=1))
    assert ctx.client.get(ctx.url(f"/products/{p['id']}")).json()["inStock"] is False
    assert ctx.client.get(ctx.url("/products"), params={"inStock": False}).json()["items"][0]["id"] == p["id"]


def test_consumer_rejects_malformed_events_and_ignores_others(ctx: Ctx) -> None:
    handle = make_handler(ctx.app.state.catalog)
    with pytest.raises(ValueError, match="lacks"):
        ctx.run(handle(new_event("stock.changed", {"productId": "P"}, correlation_id="c")))
    with pytest.raises(ValueError, match="lacks"):
        ctx.run(handle(new_event("image.processed", {"productId": "P", "ok": True}, correlation_id="c")))
    with pytest.raises(ValueError, match="lacks"):
        ctx.run(handle(new_event("image.processed", {"ok": True}, correlation_id="c")))
    ctx.run(handle(new_event("stock.low", {"productId": "P", "available": 0, "threshold": 1}, correlation_id="c")))
