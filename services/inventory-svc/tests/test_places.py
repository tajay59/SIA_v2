"""PRD I1: sites, locations, numbered shelves (stored through catalog-svc), shelf validation for scans."""

from __future__ import annotations

import pytest

from .conftest import STAFF, Ctx


@pytest.mark.req("I1")
def test_site_location_shelves_and_validation(ctx: Ctx) -> None:
    r = ctx.client.post(
        ctx.url("/sites"), headers=STAFF, json={"name": "Husbands", "country": "BB", "address": "St James"}
    )
    assert r.status_code == 201, r.text
    site = r.json()
    assert site["barcode"].startswith("SITE")
    assert len(site["barcode"]) == 36
    assert site["active"] is True
    assert site["address"] == "St James"
    assert [s["barcode"] for s in ctx.client.get(ctx.url("/sites"), headers=STAFF).json()["items"]] == [site["barcode"]]

    loc = ctx.client.post(
        ctx.url(f"/sites/{site['barcode']}/locations"), headers=STAFF, json={"name": "Store A"}
    ).json()
    assert loc["barcode"].startswith("LOC")
    assert loc["shelfCount"] == 0

    first = ctx.client.post(ctx.url(f"/locations/{loc['barcode']}/shelves"), headers=STAFF, json={"count": 2}).json()
    more = ctx.client.post(ctx.url(f"/locations/{loc['barcode']}/shelves"), headers=STAFF, json={"count": 1}).json()
    assert [s["number"] for s in first["items"] + more["items"]] == [1, 2, 3]  # numbering continues
    assert all(s["barcode"].startswith("SHEL") for s in first["items"])

    shelf = ctx.client.get(ctx.url(f"/shelves/{first['items'][1]['barcode']}"), headers=STAFF)
    assert shelf.status_code == 200
    assert shelf.json() | {"barcode": "x"} == {
        "barcode": "x", "number": 2, "site": site["barcode"], "siteName": "Husbands",
        "location": loc["barcode"], "locationName": "Store A",
    }  # fmt: skip

    locs = ctx.client.get(ctx.url(f"/sites/{site['barcode']}/locations"), params={"withShelves": True}, headers=STAFF)
    item = locs.json()["items"][0]
    assert item["shelfCount"] == 3
    assert [s["number"] for s in item["shelves"]] == [1, 2, 3]
    assert (
        "shelves"
        not in ctx.client.get(ctx.url(f"/sites/{site['barcode']}/locations"), headers=STAFF).json()["items"][0]
    )


def test_unknown_places(ctx: Ctx) -> None:
    r = ctx.client.post(ctx.url("/sites/SITEnope/locations"), headers=STAFF, json={"name": "X"})
    assert r.status_code == 404
    assert ctx.client.post(ctx.url("/locations/LOCnope/shelves"), headers=STAFF, json={"count": 1}).status_code == 404
    r = ctx.client.get(ctx.url("/shelves/SHELnope"), headers=STAFF)
    assert r.status_code == 404
    assert r.json()["code"] == "SHELF_NOT_FOUND"
    site = ctx.client.post(ctx.url("/sites"), headers=STAFF, json={"name": "S", "country": "BB"}).json()["barcode"]
    r = ctx.client.get(ctx.url(f"/shelves/{site}"), headers=STAFF)  # a site is not a shelf
    assert r.status_code == 404
    assert r.json()["code"] == "SHELF_NOT_FOUND"
    r = ctx.client.post(ctx.url(f"/sites/{site}/locations"), headers=STAFF, json={"name": "X", "colour": "red"})
    assert r.status_code == 422  # strict bodies


def test_shelf_lookups_are_cached(ctx: Ctx) -> None:
    shelf = ctx.shelves(1)[0]
    before = ctx.places.calls
    for _ in range(3):
        assert ctx.client.get(ctx.url(f"/shelves/{shelf}"), headers=STAFF).status_code == 200
    assert ctx.places.calls == before  # written through on create, then served from Redis
