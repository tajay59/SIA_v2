"""inventory-consumer: keeps the `stock` copies of product data in step with catalog-svc (TAD §4.3).

    python -m inventory_svc.consumer

  catalog.product.events  product.created / product.updated -> stock.productName, type, threshold, active
                          product.deleted                   -> stock.active = false
  order.events            order.accepted         -> reserve the lines the customer chose from CIMH stock
                          order.probono_approved -> reserve every line
                          order.cancelled / order.expired / order.agreement_rejected -> release what is held
The catalog topic is compacted, so a new consumer group starts from a full snapshot of the catalogue.
Reservations are all-or-nothing; a shortfall publishes stock.reservation_failed (order-svc flags the lines).
Delivery is at-least-once; the handlers are idempotent (an older event never overwrites a newer one).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from typing import Any

from cimh_common.auth import Principal
from cimh_common.errors import ProblemError
from cimh_common.outbox import EventEnvelope
from cimh_common.redis_client import redis_client

from .service import InventoryService

log = logging.getLogger("inventory.consumer")
TOPICS = ["catalog.product.events", "order.events"]
RELEASE_ON = ("order.cancelled", "order.expired", "order.agreement_rejected")


def make_handler(service: InventoryService) -> Any:
    async def handle(event: EventEnvelope) -> None:
        p = event.payload
        if event.type in ("product.created", "product.updated"):
            if not isinstance(p.get("productId"), str) or not isinstance(p.get("threshold"), int):
                raise ValueError(f"{event.type} {event.eventId} lacks productId/threshold")  # -> DLQ
            await service.product_upserted(p, event.occurredAt, event.correlationId or event.eventId)
        elif event.type == "product.deleted":
            if not isinstance(p.get("productId"), str):
                raise ValueError(f"product.deleted {event.eventId} lacks productId")
            await service.product_deleted(p, event.occurredAt)
        elif event.type in ("order.accepted", "order.probono_approved", *RELEASE_ON):
            order_id = p.get("orderId")
            if not isinstance(order_id, str):
                raise ValueError(f"{event.type} {event.eventId} lacks orderId")
            actor = Principal(sub=event.actorId or "svc:order", role="service")
            cid = event.correlationId or event.eventId
            if event.type in RELEASE_ON:
                await service.release(actor, order_id, cid)
                return
            lines = [
                {"lineId": x["lineId"], "productId": x["productId"], "qty": int(x["qty"])}
                for x in p.get("lines") or []
                if event.type == "order.probono_approved" or x.get("choice") == "CIMH"
            ]
            if not lines:
                return
            try:
                await service.reserve(actor, order_id, lines, cid)
            except ProblemError as exc:
                if exc.code != "RESERVATION_FAILED":  # the failure event is already in the outbox
                    raise

    return handle


async def main() -> None:
    from aiokafka import AIOKafkaProducer
    from pymongo import AsyncMongoClient

    from cimh_common.consume_loop import kafka_security, run_service_consumer
    from cimh_common.consumer import IdempotentConsumer
    from cimh_common.logging import configure_logging
    from cimh_common.settings import env_secret

    from .store import Store

    configure_logging("inventory-consumer", os.environ.get("LOG_LEVEL", "INFO"))
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
    # The consumer never touches places, so it needs no catalog client.
    service = InventoryService(Store(db), places=None, redis=redis)  # type: ignore[arg-type]
    handler = IdempotentConsumer("inventory", make_handler(service), redis, producer)
    try:
        await run_service_consumer(
            group="inventory", topics=TOPICS, handler=handler, bootstrap=bootstrap, security=security, stop=stop
        )
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
