"""Redis leader lock (one outbox relay / scheduler leader per service)."""

from __future__ import annotations

import os
from typing import Any

_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end
"""
_EXTEND = """
if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('pexpire', KEYS[1], ARGV[2]) else return 0 end
"""


class RedisLock:
    def __init__(self, redis: Any, name: str, ttl_ms: int = 15_000) -> None:
        self.redis = redis
        self.key = f"lock:{name}"
        self.ttl_ms = ttl_ms
        self.token = os.urandom(16).hex()

    async def acquire(self) -> bool:
        return bool(await self.redis.set(self.key, self.token, nx=True, px=self.ttl_ms))

    async def extend(self) -> bool:
        return bool(await self.redis.eval(_EXTEND, 1, self.key, self.token, self.ttl_ms))

    async def release(self) -> bool:
        return bool(await self.redis.eval(_RELEASE, 1, self.key, self.token))
