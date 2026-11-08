"""Scheduled jobs of order-svc.

    python -m order_svc.jobs            # loop: one leader (Redis lock) runs every JOBS_INTERVAL_SECONDS
    python -m order_svc.jobs --once     # run every job once and exit (ops, tests)

Jobs:
  expire_quotes   QUOTED / AWAITING_AGREEMENT past the quote's 30-day validity -> CANCELLED (auto);
                  `order.expired` is published (inventory releases nothing: no stock is held before acceptance).
  purge_carts     carts untouched for 180 days are emptied (business rule).
Both are idempotent and bounded per run.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
from typing import Any

from .service import OrderService

log = logging.getLogger("order.jobs")


async def run_all(service: OrderService) -> dict[str, int]:
    return {"expired": await service.expire_quotes(), "cartsEmptied": await service.purge_carts()}


async def main(once: bool = False) -> None:
    from pymongo import AsyncMongoClient
    from redis.asyncio import from_url

    from cimh_common.locks import RedisLock
    from cimh_common.logging import configure_logging
    from cimh_common.settings import env_secret

    from .store import Store

    configure_logging("order-jobs", os.environ.get("LOG_LEVEL", "INFO"))
    db: Any = AsyncMongoClient(env_secret("MONGO_URL"), tz_aware=True)[os.environ.get("MONGO_DB", "inventory")]
    service = OrderService(Store(db), deps=None)  # type: ignore[arg-type]  # jobs make no HTTP calls
    if once:
        log.info("jobs done", extra=await run_all(service))
        return
    redis = from_url(env_secret("REDIS_URL"))
    interval = float(os.environ.get("JOBS_INTERVAL_SECONDS", "900"))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    lock = RedisLock(redis, "ord:jobs", ttl_ms=int(interval * 1000))
    while not stop.is_set():
        if await lock.acquire():
            try:
                log.info("jobs done", extra=await run_all(service))
            except Exception:
                log.exception("jobs failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    asyncio.run(main(ap.parse_args().once))
