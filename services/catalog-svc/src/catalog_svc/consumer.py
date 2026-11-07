"""catalog-consumer: keeps catalog copies in step with other services (TAD §4.2).

    python -m catalog_svc.consumer

  inventory.stock.events  stock.changed     -> product.inStock / stockCount (display only)
  media.results           image.processed   -> product.images[] + product.image_added
Other event types on these topics are ignored. Delivery is at-least-once; both handlers are idempotent.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from typing import Any

from cimh_common.outbox import EventEnvelope

from .service import CatalogService
from .store import Store

log = logging.getLogger("catalog.consumer")
TOPICS = ["inventory.stock.events", "media.results"]


def make_handler(service: CatalogService) -> Any:
    async def handle(event: EventEnvelope) -> None:
        p = event.payload
        if event.type == "stock.changed":
            if not isinstance(p.get("productId"), str) or not isinstance(p.get("available"), int):
                raise ValueError(f"stock.changed {event.eventId} lacks productId/available")  # -> DLQ
            await service.stock_changed(p, event.occurredAt)
        elif event.type == "image.processed":
            if not isinstance(p.get("productId"), str):
                raise ValueError(f"image.processed {event.eventId} lacks productId")
            if p.get("ok") and not (isinstance(p.get("fileId"), str) and isinstance(p.get("url"), str)):
                raise ValueError(f"image.processed {event.eventId} lacks fileId/url")
            if not p.get("ok"):
                log.warning("image processing failed", extra={"productId": p["productId"], "error": p.get("error")})
            await service.image_processed(p, event.correlationId or event.eventId)

    return handle


async def main() -> None:
    from aiokafka import AIOKafkaProducer
    from pymongo import AsyncMongoClient
    from redis.asyncio import from_url

    from cimh_common.consume_loop import kafka_security, run_service_consumer
    from cimh_common.consumer import IdempotentConsumer
    from cimh_common.logging import configure_logging
    from cimh_common.settings import env_secret

    configure_logging("catalog-consumer", os.environ.get("LOG_LEVEL", "INFO"))
    db: Any = AsyncMongoClient(env_secret("MONGO_URL"), tz_aware=True)[os.environ.get("MONGO_DB", "inventory")]
    redis: Any = from_url(env_secret("REDIS_URL"))
    security = kafka_security(dict(os.environ))
    bootstrap = os.environ["KAFKA_BOOTSTRAP"]
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap, acks="all", **security)
    await producer.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    handler = IdempotentConsumer("catalog", make_handler(CatalogService(Store(db))), redis, producer)
    try:
        await run_service_consumer(
            group="catalog", topics=TOPICS, handler=handler, bootstrap=bootstrap, security=security, stop=stop
        )
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
