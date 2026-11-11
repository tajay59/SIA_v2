"""redis_client(): stale connections after a Redis restart are retried, not turned into 503s (pen test 2026-11)."""

from __future__ import annotations

from redis.exceptions import BusyLoadingError
from redis.exceptions import ConnectionError as RedisConnectionError

from cimh_common.redis_client import redis_client


def test_retries_connection_and_loading_errors() -> None:
    r = redis_client("redis://example.invalid:6379/0")
    kw = r.connection_pool.connection_kwargs
    assert kw["retry"]._retries >= 2
    # redis-py merges retry_on_error into the retry policy of each new connection.
    assert RedisConnectionError in kw["retry_on_error"]
    assert BusyLoadingError in kw["retry_on_error"]
    assert kw["health_check_interval"] > 0
    assert kw["socket_timeout"] == 2


def test_callers_can_override() -> None:
    r = redis_client("redis://example.invalid:6379/0", socket_timeout=5)
    assert r.connection_pool.connection_kwargs["socket_timeout"] == 5
