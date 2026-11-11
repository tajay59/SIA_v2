"""catalog-svc app factory. Run: gunicorn 'catalog_svc.main:build_app()' -k uvicorn.workers.UvicornWorker"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from cimh_common.app import create_app
from cimh_common.auth import JwksCache, TokenVerifier, http_jwks_fetcher, redis_revocation_check
from cimh_common.outbox import outbox_backlog_hook

from .api import router
from .config import Settings
from .identity_client import IdentityClient
from .service import AccountLookup, CatalogService
from .store import Store

BASE = "/api/catalog/v1"


def build_app(
    settings: Settings | None = None,
    *,
    db: Any = None,
    redis: Any = None,
    token_verifier: TokenVerifier | None = None,
    lookup_account: AccountLookup | None = None,
    configure_logs: bool = True,
    create_view: bool = True,
) -> FastAPI:
    s = settings or Settings.from_env()
    if db is None:
        from pymongo import AsyncMongoClient

        if not s.mongo_url:
            raise RuntimeError("MONGO_URL is required")
        db = AsyncMongoClient(s.mongo_url, tz_aware=True)[s.db_name]
    if redis is None and s.redis_url:
        import redis.asyncio as aioredis

        redis = aioredis.from_url(s.redis_url)
    if token_verifier is None:
        if not s.jwks_url:
            raise RuntimeError("JWKS_URL is required")
        token_verifier = TokenVerifier(
            JwksCache(http_jwks_fetcher(s.jwks_url)),
            issuer=s.issuer,
            audience=s.audience,
            is_revoked=redis_revocation_check(redis) if redis is not None else None,
        )
    if lookup_account is None and s.identity_url and s.service_secret:
        lookup_account = IdentityClient(s.identity_url, s.service_secret).account

    store = Store(db)

    async def mongo_ok() -> bool:
        res = await db.command("ping")
        return bool(res.get("ok"))

    checks: dict[str, Any] = {"mongo": mongo_ok}
    if redis is not None:

        async def redis_ok() -> bool:
            return bool(await redis.ping())

        checks["redis"] = redis_ok

    app = create_app(
        "catalog-svc",
        version=os.environ.get("APP_VERSION", "0.1.0"),
        token_verifier=token_verifier,
        readiness_checks=checks,
        configure_logs=configure_logs,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        await store.ensure_indexes()
        if create_view:
            await store.ensure_view()
        yield

    app.router.lifespan_context = lifespan
    app.state.metrics.scrape_hooks.append(
        outbox_backlog_hook(app.state.metrics, {"product": db["product"], "misc": db["misc"]})
    )
    app.state.settings = s
    app.state.catalog = CatalogService(store, lookup_account)
    app.include_router(router, prefix=BASE)
    return app
