"""create_app(): FastAPI with Problem errors, trace ids, JSON logs, metrics, health and security headers."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from .auth import TokenVerifier
from .errors import install_error_handlers
from .ids import ulid
from .logging import configure_logging, trace_id_var
from .metrics import ServiceMetrics

ReadinessCheck = Callable[[], Awaitable[bool]]
_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    # ZAP 90004 (pen test 2026-11): API responses are never read by other sites (Spectre-style leaks).
    "Cross-Origin-Resource-Policy": "same-site",
}

log = logging.getLogger("cimh.http")


def create_app(
    service: str,
    *,
    version: str = "0.0.0",
    root_path: str = "",
    token_verifier: TokenVerifier | None = None,
    readiness_checks: dict[str, ReadinessCheck] | None = None,
    log_level: str = "INFO",
    configure_logs: bool = True,
) -> FastAPI:
    if configure_logs:
        configure_logging(service, log_level)
    app = FastAPI(title=service, version=version, root_path=root_path)
    app.state.service = service
    app.state.token_verifier = token_verifier
    app.state.readiness_checks = dict(readiness_checks or {})
    metrics = ServiceMetrics(service)
    app.state.metrics = metrics
    install_error_handlers(app)

    @app.middleware("http")
    async def _observe(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        match = _TRACEPARENT.match(request.headers.get("traceparent", ""))
        trace_id = match.group(1) if match else ulid().lower()
        request.state.trace_id = trace_id
        token = trace_id_var.set(trace_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            log.exception("unhandled error", extra={"path": request.url.path})
            raise
        finally:
            elapsed = time.perf_counter() - start
            metrics.observe(request, status, elapsed)
            trace_id_var.reset(token)
        response.headers["X-Trace-Id"] = trace_id
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response

    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        results: dict[str, str] = {}
        ok = True
        for name, check in app.state.readiness_checks.items():
            try:
                passed = await check()
            except Exception:
                passed = False
            results[name] = "ok" if passed else "fail"
            ok = ok and passed
        return JSONResponse({"status": "ok" if ok else "fail", "checks": results}, status_code=200 if ok else 503)

    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:
        # nginx does not route /metrics; Prometheus scrapes it on the internal network.
        await metrics.collect()
        return metrics.render()

    return app
