"""PRD I2-I6: labels, stow, pick, relocate, assign/unassign; every scan is idempotent (TR-API-6)."""

from __future__ import annotations

import pytest

from .conftest import STAFF, STAFF2, Ctx

PID = "MET0123456789abcdef0123456789abcdef"


@pytest.fixture
def stocked(ctx: Ctx) -> tuple[Ctx, list[str], list[str]]:
    ctx.product(PID, "Tipping bucket rain gauge")
    return ctx, ctx.shelves(2), ctx.labels(PID, 3)


@pytest.mark.req("I2")
def test_labels_create_unplaced_units(ctx: Ctx) -> None:
    ctx.product(PID)
    r = ctx.client.post(
        ctx.url("/labels"), headers=STAFF, json={"productId": PID, "quantity": 2, "serials": ["A1", "A2"]}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["fileId"] is None
    assert len(set(body["barcodes"])) == 2
    assert all(b.startswith(PID + "_") and len(b) == len(PID) + 9 for b in body["barcodes"])  # legacy <pid>_<8 hex>
    unit = ctx.client.get(ctx.url(f"/units/{body['barcodes'][0]}"), headers=STAFF).json()
    assert unit["serial"] == "A1"
    assert unit["stowed"] is False
    assert unit["productName"] == "Rain gauge"
    r = ctx.client.post(ctx.url("/labels"), headers=STAFF, json={"productId": PID, "quantity": 2, "serials": ["A1"]})
    assert r.status_code == 422
    assert (
        ctx.client.post(ctx.url("/labels"), headers=STAFF, json={"productId": "NOPE", "quantity": 1}).status_code == 404
    )
    r = ctx.client.get(ctx.url("/units/NOPE"), headers=STAFF)
    assert r.status_code == 404
    assert r.json()["code"] == "UNIT_NOT_FOUND"


@pytest.mark.req("I3")
def test_stow_records_place_history_counts_and_events(stocked: tuple[Ctx, list[str], list[str]]) -> None:
    ctx, shelves, units = stocked
    r = ctx.scan("stow", {"unit": units[0], "shelf": shelves[0]})
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["stowed"]
    assert u["shelf"] == shelves[0]
    assert u["shelfNumber"] == 1
    assert u["siteName"] == "Husbands"
    assert u["locationName"] == "Store A"
    assert u["stowBy"] == "USRSTAFF"
    assert [h["operation"] for h in ctx.history(units[0])] == ["stow"]
    assert ctx.stock_doc(PID)["available"] == 1
    types = [e["type"] for e in ctx.events(PID)]
    assert types == ["unit.stowed", "stock.changed"]
    assert ctx.events(PID, "stock.changed")[0]["payload"] == {"productId": PID, "available": 1, "reserved": 0}

    again = ctx.scan("stow", {"unit": units[0], "shelf": shelves[0]})  # same shelf, new scan: nothing changes
    assert again.status_code == 200
    assert len(ctx.history(units[0])) == 1
    assert len(ctx.events(PID)) == 2
    r = ctx.scan("stow", {"unit": units[0], "shelf": shelves[1]})
    assert r.status_code == 409
    assert r.json()["code"] == "UNIT_ALREADY_STOWED"
    r = ctx.scan("stow", {"unit": units[1], "shelf": "SHELnope"})
    assert r.status_code == 404
    assert r.json()["code"] == "SHELF_NOT_FOUND"
    r = ctx.scan("stow", {"unit": "NOT_A_UNIT", "shelf": shelves[0]})
    assert r.status_code == 404
    assert r.json()["code"] == "UNIT_NOT_FOUND"


def test_legacy_label_without_record_is_created_on_first_stow(stocked: tuple[Ctx, list[str], list[str]]) -> None:
    ctx, shelves, _ = stocked
    r = ctx.scan("stow", {"unit": f"{PID}_9f8e7d6c", "shelf": shelves[0]})
    assert r.status_code == 200, r.text
    assert r.json()["product"] == PID
    r = ctx.scan("stow", {"unit": "UNKNOWNPRODUCT_9f8e7d6c", "shelf": shelves[0]})
    assert r.status_code == 404
    assert r.json()["code"] == "UNIT_NOT_FOUND"


@pytest.mark.req("I5")
def test_pick_rules(stocked: tuple[Ctx, list[str], list[str]]) -> None:
    ctx, shelves, units = stocked
    r = ctx.scan("pick", {"unit": units[0], "reason": "repair"})
    assert r.status_code == 409
    assert r.json()["code"] == "UNIT_NOT_STOWED"
    for u in units:
        ctx.scan("stow", {"unit": u, "shelf": shelves[0]})
    assert ctx.scan("pick", {"unit": units[0]}).status_code == 422  # reason or orderId
    assert ctx.scan("pick", {"unit": units[0], "reason": "x", "orderId": "ORD1"}).status_code == 422  # not both

    r = ctx.scan("pick", {"unit": units[0], "reason": "Used for station repair"})
    assert r.status_code == 200, r.text
    assert r.json()["picked"]
    assert not r.json()["stowed"]
    assert r.json()["pickedReason"] == "Used for station repair"
    r = ctx.scan("pick", {"unit": units[0], "reason": "again"})
    assert r.status_code == 409
    assert r.json()["code"] == "UNIT_ALREADY_PICKED"
    assert ctx.stock_doc(PID)["available"] == 2
    assert ctx.stock_doc(PID)["picked"] == 1
    assert ctx.events(PID, "unit.picked")[0]["payload"]["reason"] == "Used for station repair"
    # A unit picked with a reason can go back on a shelf.
    assert ctx.scan("stow", {"unit": units[0], "shelf": shelves[1]}).status_code == 200

    # Reserved units: only for their request.
    ctx.run(ctx.db["storage"].update_one({"barcode": units[1]}, {"$set": {"reservedFor": "ORD1"}}))
    r = ctx.scan("pick", {"unit": units[1], "reason": "x"})
    assert r.status_code == 409
    assert r.json()["code"] == "UNIT_RESERVED"
    r = ctx.scan("pick", {"unit": units[1], "orderId": "ORD2"})
    assert r.status_code == 409
    assert r.json()["code"] == "UNIT_NOT_RESERVED_FOR_ORDER"
    r = ctx.scan("pick", {"unit": units[1], "orderId": "ORD1"})
    assert r.status_code == 200
    assert r.json()["orderId"] == "ORD1"
    r = ctx.scan("stow", {"unit": units[1], "shelf": shelves[0]})  # picked for a request: never back on a shelf
    assert r.status_code == 409
    assert r.json()["code"] == "UNIT_ALREADY_PICKED"


@pytest.mark.req("I6")
def test_relocate(stocked: tuple[Ctx, list[str], list[str]]) -> None:
    ctx, shelves, units = stocked
    r = ctx.scan("relocate", {"unit": units[0], "toShelf": shelves[1]})
    assert r.status_code == 409
    assert r.json()["code"] == "UNIT_NOT_STOWED"
    ctx.scan("stow", {"unit": units[0], "shelf": shelves[0]})
    events = len(ctx.events(PID))
    r = ctx.scan("relocate", {"unit": units[0], "toShelf": shelves[1]})
    assert r.status_code == 200
    assert r.json()["shelfNumber"] == 2
    moved = ctx.history(units[0])[-1]
    assert moved["operation"] == "relocate"
    assert moved["from"]["shelf"] == shelves[0]
    assert moved["shelf"] == shelves[1]
    assert len(ctx.events(PID)) == events  # counts unchanged: nothing to publish
    assert ctx.scan("relocate", {"unit": units[0], "toShelf": shelves[1]}).status_code == 200  # already there
    assert len(ctx.history(units[0])) == 2


@pytest.mark.req("I4")
def test_assign_and_unassign(stocked: tuple[Ctx, list[str], list[str]]) -> None:
    ctx, shelves, units = stocked
    ctx.scan("stow", {"unit": units[0], "shelf": shelves[0]})
    r = ctx.scan("assign", {"unit": units[0], "accountId": "USRBOB"})
    assert r.status_code == 200
    assert r.json()["assignedTo"] == "USRBOB"
    assert not r.json()["stowed"]
    assert ctx.stock_doc(PID)["available"] == 0
    assert ctx.stock_doc(PID)["assigned"] == 1
    assert ctx.history(units[0])[-1]["accountId"] == "USRBOB"
    assert ctx.history(units[0])[-1]["from"]["shelf"] == shelves[0]
    assert ctx.scan("assign", {"unit": units[0], "accountId": "USRBOB"}).status_code == 200  # no-op
    for op, body in (
        ("assign", {"unit": units[0], "accountId": "USRAMY"}),
        ("stow", {"unit": units[0], "shelf": shelves[0]}),
        ("pick", {"unit": units[0], "reason": "x"}),
        ("relocate", {"unit": units[0], "toShelf": shelves[1]}),
    ):
        r = ctx.scan(op, body)
        assert r.status_code == 409, op
        assert r.json()["code"] == "UNIT_ASSIGNED", op

    who = ctx.client.get(ctx.url("/assignments"), params={"accountId": "USRBOB"}, headers=STAFF).json()
    assert [u["barcode"] for u in who["items"]] == [units[0]]
    ctx.scan("assign", {"unit": units[1], "accountId": "USRAMY"})  # never stowed: can still be issued
    every = ctx.client.get(ctx.url("/assignments"), headers=STAFF).json()["items"]
    assert [u["assignedTo"] for u in every] == ["USRAMY", "USRBOB"]  # grouped by person

    r = ctx.scan("unassign", {"unit": units[0]})
    assert r.status_code == 200
    assert r.json()["assignedTo"] is None
    assert not r.json()["stowed"]
    r = ctx.scan("unassign", {"unit": units[0]})
    assert r.status_code == 409
    assert r.json()["code"] == "UNIT_NOT_ASSIGNED"
    assert ctx.scan("stow", {"unit": units[0], "shelf": shelves[1]}).status_code == 200  # returned, then stowed
    assert [h["operation"] for h in ctx.history(units[0])] == ["stow", "assign", "unassign", "stow"]


@pytest.mark.req("TR-API-6")
def test_scans_are_idempotent(stocked: tuple[Ctx, list[str], list[str]]) -> None:
    ctx, shelves, units = stocked
    first = ctx.scan("stow", {"unit": units[0], "shelf": shelves[0]}, key="K1")
    ctx.scan("pick", {"unit": units[0], "reason": "x"})
    replay = ctx.scan("stow", {"unit": units[0], "shelf": shelves[0]}, key="K1")  # offline queue resends
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert [h["operation"] for h in ctx.history(units[0])] == ["stow", "pick"]

    r = ctx.scan("stow", {"unit": units[1], "shelf": shelves[0]}, key="K1")
    assert r.status_code == 422
    assert r.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    # Another person may use the same key: keys are scoped per caller.
    assert ctx.scan("stow", {"unit": units[1], "shelf": shelves[0]}, headers=STAFF2, key="K1").status_code == 200

    bad = ctx.scan("pick", {"unit": units[2], "reason": "x"}, key="K2")
    assert bad.status_code == 409
    ctx.scan("stow", {"unit": units[2], "shelf": shelves[0]})
    again = ctx.scan("pick", {"unit": units[2], "reason": "x"}, key="K2")
    assert again.status_code == 409
    assert again.json()["code"] == bad.json()["code"]

    no_key = ctx.client.post(ctx.url("/stow"), headers=STAFF, json={"unit": units[2], "shelf": shelves[0]})
    assert no_key.status_code == 422


@pytest.mark.req("I7")
def test_shelf_lookup_is_paged(stocked: tuple[Ctx, list[str], list[str]]) -> None:
    ctx, shelves, units = stocked
    for u in units:
        ctx.scan("stow", {"unit": u, "shelf": shelves[0]})
    seen: list[str] = []
    cursor = None
    while True:
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = ctx.client.get(ctx.url(f"/shelves/{shelves[0]}/units"), params=params, headers=STAFF).json()
        seen += [u["barcode"] for u in page["items"]]
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert seen == sorted(units)
    assert ctx.client.get(ctx.url(f"/shelves/{shelves[1]}/units"), headers=STAFF).json()["items"] == []
    assert ctx.client.get(ctx.url("/shelves/SHELnope/units"), headers=STAFF).status_code == 404
