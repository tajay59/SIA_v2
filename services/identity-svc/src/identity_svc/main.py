"""identity-svc app factory. Run: gunicorn 'identity_svc.main:build_app()' -k uvicorn.workers.UvicornWorker"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from cimh_common.app import create_app
from cimh_common.auth import JwksCache, TokenVerifier, redis_revocation_check
from cimh_common.outbox import outbox_backlog_hook
from cimh_common.redis_client import redis_client

from . import security as sec
from .api import router
from .config import Settings
from .service import IdentityService
from .store import Store
from .tokens import KeyRing, TokenService

BASE = "/api/identity/v1"


def build_app(
    settings: Settings | None = None,
    *,
    db: Any = None,
    redis: Any = None,
    breach_check: sec.BreachCheck | None = None,
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
            raise RuntimeError("REDIS_URL is required")
        redis = redis_client(s.redis_url)

    keys = KeyRing(s.private_key_pem, s.previous_public_keys_pem)

    async def own_jwks() -> dict[str, Any]:
        return keys.jwks()

    verifier = TokenVerifier(
        JwksCache(own_jwks), issuer=s.issuer, audience=s.audience, is_revoked=redis_revocation_check(redis)
    )
    store = Store(db)

    async def mongo_ok() -> bool:
        res = await db.command("ping")
        return bool(res.get("ok"))

    async def redis_ok() -> bool:
        return bool(await redis.ping())

    app = create_app(
        "identity-svc",
        version=os.environ.get("APP_VERSION", "0.1.0"),
        token_verifier=verifier,
        readiness_checks={"mongo": mongo_ok, "redis": redis_ok},
        configure_logs=configure_logs,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        await store.ensure_indexes()
        yield

    app.router.lifespan_context = lifespan
    app.state.metrics.scrape_hooks.append(outbox_backlog_hook(app.state.metrics, {"accounts": db["accounts"]}))
    app.state.settings = s
    app.state.keys = keys
    app.state.identity = IdentityService(
        s,
        store,
        TokenService(s, keys, redis),
        sec.Envelope(s.data_key_b64),
        breach_check or (sec.hibp_check() if s.hibp_enabled else sec.no_breach_check),
    )
    app.state.identity.on_event = app.state.metrics.security_event
    app.include_router(router, prefix=BASE)
    return app
