"""Relay run loop / change stream, JWKS HTTP fetcher, Redis revocation, log setup."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import fakeredis.aioredis
import httpx
import pytest

from cimh_common import auth
from cimh_common.auth import extract_token, redis_revocation_check
from cimh_common.logging import configure_logging
from cimh_common.outbox import OutboxRelay

from .conftest import Keys
from .test_outbox_consumer import TOPICS, FakeCollection, FakeProducer, seed


def test_relay_run_with_change_stream_then_stop() -> None:
    async def run() -> None:
        coll, prod = FakeCollection(), FakeProducer()
        seed(coll, 1)
        relay = OutboxRelay(coll, prod, TOPICS, sweep_interval=0.01)

        async def stream_events() -> Any:
            async def gen() -> Any:
                yield {"fullDocument": None}
                yield {"fullDocument": dict(coll.docs["d1"])}

            return gen()

        task = asyncio.create_task(relay.run(stream_events))
        await asyncio.sleep(0.05)
        relay.stop()
        await asyncio.wait_for(task, 1)
        # Published once by the stream or the sweep; the doc ends empty either way.
        assert coll.docs["d1"]["outbox"] == []
        assert len(prod.sent) >= 1

    asyncio.run(run())


def test_relay_sweep_errors_are_survived() -> None:
    class Broken(FakeCollection):
        def find(self, filter: dict[str, Any], projection: dict[str, Any] | None = None) -> Any:
            raise RuntimeError("mongo down")

    async def run() -> None:
        relay = OutboxRelay(Broken(), FakeProducer(), TOPICS, sweep_interval=0.01)
        task = asyncio.create_task(relay.run())
        await asyncio.sleep(0.03)
        relay.stop()
        await asyncio.wait_for(task, 1)

    asyncio.run(run())


def test_http_jwks_fetcher(monkeypatch: pytest.MonkeyPatch, keys: Keys) -> None:
    jwks = keys.jwks()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/.well-known/jwks.json"
        return httpx.Response(200, json=jwks)

    real = httpx.AsyncClient

    def client(**kw: Any) -> httpx.AsyncClient:
        return real(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    fetch = auth.http_jwks_fetcher("http://identity/.well-known/jwks.json")
    assert asyncio.run(fetch()) == jwks


def test_redis_revocation_check() -> None:
    async def run() -> None:
        r = fakeredis.aioredis.FakeRedis()
        check = redis_revocation_check(r)
        assert not await check("j1", "s1")
        await r.set("revoked:session:s1", "1")
        assert await check("j1", "s1")
        assert not await check("j1", None)
        await r.set("revoked:jti:j1", "1")
        assert await check("j1", None)

    asyncio.run(run())


def test_extract_token_prefers_bearer() -> None:
    from starlette.requests import Request

    scope = {
        "type": "http",
        "headers": [(b"authorization", b"Bearer abc"), (b"cookie", b"access_token=xyz")],
        "method": "GET",
    }
    assert extract_token(Request(scope)) == ("abc", False)
    scope["headers"] = [(b"cookie", b"access_token=xyz")]
    assert extract_token(Request(scope)) == ("xyz", True)


def test_configure_logging_installs_json_handler() -> None:
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    try:
        configure_logging("svc", "DEBUG")
        assert root.level == logging.DEBUG
        assert type(root.handlers[0].formatter).__name__ == "JsonFormatter"
    finally:
        root.handlers[:], _ = saved[0], root.setLevel(saved[1])
