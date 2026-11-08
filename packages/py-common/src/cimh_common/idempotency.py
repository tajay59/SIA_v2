"""`Idempotency-Key` handling (TRD TR-API-6, API README §1): a repeat within 24 h returns the first response.

    result = await IdempotencyStore(redis).run(scope=f"{principal.sub}:POST /stow", key=key,
                                                fingerprint=body_json, call=lambda: do_stow(...))

- The first call runs `call()` and stores its JSON result (or its 4xx ProblemError, so a replayed scan that
  failed gets the same answer). 5xx and unexpected errors are not stored: the client may retry them.
- A repeat with the same key and the same request returns the stored outcome without running `call()`.
- The same key with a different request -> 422 IDEMPOTENCY_KEY_REUSED.
- A repeat while the first is still running -> 409 IDEMPOTENCY_IN_PROGRESS (the client retries shortly).
Keys are scoped by caller and operation, so two devices can't collide.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from .errors import ProblemError

TTL_SECONDS = 24 * 3600
PENDING_SECONDS = 60


def fingerprint(body: Any) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


class IdempotencyStore:
    def __init__(self, redis: Any, *, prefix: str = "idem", ttl: int = TTL_SECONDS) -> None:
        self.redis = redis
        self.prefix = prefix
        self.ttl = ttl

    def _key(self, scope: str, key: str) -> str:
        return f"{self.prefix}:{hashlib.sha256(f'{scope}|{key}'.encode()).hexdigest()}"

    @staticmethod
    def _replay(stored: dict[str, Any], fp: str) -> Any:
        if stored.get("fp") != fp:
            raise ProblemError(422, "IDEMPOTENCY_KEY_REUSED", "This Idempotency-Key was used for a different request")
        if stored.get("pending"):
            raise ProblemError(409, "IDEMPOTENCY_IN_PROGRESS", "The first request with this key is still running")
        if "error" in stored:
            e = stored["error"]
            raise ProblemError(e["status"], e.get("code"), e.get("detail"), errors=e.get("errors"))
        return stored["result"]

    async def run(self, *, scope: str, key: str, fingerprint: str, call: Callable[[], Awaitable[Any]]) -> Any:
        rkey = self._key(scope, key)
        claimed = await self.redis.set(
            rkey, json.dumps({"fp": fingerprint, "pending": True}), nx=True, ex=PENDING_SECONDS
        )
        if not claimed:
            raw = await self.redis.get(rkey)
            if raw is not None:
                return self._replay(json.loads(raw), fingerprint)
            # Expired between SET and GET: treat as new (rare).
            await self.redis.set(rkey, json.dumps({"fp": fingerprint, "pending": True}), ex=PENDING_SECONDS)
        try:
            result = await call()
        except ProblemError as exc:
            if 400 <= exc.status < 500:
                err = {"status": exc.status, "code": exc.code, "detail": exc.detail, "errors": exc.errors}
                await self.redis.set(rkey, json.dumps({"fp": fingerprint, "error": err}), ex=self.ttl)
            else:
                await self.redis.delete(rkey)
            raise
        except BaseException:
            await self.redis.delete(rkey)
            raise
        await self.redis.set(rkey, json.dumps({"fp": fingerprint, "result": result}, default=str), ex=self.ttl)
        return result
