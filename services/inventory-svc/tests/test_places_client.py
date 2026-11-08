"""catalog-svc places client: service token from identity (cached), filters, errors -> 503."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from cimh_common.errors import ProblemError
from inventory_svc.places import CatalogPlaces


def test_list_and_put_with_a_cached_service_token() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("/internal/service-token"):
            assert json.loads(request.read()) == {"service": "inventory", "secret": "s3"}
            return httpx.Response(200, json={"token": "T", "expiresIn": 300})
        assert request.headers["Authorization"] == "Bearer T"
        if request.method == "GET":
            assert dict(request.url.params) == {"kind": "shelf", "barcode": "SHEL1"}
            return httpx.Response(200, json={"items": [{"kind": "shelf", "barcode": "SHEL1"}]})
        return httpx.Response(200, json=json.loads(request.read()))

    places = CatalogPlaces("http://catalog:8000/", "http://identity:8000", "s3", transport=httpx.MockTransport(handler))

    async def run() -> None:
        assert await places.list(kind="shelf", barcode="SHEL1") == [{"kind": "shelf", "barcode": "SHEL1"}]
        assert (await places.put({"kind": "site", "barcode": "SITE1"}))["barcode"] == "SITE1"

    asyncio.run(run())
    assert calls == [
        "POST /api/identity/v1/internal/service-token",
        "GET /api/catalog/v1/internal/places",
        "PUT /api/catalog/v1/internal/places",
    ]


def test_catalog_failure_is_a_503() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/internal/service-token"):
            return httpx.Response(200, json={"token": "T"})
        return httpx.Response(500)

    places = CatalogPlaces("http://catalog:8000", "http://identity:8000", "s3", transport=httpx.MockTransport(handler))
    with pytest.raises(ProblemError) as err:
        asyncio.run(places.list(kind="site"))
    assert err.value.status == 503
    assert err.value.code == "DEPENDENCY_UNAVAILABLE"
