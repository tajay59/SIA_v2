"""hello-svc: the P1 skeleton that proves the pipeline (PR -> CI -> image -> staging -> production).

It exercises everything a real service needs: Problem errors, trace ids, JSON logs,
/metrics, /health/live + /health/ready (Mongo and Redis checks when configured),
and JWT auth via identity's JWKS. It owns no data.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends

from cimh_common.app import ReadinessCheck, create_app
from cimh_common.auth import JwksCache, Principal, TokenVerifier, http_jwks_fetcher, redis_revocation_check
from cimh_common.authz import current_principal, require_staff

SERVICE = "hello-svc"
VERSION = os.environ.get("APP_VERSION", "0.1.0")


def _readiness() -> tuple[dict[str, ReadinessCheck], Any]:
    checks: dict[str, ReadinessCheck] = {}
    redis_client: Any = None

    mongo_url = os.environ.get("MONGO_URL")
    if mongo_url:
        from pymongo import AsyncMongoClient

        mongo: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_url, serverSelectionTimeoutMS=2000)

        async def mongo_ok() -> bool:
            res = await mongo.admin.command("ping")
            return bool(res.get("ok"))

        checks["mongo"] = mongo_ok

    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(redis_url, socket_timeout=2)

        async def redis_ok() -> bool:
            return bool(await redis_client.ping())

        checks["redis"] = redis_ok
    return checks, redis_client


def _verifier(redis_client: Any) -> TokenVerifier | None:
    jwks_url = os.environ.get("JWKS_URL")
    if not jwks_url:
        return None
    return TokenVerifier(
        JwksCache(http_jwks_fetcher(jwks_url)),
        issuer=os.environ.get("JWT_ISSUER", "https://identity.cimh.internal"),
        audience=os.environ.get("JWT_AUDIENCE", "cimh-stores"),
        is_revoked=redis_revocation_check(redis_client) if redis_client is not None else None,
    )


router = APIRouter()


@router.get("/greeting")
async def greeting() -> dict[str, str]:
    return {"message": "Hello from CIMH Stores", "service": SERVICE, "version": VERSION}


@router.get("/whoami")
async def whoami(me: Principal = Depends(current_principal)) -> dict[str, str]:
    return {"sub": me.sub, "role": me.role}


@router.get("/staff-only")
async def staff_only(me: Principal = Depends(require_staff)) -> dict[str, str]:
    return {"ok": "staff"}


def build_app(**overrides: Any) -> Any:
    checks, redis_client = _readiness()
    app = create_app(
        SERVICE,
        version=VERSION,
        token_verifier=overrides.get("token_verifier", _verifier(redis_client)),
        readiness_checks=overrides.get("readiness_checks", checks),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        configure_logs=overrides.get("configure_logs", True),
    )
    app.include_router(router, prefix="/api/hello/v1")
    return app


app = build_app()
