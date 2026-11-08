"""inventory-svc app factory. Run: gunicorn 'inventory_svc.main:build_app()' -k uvicorn.workers.UvicornWorker"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from cimh_common.app import create_app
from cimh_common.auth import JwksCache, TokenVerifier, http_jwks_fetcher, redis_revocation_check
from cimh_common.idempotency import IdempotencyStore

from .api import router
from .config import Settings
from .documents import DocumentLabels, LabelPdfs
from .places import CatalogPlaces, Places
from .service import InventoryService
from .store import Store

BASE = "/api/inventory/v1"


def build_app(
    settings: Settings | None = None,
    *,
    db: Any = None,
    redis: Any = None,
    token_verifier: TokenVerifier | None = None,
    places: Places | None = None,
    label_pdfs: LabelPdfs | None = None,
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
            raise RuntimeError("REDIS_URL is required (idempotency keys, place cache)")
        import redis.asyncio as aioredis

        redis = aioredis.from_url(s.redis_url)
    if token_verifier is None:
        if not s.jwks_url:
            raise RuntimeError("JWKS_URL is required")
        token_verifier = TokenVerifier(
            JwksCache(http_jwks_fetcher(s.jwks_url)),
            issuer=s.issuer,
            audience=s.audience,
            is_revoked=redis_revocation_check(redis),
        )
    if places is None:
        if not (s.catalog_url and s.identity_url and s.service_secret):
            raise RuntimeError("CATALOG_URL, IDENTITY_URL and SERVICE_SECRET are required (places)")
        places = CatalogPlaces(s.catalog_url, s.identity_url, s.service_secret)
    if label_pdfs is None and s.document_url and s.identity_url and s.service_secret:
        label_pdfs = DocumentLabels(s.document_url, s.identity_url, s.service_secret)

    store = Store(db)

    async def mongo_ok() -> bool:
        res = await db.command("ping")
        return bool(res.get("ok"))

    async def redis_ok() -> bool:
        return bool(await redis.ping())

    app = create_app(
        "inventory-svc",
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
    app.state.settings = s
    app.state.inventory = InventoryService(
        store, places, redis, cache_seconds=s.place_cache_seconds, label_pdfs=label_pdfs
    )
    app.state.idempotency = IdempotencyStore(redis, prefix="inv:idem")  # Redis ACL: inventory owns inv:*
    app.include_router(router, prefix=BASE)
    return app
