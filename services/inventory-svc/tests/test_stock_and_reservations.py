"""PRD I8-I11: stock levels and low-stock events, movement history, availability and reservations."""

from __future__ import annotations

import asyncio
import random
from typing import Any

import pytest

from cimh_common.outbox import new_event
from inventory_svc.consumer import make_handler

from .conftest import CATALOG, ORDER, STAFF, Ctx, ts

P1 = "MET11111111111111111111111111111111"
P2 = "RAD22222222222222222222222222222222"


def _stock(ctx: Ctx, pid: str, n: int, shelf: str) -> list[str]:
    units = ctx.labels(pid, n)
    for u in units:
        assert ctx.scan("stow", {"unit": u, "shelf": shelf}).status_code == 200
    return units


@pytest.mark.req("I8")
def test_product_stock_by_location_and_low_stock(ctx: Ctx) -> None:
    ctx.product(P1, "Anemometer", threshold=2)
    ctx.product(P2, "Magnetron", threshold=0)
    s1, s2 = ctx.shelves(2)
    units = _stock(ctx, P1, 3, s1) + _stock(ctx, P1, 1, s2)
    _stock(ctx, P2, 1, s1)

    st = ctx.client.get(ctx.url(f"/products/{P1}/stock"), headers=STAFF).json()
    assert (st["available"], st["reserved"], st["picked"], st["threshold"]) == (4, 0, 0, 2)
    assert st["productName"] == "Anemometer"
    assert sorted((b["shelfNumber"], b["count"]) for b in st["byLocation"]) == [(1, 3), (2, 1)]
    assert {b["locationName"] for b in st["byLocation"]} == {"Store A"}
    assert ctx.client.get(ctx.url("/stock/low"), headers=STAFF).json()["items"] == []

    ctx.scan("pick", {"unit": units[0], "reason": "x"})
    assert ctx.events(P1, "stock.low") == []  # 3 > 2
    ctx.scan("pick", {"unit": units[1], "reason": "x"})
    low = ctx.events(P1, "stock.low")
    assert [e["payload"] for e in low] == [{"productId": P1, "available": 2, "threshold": 2}]
    ctx.scan("pick", {"unit": units[2], "reason": "x"})
    assert len(ctx.events(P1, "stock.low")) == 1  # only when it crosses, not on every pick
    items = ctx.client.get(ctx.url("/stock/low"), headers=STAFF).json()["items"]
    assert [(i["productId"], i["available"]) for i in items] == [(P1, 1)]  # threshold 0 = no alert for P2

    ctx.scan("stow", {"unit": units[0], "shelf": s1})
    ctx.scan("stow", {"unit": units[1], "shelf": s1})
    assert ctx.client.get(ctx.url("/stock/low"), headers=STAFF).json()["items"] == []
    unknown = ctx.client.get(ctx.url("/products/NOPE/stock"), headers=STAFF).json()
    assert unknown["available"] == 0
    assert unknown["byLocation"] == []


@pytest.mark.req("I10")
def test_history_filters_and_paging(ctx: Ctx) -> None:
    ctx.product(P1)
    s1, s2 = ctx.shelves(2)
    units = _stock(ctx, P1, 3, s1)
    ctx.scan("relocate", {"unit": units[0], "toShelf": s2})
    ctx.scan("pick", {"unit": units[1], "reason": "x"})
    rows = ctx.client.get(ctx.url("/history"), headers=STAFF).json()["items"]
    assert [r["operation"] for r in rows[:2]] == ["pick", "relocate"]  # newest first
    one = ctx.client.get(ctx.url("/history"), params={"unit": units[0]}, headers=STAFF).json()["items"]
    assert [r["operation"] for r in one] == ["relocate", "stow"]
    assert one[0]["from"]["shelf"] == s1
    stows = ctx.client.get(ctx.url("/history"), params={"operation": "stow", "user": "USRSTAFF"}, headers=STAFF)
    assert len(stows.json()["items"]) == 3
    seen: list[tuple[str, str]] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = ctx.client.get(ctx.url("/history"), params=params, headers=STAFF).json()
        seen += [(r["unit"], r["operation"]) for r in page["items"]]
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert len(seen) == 5
    assert len(set(seen)) == 5
    future = ctx.client.get(ctx.url("/history"), params={"from": "2999-01-01T00:00:00Z"}, headers=STAFF).json()
    assert future["items"] == []
    assert ctx.client.get(ctx.url("/history"), params={"cursor": "bad"}, headers=STAFF).status_code == 422


def test_legacy_history_rows_are_shown_with_v2_operations(ctx: Ctx) -> None:
    ctx.run(
        ctx.db["history"].insert_one({"id": "U1", "operation": "orderpick", "user": "ACC1", "date": ts(), "reason": ""})
    )
    row = ctx.client.get(ctx.url("/history"), headers=STAFF).json()["items"][0]
    assert row["operation"] == "pick"
    assert row["reason"] is None
    assert row["date"].endswith("Z")


@pytest.mark.req("I8")
def test_counts_reconcile_with_units_after_random_scans(ctx: Ctx) -> None:
    """Exit criterion P4: stock counts reconcile with units and history."""
    ctx.product(P1)
    shelves = ctx.shelves(3)
    units = ctx.labels(P1, 8)
    rng = random.Random(4)
    for _ in range(80):
        u = rng.choice(units)
        op = rng.choice(["stow", "pick", "relocate", "assign", "unassign"])
        body = {"unit": u}
        if op == "stow":
            body["shelf"] = rng.choice(shelves)
        elif op == "pick":
            body["reason"] = "audit"
        elif op == "relocate":
            body["toShelf"] = rng.choice(shelves)
        elif op == "assign":
            body["accountId"] = rng.choice(["USRA", "USRB"])
        assert ctx.scan(op, body).status_code in (200, 409)

    docs = ctx.run(ctx.db["storage"].find({"product": P1}).to_list())
    expected = {
        "available": sum(1 for d in docs if d.get("stowed") and not d.get("picked") and not d.get("reservedFor")),
        "picked": sum(1 for d in docs if d.get("picked")),
        "assigned": sum(1 for d in docs if d.get("assignedTo")),
    }
    stock = ctx.stock_doc(P1)
    assert {k: stock[k] for k in expected} == expected
    # Replaying history from scratch gives the same final state per unit.
    for d in docs:
        ops = [h["operation"] for h in ctx.history(d["barcode"])]
        state = {"stowed": False, "picked": False, "assigned": False}
        for op in ops:
            if op == "stow":
                state |= {"stowed": True, "picked": False}
            elif op == "pick":
                state |= {"stowed": False, "picked": True}
            elif op == "assign":
                state |= {"stowed": False, "assigned": True}
            elif op == "unassign":
                state["assigned"] = False
        assert state == {
            "stowed": bool(d.get("stowed")),
            "picked": bool(d.get("picked")),
            "assigned": bool(d.get("assignedTo")),
        }
    changed = ctx.events(P1, "stock.changed")[-1]["payload"]
    assert changed["available"] == expected["available"]


@pytest.mark.req("I11")
def test_availability(ctx: Ctx) -> None:
    ctx.product(P1)
    _stock(ctx, P1, 2, ctx.shelves(1)[0])
    lines = [{"lineId": "L1", "productId": P1, "qty": 2}, {"lineId": "L2", "productId": P2, "qty": 1}]
    r = ctx.client.post(ctx.url("/internal/availability"), headers=ORDER, json={"lines": lines})
    assert r.json()["lines"] == [
        {"lineId": "L1", "available": 2, "fullQuantity": True},
        {"lineId": "L2", "available": 0, "fullQuantity": False},
    ]
    r = ctx.client.post(ctx.url("/internal/availability"), headers=CATALOG, json={"lines": lines})
    assert r.status_code == 403  # order-svc only


@pytest.mark.req("I9")
def test_reserve_all_or_nothing_then_release(ctx: Ctx) -> None:
    ctx.product(P1)
    ctx.product(P2)
    shelf = ctx.shelves(1)[0]
    _stock(ctx, P1, 3, shelf)
    _stock(ctx, P2, 1, shelf)
    url = ctx.url("/internal/reservations")

    short = {
        "orderId": "ORD1",
        "lines": [{"lineId": "L1", "productId": P1, "qty": 2}, {"lineId": "L2", "productId": P2, "qty": 2}],
    }
    r = ctx.client.post(url, headers=ORDER, json=short)
    assert r.status_code == 409
    assert r.json()["code"] == "RESERVATION_FAILED"
    assert ctx.run(ctx.db["storage"].count_documents({"reservedFor": "ORD1"})) == 0  # nothing kept
    failed = ctx.events(P1, "stock.reservation_failed")[0]["payload"]
    assert failed == {"orderId": "ORD1", "lines": [{"lineId": "L2", "requested": 2, "available": 1}]}

    ok = {
        "orderId": "ORD2",
        "lines": [{"lineId": "L1", "productId": P1, "qty": 2}, {"lineId": "L2", "productId": P2, "qty": 1}],
    }
    r = ctx.client.post(url, headers=ORDER, json=ok)
    assert r.status_code == 200, r.text
    lines = r.json()["lines"]
    assert [len(x["units"]) for x in lines] == [2, 1]
    assert ctx.client.post(url, headers=ORDER, json=ok).json()["lines"] == lines  # repeat = same units
    assert (ctx.stock_doc(P1)["available"], ctx.stock_doc(P1)["reserved"]) == (1, 2)
    assert ctx.events(P1, "stock.reserved")[0]["payload"] == {"orderId": "ORD2", "lines": lines}
    assert [h["operation"] for h in ctx.history(lines[0]["units"][0])] == ["stow", "reserve"]

    # Pick one reserved unit for the request, then cancel: only the unpicked ones go back.
    assert ctx.scan("pick", {"unit": lines[0]["units"][0], "orderId": "ORD2"}).status_code == 200
    assert ctx.client.delete(ctx.url("/internal/reservations/ORD2"), headers=ORDER).status_code == 204
    released = ctx.events(P1, "stock.released")[0]["payload"]
    assert sorted(released["units"]) == sorted([lines[0]["units"][1], lines[1]["units"][0]])
    assert (ctx.stock_doc(P1)["available"], ctx.stock_doc(P1)["reserved"]) == (2, 0)
    assert ctx.client.delete(ctx.url("/internal/reservations/ORD2"), headers=ORDER).status_code == 204  # idempotent
    assert len(ctx.events(P1, "stock.released")) == 1
    assert ctx.client.delete(ctx.url("/internal/reservations/ORD2"), headers=STAFF).status_code == 403


def test_catalog_events_keep_the_stock_copy(ctx: Ctx) -> None:
    handle = make_handler(ctx.client.app.state.inventory)  # type: ignore[attr-defined]

    def upsert(at: int, **payload: Any) -> None:
        evt = new_event("product.updated", {"productId": P1, "name": "Gauge", "type": "MET", "sellable": True,
                                             "probono": False, "active": True, "threshold": 0, **payload},
                        correlation_id="c")  # fmt: skip
        asyncio.run(handle(evt.envelope().model_copy(update={"occurredAt": ts(at)})))

    upsert(1, threshold=5)
    doc = ctx.stock_doc(P1)
    assert (doc["productName"], doc["threshold"], doc["available"], doc["low"]) == ("Gauge", 5, 0, True)
    assert len(ctx.events(P1, "stock.low")) == 1  # threshold raised above what is on the shelves
    upsert(0, name="Old name", threshold=1)  # older event arrives late: ignored
    assert ctx.stock_doc(P1)["productName"] == "Gauge"
    upsert(2, name="New name", threshold=5)
    assert ctx.stock_doc(P1)["productName"] == "New name"
    assert len(ctx.events(P1, "stock.low")) == 1
    asyncio.run(handle(new_event("product.deleted", {"productId": P1}, correlation_id="c").envelope()))
    assert ctx.stock_doc(P1)["active"] is False
    assert ctx.stock_doc(P1)["low"] is False
    asyncio.run(handle(new_event("stock.changed", {"productId": P1}, correlation_id="c").envelope()))  # ignored
    with pytest.raises(ValueError, match="lacks productId/threshold"):
        asyncio.run(handle(new_event("product.created", {"productId": P1}, correlation_id="c").envelope()))
    with pytest.raises(ValueError, match="lacks productId"):
        asyncio.run(handle(new_event("product.deleted", {}, correlation_id="c").envelope()))


@pytest.mark.req("O6")
def test_order_events_reserve_and_release(ctx: Ctx) -> None:
    """order.accepted reserves CIMH-chosen lines only; Pro Bono approval reserves all; cancellation releases."""
    ctx.product(P1)
    ctx.product(P2)
    shelf = ctx.shelves(1)[0]
    _stock(ctx, P1, 3, shelf)
    _stock(ctx, P2, 1, shelf)
    handle = make_handler(ctx.client.app.state.inventory)  # type: ignore[attr-defined]

    def send(etype: str, payload: dict[str, Any]) -> None:
        asyncio.run(handle(new_event(etype, payload, correlation_id="c", actor_id="USRUSER").envelope()))

    lines = [{"lineId": "L1", "productId": P1, "qty": 2, "choice": "CIMH"},
             {"lineId": "L2", "productId": P2, "qty": 5, "choice": "SUPPLIER"}]  # fmt: skip
    send("order.accepted", {"orderId": "ORDA", "customer": "USRUSER", "quoteVersion": 1, "lines": lines})
    assert ctx.run(ctx.db["storage"].count_documents({"reservedFor": "ORDA"})) == 2  # supplier line untouched
    send("order.agreement_rejected", {"orderId": "ORDA", "from": "ACCEPTED", "to": "AWAITING_AGREEMENT"})
    assert ctx.run(ctx.db["storage"].count_documents({"reservedFor": "ORDA"})) == 0
    # A shortfall is reported, not raised (the consumer must not DLQ a business outcome).
    send("order.probono_approved", {"orderId": "ORDB", "lines": [{"lineId": "L1", "productId": P2, "qty": 2}]})
    assert ctx.events(P2, "stock.reservation_failed")[0]["payload"]["orderId"] == "ORDB"
    send("order.probono_approved", {"orderId": "ORDC", "lines": [{"lineId": "L1", "productId": P2, "qty": 1}]})
    assert ctx.run(ctx.db["storage"].count_documents({"reservedFor": "ORDC"})) == 1
    send("order.cancelled", {"orderId": "ORDC", "customer": "USRUSER", "reason": "x", "auto": False})
    assert ctx.run(ctx.db["storage"].count_documents({"reservedFor": "ORDC"})) == 0
    send("order.accepted", {"orderId": "ORDD", "customer": "U", "quoteVersion": 1, "lines": [lines[1]]})  # no-op
    with pytest.raises(ValueError, match="lacks orderId"):
        send("order.cancelled", {"customer": "U"})


def test_internal_pick_for_order_svc(ctx: Ctx) -> None:
    ctx.product(P1)
    shelf = ctx.shelves(1)[0]
    _stock(ctx, P1, 2, shelf)
    held = ctx.client.post(
        ctx.url("/internal/reservations"), headers=ORDER,
        json={"orderId": "ORDP", "lines": [{"lineId": "L1", "productId": P1, "qty": 1}]},
    ).json()["lines"][0]["units"]  # fmt: skip
    free = next(d["barcode"] for d in ctx.run(ctx.db["storage"].find({}).to_list()) if d["barcode"] not in held)

    def pick(unit: str, key: str, who: dict[str, str] = ORDER) -> Any:
        return ctx.client.post(ctx.url("/internal/picks"), headers={**who, "Idempotency-Key": key},
                               json={"unit": unit, "orderId": "ORDP", "pickedBy": "USRSTAFF"})  # fmt: skip

    assert pick(free, "k1").json()["code"] == "UNIT_NOT_RESERVED_FOR_ORDER"
    r = pick(held[0], "k2")
    assert r.status_code == 200
    assert r.json()["pickedBy"] == "USRSTAFF"
    assert r.json()["orderId"] == "ORDP"
    assert pick(held[0], "k2").status_code == 200  # replay
    assert ctx.history(held[0])[-1]["user"] == "USRSTAFF"
    assert pick(held[0], "k3", STAFF).status_code == 403
