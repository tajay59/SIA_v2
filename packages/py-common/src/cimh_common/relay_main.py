"""Outbox relay process: one per owning service (INFRASTRUCTURE §4.1 `outbox-relay-*`).

    python -m cimh_common.relay_main

Environment:
    MONGO_URL[_FILE], MONGO_DB (default inventory)
    REDIS_URL[_FILE]                     leader lock: only one relay per service publishes
    KAFKA_BOOTSTRAP                e.g. kafka1:9092,kafka2:9092,kafka3:9092
    RELAY_NAME                     e.g. identity (lock key and client id)
    RELAY_COLLECTIONS              e.g. accounts            (comma-separated)
    RELAY_TOPICS                   e.g. user.=identity.user.events,audit.=audit.events
    KAFKA_SASL_USER / KAFKA_SASL_PASSWORD_FILE (optional; SCRAM-SHA-512 in prod, TR-SEC-7)
    KAFKA_CA_FILE                  private CA for the brokers' TLS certificates
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import ssl
from typing import Any

from .locks import RedisLock
from .logging import configure_logging
from .outbox import OutboxRelay, topic_by_prefix
from .settings import env_secret

log = logging.getLogger("cimh.relay")


def parse_topics(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in raw.split(","):
        if "=" in part:
            prefix, topic = part.split("=", 1)
            out[prefix.strip()] = topic.strip()
    if not out:
        raise ValueError("RELAY_TOPICS is empty")
    return out


def kafka_kwargs() -> dict[str, Any]:
    kw: dict[str, Any] = {
        "bootstrap_servers": os.environ["KAFKA_BOOTSTRAP"],
        "acks": "all",
        "enable_idempotence": True,
        "client_id": f"outbox-relay-{os.environ.get('RELAY_NAME', 'svc')}",
    }
    user = os.environ.get("KAFKA_SASL_USER")
    if user:
        pw_file = os.environ.get("KAFKA_SASL_PASSWORD_FILE", "")
        with open(pw_file, encoding="utf-8") as fh:
            password = fh.read().strip()
        ca_file = os.environ.get("KAFKA_CA_FILE")
        kw.update(
            ssl_context=ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context(),
            security_protocol="SASL_SSL",
            sasl_mechanism="SCRAM-SHA-512",
            sasl_plain_username=user,
            sasl_plain_password=password,
        )
    return kw


async def run_leader(relays: list[OutboxRelay], lock: RedisLock, collections: list[Any], stop: asyncio.Event) -> None:
    """Publish while holding the lock; give it up (and stop) if the lock can't be extended."""

    def stream_for(coll: Any) -> Any:
        async def open_stream() -> Any:
            pipeline = [{"$match": {"operationType": {"$in": ["insert", "update", "replace"]}}}]
            return await coll.watch(pipeline, full_document="updateLookup")

        return open_stream

    tasks = [asyncio.create_task(r.run(stream_for(c))) for r, c in zip(relays, collections, strict=True)]
    try:
        while not stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=lock.ttl_ms / 3000)
            if not await lock.extend():
                log.warning("lost relay leadership")
                break
    finally:
        for r in relays:
            r.stop()
        await asyncio.gather(*tasks, return_exceptions=True)
        await lock.release()


async def main() -> None:
    from aiokafka import AIOKafkaProducer
    from pymongo import AsyncMongoClient
    from redis.asyncio import from_url

    name = os.environ.get("RELAY_NAME", "svc")
    configure_logging(f"outbox-relay-{name}", os.environ.get("LOG_LEVEL", "INFO"))
    topics = topic_by_prefix(parse_topics(os.environ["RELAY_TOPICS"]))
    db: Any = AsyncMongoClient(env_secret("MONGO_URL"), tz_aware=True)[os.environ.get("MONGO_DB", "inventory")]
    redis = from_url(env_secret("REDIS_URL"))
    names = [c.strip() for c in os.environ["RELAY_COLLECTIONS"].split(",") if c.strip()]
    collections = [db[n] for n in names]

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):  # Windows dev
            loop.add_signal_handler(sig, stop.set)

    producer = AIOKafkaProducer(**kafka_kwargs())
    await producer.start()
    try:
        while not stop.is_set():
            lock = RedisLock(redis, f"outbox-relay:{name}", ttl_ms=15_000)
            if await lock.acquire():
                log.info("relay leader", extra={"collections": names})
                relays = [OutboxRelay(c, producer, topics) for c in collections]
                await run_leader(relays, lock, collections, stop)
            else:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=5)
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
