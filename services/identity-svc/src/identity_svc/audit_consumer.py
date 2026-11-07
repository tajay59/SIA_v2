"""`audit.events` consumer (TAD §4 identity "Consumes"): other services' audit records go into `auditlog`.

    python -m identity_svc.audit_consumer

The entry id is derived from the event id, so a redelivered event can never create a second entry, even
if the processed-event key in Redis has expired.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from typing import Any

from cimh_common.outbox import EventEnvelope

from .store import Store

log = logging.getLogger("identity.audit")
TOPIC = "audit.events"


def entry_from_event(event: EventEnvelope) -> dict[str, Any]:
    p = event.payload
    if (
        not isinstance(p.get("action"), str)
        or not isinstance(p.get("entity"), dict)
        or not isinstance(p.get("actor"), dict)
    ):
        # Contract violation: retrying won't fix it, so the consumer sends it to the DLQ.
        raise ValueError(f"audit event {event.eventId} lacks action/entity/actor")
    entry: dict[str, Any] = {
        "id": f"AUD{event.eventId}",
        "at": event.occurredAt,
        "actor": {k: p["actor"].get(k) for k in ("id", "name", "role")},
        "action": p["action"],
        "entity": {"type": str(p["entity"].get("type")), "id": str(p["entity"].get("id"))},
        "correlationId": event.correlationId,
    }
    for k in ("from", "to", "reason", "ip"):
        if p.get(k) is not None:
            entry[k] = p[k]
    return entry


def make_handler(store: Store) -> Any:
    async def handle(event: EventEnvelope) -> None:
        entry = entry_from_event(event)
        await store.audit.update_one({"id": entry["id"]}, {"$setOnInsert": entry}, upsert=True)

    return handle


async def main() -> None:
    from aiokafka import AIOKafkaProducer
    from pymongo import AsyncMongoClient
    from redis.asyncio import from_url

    from cimh_common.consume_loop import kafka_security, run_service_consumer
    from cimh_common.consumer import IdempotentConsumer
    from cimh_common.logging import configure_logging
    from cimh_common.settings import env_secret

    configure_logging("identity-audit-consumer", os.environ.get("LOG_LEVEL", "INFO"))
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
    handler = IdempotentConsumer("identity", make_handler(Store(db)), redis, producer)
    try:
        await run_service_consumer(
            group="identity", topics=[TOPIC], handler=handler, bootstrap=bootstrap, security=security, stop=stop
        )
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
