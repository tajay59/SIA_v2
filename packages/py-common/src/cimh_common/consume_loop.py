"""Run an `IdempotentConsumer` against Kafka (TAD §5.4 retry topics then DLQ).

Two loops per service: the main topics, and their `.retry` topics. A retry message carries a not-before
time; the retry loop waits for it before handling (blocking only the retry loop, never the main topics).
Offsets are committed after each message is handled, so a crash redelivers at most the current message,
and the idempotent consumer skips it if it was already applied.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import ssl
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .consumer import IdempotentConsumer, Message, Outcome

log = logging.getLogger("cimh.consume")


def to_message(record: Any) -> Message:
    return Message(topic=record.topic, value=record.value, key=record.key, headers=list(record.headers or []))


async def consume(
    kafka: Any,
    handler: IdempotentConsumer,
    stop: asyncio.Event,
    *,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    clock: Callable[[], float] = time.time,
) -> None:
    """Handle records from a started aiokafka consumer until `stop` is set."""

    async def wait_or_stop(seconds: float) -> None:
        # Waiting for a retry's not-before time must not delay shutdown.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=seconds)

    pause = sleep or wait_or_stop
    from aiokafka.structs import TopicPartition  # local: py-common doesn't require aiokafka for unit tests

    while not stop.is_set():
        batches = await kafka.getmany(timeout_ms=1000)
        for tp, records in batches.items():
            for record in records:
                msg = to_message(record)
                outcome = await handler.handle(msg)
                while outcome == Outcome.DELAYED and not stop.is_set():
                    await pause(max(0.0, min(30.0, handler.not_before(msg) - clock())))
                    outcome = await handler.handle(msg)
                if stop.is_set() and outcome == Outcome.DELAYED:
                    return  # not committed: redelivered after restart
                await kafka.commit({TopicPartition(tp.topic, tp.partition): record.offset + 1})


def kafka_security(env: dict[str, str]) -> dict[str, Any]:
    """SASL_SSL/SCRAM settings from KAFKA_SASL_USER, KAFKA_SASL_PASSWORD_FILE, KAFKA_CA_FILE (TR-SEC-7)."""
    user = env.get("KAFKA_SASL_USER")
    if not user:
        return {}
    with open(env["KAFKA_SASL_PASSWORD_FILE"], encoding="utf-8") as fh:
        password = fh.read().strip()
    ca = env.get("KAFKA_CA_FILE")
    return {
        "security_protocol": "SASL_SSL",
        "sasl_mechanism": "SCRAM-SHA-512",
        "sasl_plain_username": user,
        "sasl_plain_password": password,
        "ssl_context": ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context(),
    }


async def run_service_consumer(
    *,
    group: str,
    topics: list[str],
    handler: IdempotentConsumer,
    bootstrap: str,
    security: dict[str, Any],
    stop: asyncio.Event,
) -> None:
    """Start the main and retry loops for `topics` and run them until `stop`."""
    from aiokafka import AIOKafkaConsumer

    def make(subscribed: list[str], group_id: str) -> Any:
        return AIOKafkaConsumer(
            *subscribed,
            bootstrap_servers=bootstrap,
            group_id=group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            client_id=f"{group_id}-consumer",
            **security,
        )

    # Separate groups: one group with two different subscriptions keeps rebalancing (and stalls both).
    # `<group>.retry` is still covered by the service's prefixed group ACL (deploy/kafka/setup.sh).
    main_c, retry_c = make(topics, group), make([f"{t}.retry" for t in topics], f"{group}.retry")
    await main_c.start()
    await retry_c.start()
    try:
        await asyncio.gather(consume(main_c, handler, stop), consume(retry_c, handler, stop))
    finally:
        for c in (main_c, retry_c):
            with contextlib.suppress(Exception):
                await c.stop()
