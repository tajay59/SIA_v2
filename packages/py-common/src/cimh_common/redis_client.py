"""The one way services open Redis (revocation, rate limits, idempotency, dedupe, locks).

Pen test 2026-11: after a Redis restart every pooled connection is stale, and each failed once, so requests
answered 503 (revocation fails closed) in bursts across all services. Connection errors are now retried once on
a fresh connection, and idle connections are health-checked before use. Redis being really down still fails
closed: the retry fails too and the caller answers 503.
"""

from __future__ import annotations

from typing import Any

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import BusyLoadingError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError


def redis_client(url: str, **kwargs: Any) -> Redis:
    opts: dict[str, Any] = {
        "retry": Retry(ExponentialBackoff(cap=0.5, base=0.05), retries=3),  # LOADING after a restart: ~1 s
        "retry_on_error": [RedisConnectionError, RedisTimeoutError, ConnectionResetError, BusyLoadingError],
        "health_check_interval": 15,
        "socket_connect_timeout": 2,
        "socket_timeout": 2,
        **kwargs,
    }
    return Redis.from_url(url, **opts)
