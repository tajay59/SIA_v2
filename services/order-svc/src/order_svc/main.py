"""order-svc app factory. Run: gunicorn 'order_svc.main:build_app()' -k uvicorn.workers.UvicornWorker"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from cimh_common.app import create_app
from cimh_common.auth import JwksCache, TokenVerifier, http_jwks_fetcher, redis_revocation_check
from cimh_common.idempotency import IdempotencyStore
from cimh_common.outbox import outbox_backlog_hook
from cimh_common.redis_client import redis_client

from .api import router
from .clients import Deps, HttpDeps
from .config import Settings
from .service import OrderService
from .store import Store

BASE = "/api/orders/v1"


def build_app(
    settings: Settings | None = None,
    *,
    db: Any = None,
    redis: Any = None,
    token_verifier: TokenVerifier | None = None,
    deps: Deps | None = None,
    configure_logs: bool = True,
) -> FastAPI:
    s = settings or Settings.from_env()
    if db is None:
        from pymongo import AsyncMongoClient

        if not s.mongo_url:
            raise RuntimeError("MONGO_URL is required")
        db = AsyncMongoClient(s.mongo_url, tz_aware=True)[s.db_name]
    if redis is None:
        if not s.redis_url:
            raise RuntimeError("REDIS_URL is required (idempotency keys, revocation)")

        redis = redis_client(s.redis_url)
    if token_verifier is None:
        if not s.jwks_url:
            raise RuntimeError("JWKS_URL is required")
        token_verifier = TokenVerifier(
            JwksCache(http_jwks_fetcher(s.jwks_url)),
            issuer=s.issuer,
            audience=s.audience,
            is_revoked=redis_revocation_check(redis),
        )
    if deps is None:
        if not (s.catalog_url and s.identity_url and s.inventory_url and s.service_secret):
            raise RuntimeError("CATALOG_URL, INVENTORY_URL, IDENTITY_URL and SERVICE_SECRET are required")
        deps = HttpDeps(
            identity_url=s.identity_url,
            catalog_url=s.catalog_url,
            inventory_url=s.inventory_url,
            secret=s.service_secret,
        )

    store = Store(db)

    async def mongo_ok() -> bool:
        res = await db.command("ping")
        return bool(res.get("ok"))

    async def redis_ok() -> bool:
        return bool(await redis.ping())

    app = create_app(
        "order-svc",
        version=os.environ.get("APP_VERSION", "0.1.0"),
        token_verifier=token_verifier,
        readiness_checks={"mongo": mongo_ok, "redis": redis_ok},
        configure_logs=configure_logs,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        await store.ensure_indexes()
        yield

    app.router.lifespan_context = lifespan
    app.state.metrics.scrape_hooks.append(outbox_backlog_hook(app.state.metrics, {"orders": db["orders"]}))
    app.state.settings = s
    app.state.orders = OrderService(store, deps, quote_valid_days=s.quote_valid_days)
    app.state.idempotency = IdempotencyStore(redis, prefix="ord:idem")  # Redis ACL: order owns ord:*
    app.include_router(router, prefix=BASE)
    return app
