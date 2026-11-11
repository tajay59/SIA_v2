"""order-consumer: reservation results from inventory-svc and files from document-svc (TAD §4.4).

    python -m order_svc.consumer

  inventory.stock.events  stock.reserved            -> lines[].reservation RESERVED + units
                          stock.reservation_failed  -> short lines FAILED (staff requote them)
                          stock.released            -> RESERVED lines -> RELEASED
  document.events         document.uploaded / document.generated -> files[] (agreement / CIMH quote ids)
                          document.deleted -> files[].deleted
  identity.user.events    user.suspended -> cart blocked (403 ACCOUNT_SUSPENDED); user.reactivated -> unblocked
                          (defence in depth: suspension already revokes every session)
                          user.deleted -> open requests cancelled, personal data "[deleted]", cart removed
Other stock events (counts, unit scans) are ignored. Handlers are idempotent; delivery is at-least-once.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from typing import Any

from cimh_common.outbox import EventEnvelope
from cimh_common.redis_client import redis_client

from .service import OrderService

log = logging.getLogger("order.consumer")
TOPICS = ["inventory.stock.events", "document.events", "identity.user.events"]


def make_handler(service: OrderService) -> Any:
    async def handle(event: EventEnvelope) -> None:
        p = event.payload
        t = event.type
        if t in ("stock.reserved", "stock.reservation_failed", "stock.released"):
            if not isinstance(p.get("orderId"), str):
                raise ValueError(f"{t} {event.eventId} lacks orderId")  # -> DLQ
            if t == "stock.reserved":
                await service.stock_reserved(p)
            elif t == "stock.reservation_failed":
                await service.stock_reservation_failed(p)
            else:
                await service.stock_released(p)
        elif t in ("document.uploaded", "document.generated"):
            if not isinstance(p.get("orderId"), str) or not isinstance(p.get("fileId"), str):
                raise ValueError(f"{t} {event.eventId} lacks orderId/fileId")
            if p.get("kind") == "labels":
                return
            await service.attach_file(
                p["orderId"],
                {
                    "id": p["fileId"],
                    "kind": p["kind"],
                    "name": p.get("name"),
                    "mime": p.get("mime"),
                    "size": p.get("size"),
                    "sha256": p.get("sha256"),
                    "uploadedAt": event.occurredAt,
                },
            )
        elif t in ("user.suspended", "user.reactivated"):
            account = p.get("userId")
            if not isinstance(account, str) or not account:
                raise ValueError(f"{t} {event.eventId} lacks userId")
            await service.set_cart_blocked(account, blocked=t == "user.suspended")
        elif t == "user.deleted":
            account = p.get("userId")
            if not isinstance(account, str) or not account:
                raise ValueError(f"{t} {event.eventId} lacks userId")
            await service.forget_person(account)
        elif t == "document.deleted":
            if not isinstance(p.get("orderId"), str) or not isinstance(p.get("fileId"), str):
                raise ValueError(f"{t} {event.eventId} lacks orderId/fileId")
            await service.file_deleted(p["orderId"], p["fileId"], p.get("reason"))

    return handle


async def main() -> None:
    from aiokafka import AIOKafkaProducer
    from pymongo import AsyncMongoClient

    from cimh_common.consume_loop import kafka_security, run_service_consumer
    from cimh_common.consumer import IdempotentConsumer
    from cimh_common.logging import configure_logging
    from cimh_common.settings import env_secret

    from .store import Store

    configure_logging("order-consumer", os.environ.get("LOG_LEVEL", "INFO"))
    db: Any = AsyncMongoClient(env_secret("MONGO_URL"), tz_aware=True)[os.environ.get("MONGO_DB", "inventory")]
    redis: Any = redis_client(env_secret("REDIS_URL"))
    security = kafka_security(dict(os.environ))
    bootstrap = os.environ["KAFKA_BOOTSTRAP"]
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap, acks="all", **security)
    await producer.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    service = OrderService(Store(db), deps=None)  # type: ignore[arg-type]  # handlers make no HTTP calls
    handler = IdempotentConsumer("order", make_handler(service), redis, producer)
    try:
        await run_service_consumer(
            group="order", topics=TOPICS, handler=handler, bootstrap=bootstrap, security=security, stop=stop
        )
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
