"""identity-svc lookup used for email lists: service token cached, 404 -> None."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from catalog_svc.identity_client import IdentityClient


def test_lookup_caches_the_service_token_and_maps_404() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/internal/service-token"):
            assert request.read() == b'{"service":"catalog","secret":"s3"}'
            return httpx.Response(200, json={"token": "T", "expiresIn": 300})
        assert request.headers["Authorization"] == "Bearer T"
        if request.url.path.endswith("/USR1"):
            return httpx.Response(200, json={"id": "USR1", "role": "staff", "status": "ACTIVE"})
        return httpx.Response(404, json={"code": "NOT_FOUND"})

    client = IdentityClient("http://identity:8000/", "s3", transport=httpx.MockTransport(handler))

    async def run() -> tuple[object, object]:
        return await client.account("USR1"), await client.account("USR404")

    found, missing = asyncio.run(run())
    assert found == {"id": "USR1", "role": "staff", "status": "ACTIVE"}
    assert missing is None
    assert calls.count("/api/identity/v1/internal/service-token") == 1


def test_lookup_raises_when_identity_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = IdentityClient("http://identity:8000", "s3", transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.account("USR1"))
