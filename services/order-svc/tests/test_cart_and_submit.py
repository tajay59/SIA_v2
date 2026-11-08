"""Cart (O1, O12, O13), submission with split (O2, O3, O14), visibility (O4)."""

from __future__ import annotations

import pytest

from .conftest import ADDRESS, CIMH_USER, OTHER, PEER, STAFF, USER, Ctx


def test_cart_is_created_empty_and_holds_snapshots(ctx: Ctx) -> None:
    r = ctx.client.get(ctx.url("/cart"), headers=USER)
    assert r.status_code == 200
    assert r.json()["lines"] == []
    assert r.json()["version"] == 1
    r = ctx.cart_add("MET1", 2)
    assert r.status_code == 200, r.text
    line = r.json()["lines"][0]
    assert line["qty"] == 2
    assert line["product"]["name"] == "Product MET1"
    assert line["available"] is True
    assert r.json()["hasPaidLines"]
    assert not r.json()["hasProbonoLines"]
    # Setting the same product again replaces the quantity.
    assert ctx.cart_add("MET1", 5).json()["lines"][0]["qty"] == 5
    assert len(ctx.client.get(ctx.url("/cart"), headers=USER).json()["lines"]) == 1


def test_one_cart_per_user(ctx: Ctx) -> None:
    ctx.cart_add("MET1")
    ctx.client.get(ctx.url("/cart"), headers=USER)
    assert ctx.run(ctx.db["orders"].count_documents({"customer": "USRUSER", "status": "CART"})) == 1


@pytest.mark.req("O13")
def test_probono_limit(ctx: Ctx) -> None:
    assert ctx.cart_add("PRO1", 3).status_code == 200
    r = ctx.cart_add("PRO1", 4)
    assert r.status_code == 422
    assert r.json()["code"] == "PROBONO_LIMIT_EXCEEDED"


def test_unavailable_and_unknown_products(ctx: Ctx) -> None:
    r = ctx.cart_add("OLD1")
    assert r.status_code == 422
    assert r.json()["code"] == "PRODUCT_UNAVAILABLE"
    assert ctx.cart_add("NOPE").status_code == 404


@pytest.mark.req("O1")
def test_cimh_accounts_cannot_request(ctx: Ctx) -> None:
    for r in (
        ctx.client.get(ctx.url("/cart"), headers=CIMH_USER),
        ctx.cart_add("MET1", who=CIMH_USER),
        ctx.client.post(ctx.url("/requests"), headers=CIMH_USER, json={"shipTo": ADDRESS}),
    ):
        assert r.status_code == 403
        assert r.json()["code"] == "CIMH_CANNOT_REQUEST"
    assert ctx.client.get(ctx.url("/cart"), headers=STAFF).status_code == 403


def test_remove_and_empty(ctx: Ctx) -> None:
    ctx.cart_add("MET1")
    ctx.cart_add("MET2")
    r = ctx.client.delete(ctx.url("/cart/lines/MET1"), headers=USER)
    assert [x["productId"] for x in r.json()["lines"]] == ["MET2"]
    assert ctx.client.delete(ctx.url("/cart"), headers=USER).status_code == 204
    assert ctx.client.get(ctx.url("/cart"), headers=USER).json()["lines"] == []


def test_cart_survives_catalog_outage(ctx: Ctx) -> None:
    ctx.cart_add("MET1")
    ctx.deps.down = True
    line = ctx.client.get(ctx.url("/cart"), headers=USER).json()["lines"][0]
    assert line["product"]["name"] == "Product MET1"
    assert "available" not in line


@pytest.mark.req("O14")
def test_mixed_cart_is_split_and_emptied(ctx: Ctx) -> None:
    ctx.cart_add("MET1", 2)
    ctx.cart_add("PRO1", 1)
    reqs = ctx.submit("USD", notes="Urgent")
    assert sorted(r["type"] for r in reqs) == ["PAID", "PROBONO"]
    paid = next(r for r in reqs if r["type"] == "PAID")
    probono = next(r for r in reqs if r["type"] == "PROBONO")
    assert paid["currency"] == "USD"
    assert probono["currency"] is None
    assert paid["splitFrom"] == probono["id"]
    assert probono["splitFrom"] == paid["id"]
    assert paid["status"] == "SUBMITTED"
    assert paid["customerName"] == "Una User"
    assert paid["organisationName"] == "Met Office"
    assert paid["billTo"] == ADDRESS
    assert paid["lines"][0]["product"]["name"] == "Product MET1"
    assert paid["lines"][0]["lineId"] == "L1"
    assert ctx.client.get(ctx.url("/cart"), headers=USER).json()["lines"] == []
    for r in reqs:
        (evt,) = ctx.events(r["id"], "order.submitted")
        assert evt["payload"]["splitFrom"] is not None
        assert evt["payload"]["organisationId"] == "ORGMET"


def test_submit_needs_currency_for_paid_lines_only(ctx: Ctx) -> None:
    ctx.cart_add("MET1")
    r = ctx.client.post(ctx.url("/requests"), headers=USER, json={"shipTo": ADDRESS})
    assert r.status_code == 422
    assert r.json()["code"] == "CURRENCY_REQUIRED"
    ctx.client.delete(ctx.url("/cart"), headers=USER)
    ctx.cart_add("PRO1")
    (req,) = ctx.submit(currency=None)
    assert req["type"] == "PROBONO"


def test_submit_rechecks_the_catalogue(ctx: Ctx) -> None:
    ctx.cart_add("MET1")
    ctx.deps.catalog["MET1"]["active"] = False
    r = ctx.client.post(ctx.url("/requests"), headers=USER, json={"shipTo": ADDRESS, "currency": "BBD"})
    assert r.status_code == 422
    assert r.json()["code"] == "PRODUCT_UNAVAILABLE"
    assert ctx.client.get(ctx.url("/cart"), headers=USER).json()["lines"]  # cart kept


def test_empty_cart_cannot_be_submitted(ctx: Ctx) -> None:
    r = ctx.client.post(ctx.url("/requests"), headers=USER, json={"shipTo": ADDRESS, "currency": "BBD"})
    assert r.status_code == 422


def test_submit_is_idempotent_with_a_key(ctx: Ctx) -> None:
    ctx.cart_add("MET1")
    h = {**USER, "Idempotency-Key": "k-1"}
    body = {"shipTo": ADDRESS, "currency": "BBD"}
    a = ctx.client.post(ctx.url("/requests"), headers=h, json=body)
    b = ctx.client.post(ctx.url("/requests"), headers=h, json=body)
    assert a.status_code == b.status_code == 201
    assert a.json()["requests"][0]["id"] == b.json()["requests"][0]["id"]
    assert ctx.run(ctx.db["orders"].count_documents({"status": "SUBMITTED"})) == 1


@pytest.mark.req("O4")
def test_visibility_same_org_reads_others_do_not(ctx: Ctx) -> None:
    rid = ctx.paid_request()
    assert ctx.client.get(ctx.url(f"/requests/{rid}"), headers=PEER).status_code == 200
    assert ctx.client.get(ctx.url(f"/requests/{rid}"), headers=OTHER).status_code == 404
    # Same organisation can see but not act; others don't learn it exists.
    ctx.ok(rid, "start-quoting")
    v = ctx.get(rid)["version"]
    r = ctx.client.post(
        ctx.url(f"/requests/{rid}/cancel"), headers={**PEER, "If-Match": str(v)}, json={"reason": "not needed"}
    )
    assert r.status_code == 403
    r = ctx.client.post(
        ctx.url(f"/requests/{rid}/cancel"), headers={**OTHER, "If-Match": str(v)}, json={"reason": "not needed"}
    )
    assert r.status_code == 404


def test_listing_scopes_and_filters(ctx: Ctx) -> None:
    mine = ctx.paid_request()
    ctx.cart_add("MET1", who=PEER)
    peer = ctx.submit(who=PEER)[0]["id"]
    ctx.cart_add("MET1", who=OTHER)
    ctx.submit(who=OTHER)

    def ids(params: dict[str, str], who: dict[str, str]) -> list[str]:
        r = ctx.client.get(ctx.url("/requests"), headers=who, params=params)
        assert r.status_code == 200, r.text
        return [x["id"] for x in r.json()["items"]]

    assert ids({}, USER) == [mine]
    assert set(ids({"scope": "organisation"}, USER)) == {mine, peer}
    assert ctx.client.get(ctx.url("/requests"), headers=USER, params={"scope": "all"}).status_code == 403
    assert len(ids({"scope": "all"}, STAFF)) == 3
    assert ids({"q": mine[:12]}, STAFF) == [mine]
    assert ids({"q": "una"}, STAFF) == [mine]
    assert ids({"status": "QUOTED"}, STAFF) == []
    assert len(ids({"status": "SUBMITTED,QUOTED", "type": "PAID", "sort": "waiting"}, STAFF)) == 3
    assert ctx.client.get(ctx.url("/requests"), headers=STAFF, params={"status": "NOPE"}).status_code == 422


def test_listing_pages(ctx: Ctx) -> None:
    for _ in range(3):
        ctx.paid_request()
    r1 = ctx.client.get(ctx.url("/requests"), headers=STAFF, params={"limit": 2}).json()
    assert len(r1["items"]) == 2
    assert r1["nextCursor"]
    r2 = ctx.client.get(ctx.url("/requests"), headers=STAFF, params={"limit": 2, "cursor": r1["nextCursor"]}).json()
    assert len(r2["items"]) == 1
    assert r2["nextCursor"] is None
    assert not {x["id"] for x in r1["items"]} & {x["id"] for x in r2["items"]}


def test_status_filter_rejects_empty_items(ctx: Ctx) -> None:
    for value in (",", "SUBMITTED,", ""):
        assert ctx.client.get(ctx.url("/requests"), headers=STAFF, params={"status": value}).status_code == 422
