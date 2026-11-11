"""Prometheus metrics (TRD: Prometheus + Alertmanager only)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger(__name__)
ScrapeHook = Callable[[], Awaitable[None]]


class ServiceMetrics:
    def __init__(self, service: str, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry()
        self.requests = Counter(
            "http_requests_total",
            "HTTP requests",
            ["service", "method", "route", "status"],
            registry=self.registry,
        )
        self.latency = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency",
            ["service", "method", "route"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
            registry=self.registry,
        )
        self.events = Counter(
            "events_consumed_total", "Kafka events consumed", ["service", "topic", "outcome"], registry=self.registry
        )
        self.outbox_pending = Gauge(
            "outbox_pending_events", "Events waiting in the outbox", ["service", "collection"], registry=self.registry
        )
        self.outbox_oldest = Gauge(
            "outbox_oldest_event_age_seconds",
            "Age of the oldest event waiting in the outbox (0 when empty)",
            ["service", "collection"],
            registry=self.registry,
        )
        self.service = service
        self.scrape_hooks: list[ScrapeHook] = []

    def observe(self, request: Request, status: int, seconds: float) -> None:
        # Use the route template, not the raw path, to keep label cardinality bounded.
        route = getattr(request.scope.get("route"), "path", "unmatched")
        self.requests.labels(self.service, request.method, route, str(status)).inc()
        self.latency.labels(self.service, request.method, route).observe(seconds)

    async def collect(self) -> None:
        """Run the scrape-time hooks (e.g. outbox backlog); a failing hook never breaks /metrics."""
        for hook in self.scrape_hooks:
            try:
                await hook()
            except Exception:
                log.warning("metrics hook failed", exc_info=True)

    def render(self) -> Response:
        return Response(generate_latest(self.registry), media_type=CONTENT_TYPE_LATEST)
