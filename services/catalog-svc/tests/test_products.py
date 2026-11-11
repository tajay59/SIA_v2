"""Products (PRD C1-C5, BSD §5.5-5.6): views by role, Pro Bono rules, versioned edits, soft delete, events."""

from __future__ import annotations

import re

import pytest

from catalog_svc.store import PUBLIC_FIELDS

from .conftest import ADMIN, STAFF, USER, Ctx, check_event

STAFF_ONLY = {"cost", "sn", "sn1", "threshold", "keywords", "sellable", "active", "stockCount", "version", "number"}


@pytest.mark.req("C4")
def test_staff_creates_a_product_with_a_legacy_style_id_and_an_event(ctx: Ctx) -> None:
    p = ctx.create()
    assert re.fullmatch(r"MET[0-9a-f]{32}", p["id"])
    assert p["number"] == 1
    assert p["cost"] == "1250.00"
    assert p["keywords"] == ["rain", "gauge"]
    assert p["version"] == 1
    doc = ctx.product(p["id"])
    assert [e["type"] for e in doc["outbox"]] == ["product.created"]
    check_event(doc["outbox"][0])
    assert ctx.create(name="Second")["number"] == 2


def test_supplied_id_is_kept_and_must_be_unique(ctx: Ctx) -> None:
    ctx.create(id="BARCODE-123456")
    r = ctx.client.post(
        ctx.url("/products"),
        headers=STAFF,
        json={"id": "BARCODE-123456", "name": "X", "type": "MET", "department": "D", "sellable": True,
              "probono": False, "threshold": 0},
    )  # fmt: skip
    assert r.status_code == 409
    assert r.json()["code"] == "PRODUCT_EXISTS"


@pytest.mark.req("C5")
def test_pro_bono_rules(ctx: Ctx) -> None:
    base = {"name": "Kit", "type": "PRO", "department": "D", "threshold": 0}
    r = ctx.client.post(ctx.url("/products"), headers=STAFF, json={**base, "sellable": False, "probono": True})
    assert r.status_code == 422
    r = ctx.client.post(
        ctx.url("/products"),
        headers=STAFF,
        json={**base, "sellable": True, "probono": False, "probonoMaxPerRequest": 2},
    )
    assert r.status_code == 422
    r = ctx.client.post(ctx.url("/products"), headers=STAFF, json={**base, "sellable": True})
    assert r.status_code == 422  # probono must be given explicitly
    p = ctx.create(**base, sellable=True, probono=True, probonoMaxPerRequest=2)
    assert p["probono"] is True
    assert p["probonoMaxPerRequest"] == 2


def test_department_and_project_must_exist_once_lists_are_set(ctx: Ctx) -> None:
    ctx.client.put(ctx.url("/reference/departments"), headers=ADMIN, json={"values": ["Meteorology"]})
    r = ctx.client.post(
        ctx.url("/products"),
        headers=STAFF,
        json={"name": "X", "type": "MET", "department": "Other", "sellable": True, "probono": False, "threshold": 0},
    )
    assert r.status_code == 422
    assert r.json()["errors"][0]["field"] == "department"
    r = ctx.client.post(
        ctx.url("/products"),
        headers=STAFF,
        json={"name": "X", "type": "PRO", "department": "Meteorology", "project": "nope", "sellable": True,
              "probono": False, "threshold": 0},
    )  # fmt: skip
    assert r.json()["errors"][0]["field"] == "project"
    ctx.client.post(ctx.url("/reference/projects"), headers=ADMIN, json={"code": "CREWS", "name": "CREWS"})
    assert ctx.create(type="PRO", department="Meteorology", project="CREWS")["project"] == "crews"


@pytest.mark.req("C7")
@pytest.mark.parametrize("who", [None, USER], ids=["anonymous", "customer"])
def test_customers_only_ever_get_public_fields(ctx: Ctx, who: dict[str, str] | None) -> None:
    p = ctx.create()
    ctx.create(name="Hidden", sellable=False)
    gone = ctx.create(name="Gone")
    ctx.client.delete(ctx.url(f"/products/{gone['id']}"), headers={**STAFF, "If-Match": "1"})
    headers = who or {}

    listing = ctx.client.get(ctx.url("/products"), headers=headers).json()["items"]
    assert [i["name"] for i in listing] == ["Rain gauge"]
    detail = ctx.client.get(ctx.url(f"/products/{p['id']}"), headers=headers)
    for item in (listing[0], detail.json()):
        assert set(item) == set(PUBLIC_FIELDS)  # snapshot: nothing more, ever
        assert not STAFF_ONLY & set(item)
    assert "ETag" not in detail.headers  # no version for customers
    hidden = ctx.client.get(ctx.url("/products"), headers=headers, params={"includeInactive": True}).json()
    assert len(hidden["items"]) == 1


def test_staff_see_everything_including_inactive_on_request(ctx: Ctx) -> None:
    ctx.create()
    ctx.create(name="Hidden", sellable=False)
    gone = ctx.create(name="Gone")
    ctx.client.delete(ctx.url(f"/products/{gone['id']}"), headers={**STAFF, "If-Match": "1"})
    names = [i["name"] for i in ctx.client.get(ctx.url("/products"), headers=STAFF).json()["items"]]
    assert names == ["Hidden", "Rain gauge"]
    r = ctx.client.get(ctx.url("/products"), headers=STAFF, params={"includeInactive": True})
    assert [i["name"] for i in r.json()["items"]] == ["Gone", "Hidden", "Rain gauge"]
    r = ctx.client.get(ctx.url("/products"), headers=STAFF, params={"sellable": False})
    assert [i["name"] for i in r.json()["items"]] == ["Hidden"]
    r = ctx.client.get(ctx.url("/products"), params={"sellable": False})
    assert [i["name"] for i in r.json()["items"]] == ["Rain gauge"]  # ignored for customers
    detail = ctx.client.get(ctx.url(f"/products/{gone['id']}"), headers=STAFF)
    assert detail.json()["active"] is False
    assert detail.headers["ETag"] == '"2"'


def test_paging_and_filters(ctx: Ctx) -> None:
    for i in range(5):
        ctx.create(name=f"Item {i}", type="RAD" if i % 2 else "MET")
    ctx.create(name="Free kit", type="PRO", probono=True)
    page1 = ctx.client.get(ctx.url("/products"), params={"limit": 2}).json()
    assert [i["name"] for i in page1["items"]] == ["Free kit", "Item 0"]
    page2 = ctx.client.get(ctx.url("/products"), params={"limit": 2, "cursor": page1["nextCursor"]}).json()
    assert [i["name"] for i in page2["items"]] == ["Item 1", "Item 2"]
    rad = ctx.client.get(ctx.url("/products"), params={"type": "RAD"}).json()["items"]
    assert [i["name"] for i in rad] == ["Item 1", "Item 3"]
    free = ctx.client.get(ctx.url("/products"), params={"probono": True}).json()["items"]
    assert [i["name"] for i in free] == ["Free kit"]
    paid = ctx.client.get(ctx.url("/products"), params={"probono": False}).json()["items"]
    assert len(paid) == 5
    assert ctx.client.get(ctx.url("/products"), params={"inStock": True}).json()["items"] == []


@pytest.mark.req("C4")
def test_edits_are_versioned_and_published(ctx: Ctx) -> None:
    p = ctx.create()
    url = ctx.url(f"/products/{p['id']}")
    assert ctx.client.patch(url, headers=STAFF, json={"name": "New"}).status_code == 428
    assert ctx.client.patch(url, headers={**STAFF, "If-Match": "7"}, json={"name": "New"}).status_code == 409
    r = ctx.client.patch(url, headers={**STAFF, "If-Match": '"1"'}, json={"name": "New", "cost": "99.50"})
    assert r.status_code == 200
    assert r.json()["version"] == 2
    assert r.json()["cost"] == "99.50"
    assert r.headers["ETag"] == '"2"'
    outbox = ctx.product(p["id"])["outbox"]
    assert [e["type"] for e in outbox] == ["product.created", "product.updated", "audit.recorded"]
    assert outbox[1]["payload"]["changed"] == ["cost", "name"]
    assert outbox[2]["payload"]["action"] == "product.cost_changed"
    assert outbox[2]["payload"]["from"] == "1250.00"
    for e in outbox:
        check_event(e)
    same = ctx.client.patch(url, headers={**STAFF, "If-Match": "2"}, json={"name": "New"})
    assert same.json()["version"] == 2  # nothing changed: no new version, no event
    assert ctx.client.patch(url, headers={**STAFF, "If-Match": "2"}, json={}).status_code == 422
    assert ctx.client.patch(url, headers={**STAFF, "If-Match": "2"}, json={"name": None}).status_code == 422


def test_turning_pro_bono_off_clears_its_limit(ctx: Ctx) -> None:
    p = ctx.create(type="PRO", probono=True, probonoMaxPerRequest=3)
    r = ctx.client.patch(ctx.url(f"/products/{p['id']}"), headers={**STAFF, "If-Match": "1"}, json={"probono": False})
    assert r.json()["probonoMaxPerRequest"] is None
    assert ctx.product(p["id"])["outbox"][-1]["payload"]["changed"] == ["probono", "probonoMaxPerRequest"]


def test_deactivate_is_a_soft_delete(ctx: Ctx) -> None:
    p = ctx.create()
    url = ctx.url(f"/products/{p['id']}")
    assert ctx.client.delete(url, headers={**STAFF, "If-Match": "5"}).status_code == 409
    assert ctx.client.delete(url, headers={**STAFF, "If-Match": "1"}).status_code == 204
    assert ctx.client.delete(url, headers={**STAFF, "If-Match": "2"}).status_code == 204  # already inactive
    assert ctx.client.get(url).status_code == 404
    types = [e["type"] for e in ctx.product(p["id"])["outbox"]]
    assert types == ["product.created", "product.deleted", "audit.recorded"]
    assert ctx.client.delete(ctx.url("/products/NOPE"), headers={**STAFF, "If-Match": "1"}).status_code == 404
    assert (
        ctx.client.patch(ctx.url("/products/NOPE"), headers={**STAFF, "If-Match": "1"}, json={"name": "x"}).status_code
        == 404
    )


def test_customers_cannot_write(ctx: Ctx) -> None:
    r = ctx.client.post(
        ctx.url("/products"),
        headers=USER,
        json={"name": "X", "type": "MET", "department": "D", "sellable": True, "probono": False, "threshold": 0},
    )
    assert r.status_code == 403


def test_integers_beyond_mongodb_range_are_422_or_400_not_500(ctx: Ctx) -> None:
    """Schemathesis found a 500: threshold 2**63 overflowed MongoDB's int64 (P9)."""
    body = {"name": "X", "type": "MET", "department": "D", "sellable": True, "probono": False}
    for field, value in [("threshold", 2**63), ("threshold", 1_000_001), ("unitquantity", 2**63),
                         ("probonoMaxPerRequest", 2**63)]:  # fmt: skip
        r = ctx.client.post(ctx.url("/products"), headers=STAFF, json={**body, "threshold": 0, field: value})
        assert r.status_code == 422, (field, value, r.status_code)
    p = ctx.create()
    r = ctx.client.patch(ctx.url(f"/products/{p['id']}"), headers={**STAFF, "If-Match": str(2**63)}, json={"name": "Y"})
    assert r.status_code == 400
