"""document-svc app factory. Run: gunicorn 'document_svc.main:build_app()' -k uvicorn.workers.UvicornWorker"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from cimh_common.app import create_app
from cimh_common.auth import JwksCache, TokenVerifier, http_jwks_fetcher, redis_revocation_check
from cimh_common.redis_client import redis_client

from .api import router
from .clients import HttpOrders, KafkaPublisher, Orders, Publisher
from .config import Settings
from .files import ClamdScanner, FileStore, NoScanner, Scanner
from .service import DocumentService

BASE = "/api/documents/v1"


def build_app(
    settings: Settings | None = None,
    *,
    redis: Any = None,
    token_verifier: TokenVerifier | None = None,
    orders: Orders | None = None,
    publisher: Publisher | None = None,
    scanner: Scanner | None = None,
    configure_logs: bool = True,
) -> FastAPI:
    s = settings or Settings.from_env()
    if token_verifier is None:
        if not (s.jwks_url and s.redis_url):
            raise RuntimeError("JWKS_URL and REDIS_URL are required")

        redis = redis or redis_client(s.redis_url)
        token_verifier = TokenVerifier(
            JwksCache(http_jwks_fetcher(s.jwks_url)),
            issuer=s.issuer,
            audience=s.audience,
            is_revoked=redis_revocation_check(redis),
        )
    if orders is None:
        if not (s.identity_url and s.order_url and s.service_secret):
            raise RuntimeError("IDENTITY_URL, ORDER_URL and SERVICE_SECRET are required")
        orders = HttpOrders(identity_url=s.identity_url, order_url=s.order_url, secret=s.service_secret)
    kafka: KafkaPublisher | None = None
    if publisher is None:
        if not s.kafka_bootstrap:
            raise RuntimeError("KAFKA_BOOTSTRAP is required (document.events)")
        from cimh_common.consume_loop import kafka_security

        kafka = KafkaPublisher(s.kafka_bootstrap, kafka_security(dict(os.environ)))
        publisher = kafka
    if scanner is None:
        scanner = ClamdScanner(s.clamd_host, s.clamd_port) if s.scan_enabled else NoScanner()

    files = FileStore(s.data_dir)

    async def volume_ok() -> bool:
        return (files.root / "protected").is_dir() or files.root.is_dir()

    app = create_app(
        "document-svc",
        version=os.environ.get("APP_VERSION", "0.1.0"),
        token_verifier=token_verifier,
        readiness_checks={"volume": volume_ok, "scanner": scanner.ready},
        configure_logs=configure_logs,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        if kafka is not None:
            await kafka.start()
        try:
            yield
        finally:
            if kafka is not None:
                await kafka.stop()

    app.router.lifespan_context = lifespan
    app.state.settings = s
    app.state.documents = DocumentService(files, orders, publisher, scanner, max_bytes=s.max_bytes)
    app.include_router(router, prefix=BASE)
    return app
