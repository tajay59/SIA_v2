"""Idempotent Kafka consumer with retry topics and DLQ (TAD §5).

1. `SET NX processed:<group>:<eventId>` with a 7-day expiry; already set -> skip.
2. The handler applies the change with a conditional update, so replays are harmless.
3. On error, the message goes to `<topic>.retry` with a delay (1, 5, 30 min) and
   after 3 failures to `<topic>.dlq` (alerted on). If the retry hop itself fails,
   the dedupe key is released so a redelivery can try again.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .outbox import EventEnvelope

log = logging.getLogger(__name__)

PROCESSED_TTL_SECONDS = 7 * 24 * 3600
RETRY_DELAYS_SECONDS = (60, 300, 1800)
HDR_ATTEMPT = "x-attempt"
HDR_NOT_BEFORE = "x-not-before"
HDR_ORIGINAL_TOPIC = "x-original-topic"
HDR_ERROR = "x-error"

Handler = Callable[[EventEnvelope], Awaitable[None]]


class Redis(Protocol):
    async def set(self, name: str, value: str, *, nx: bool = ..., ex: int = ...) -> Any: ...
    async def delete(self, *names: str) -> Any: ...


class Producer(Protocol):
    async def send_and_wait(
        self, topic: str, value: bytes, key: bytes | None = None, headers: list[tuple[str, bytes]] | None = None
    ) -> Any: ...


@dataclass
class Message:
    """Transport-neutral view of a consumed record (adapt aiokafka's ConsumerRecord to this)."""

    topic: str
    value: bytes
    key: bytes | None = None
    headers: list[tuple[str, bytes]] | None = None

    def header(self, name: str) -> str | None:
        for k, v in self.headers or []:
            if k == name:
                return v.decode()
        return None


class Outcome:
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    RETRY = "retry"
    DLQ = "dlq"
    DELAYED = "delayed"


def base_topic(topic: str) -> str:
    for suffix in (".retry", ".dlq"):
        if topic.endswith(suffix):
            return topic[: -len(suffix)]
    return topic


class IdempotentConsumer:
    def __init__(
        self,
        group: str,
        handler: Handler,
        redis: Redis,
        producer: Producer,
        *,
        clock: Callable[[], float] = time.time,
        retry_delays: tuple[int, ...] = RETRY_DELAYS_SECONDS,
    ) -> None:
        self.group = group
        self.handler = handler
        self.redis = redis
        self.producer = producer
        self.clock = clock
        self.retry_delays = retry_delays

    def _dedupe_key(self, event_id: str) -> str:
        return f"processed:{self.group}:{event_id}"

    def not_before(self, msg: Message) -> float:
        nb = msg.header(HDR_NOT_BEFORE)
        return float(nb) if nb else 0.0

    async def handle(self, msg: Message) -> str:
        """Process one message. The caller commits the offset after this returns.

        For retry topics, the caller should pause the partition until `not_before(msg)`
        when this returns DELAYED, then redeliver.
        """
        if msg.topic.endswith(".retry") and self.clock() < self.not_before(msg):
            return Outcome.DELAYED

        try:
            event = EventEnvelope.model_validate_json(msg.value)
        except Exception as exc:
            # Unparseable: retrying won't help.
            await self._send(f"{base_topic(msg.topic)}.dlq", msg, attempt=0, error=f"invalid envelope: {exc}")
            return Outcome.DLQ

        key = self._dedupe_key(event.eventId)
        if not await self.redis.set(key, "1", nx=True, ex=PROCESSED_TTL_SECONDS):
            return Outcome.DUPLICATE

        try:
            await self.handler(event)
            return Outcome.PROCESSED
        except Exception as exc:
            log.exception("event handler failed", extra={"eventId": event.eventId, "type": event.type})
            attempt = int(msg.header(HDR_ATTEMPT) or 0) + 1
            try:
                if attempt <= len(self.retry_delays):
                    await self._send(
                        f"{base_topic(msg.topic)}.retry",
                        msg,
                        attempt=attempt,
                        error=repr(exc),
                        not_before=self.clock() + self.retry_delays[attempt - 1],
                    )
                    outcome = Outcome.RETRY
                else:
                    await self._send(f"{base_topic(msg.topic)}.dlq", msg, attempt=attempt, error=repr(exc))
                    outcome = Outcome.DLQ
            finally:
                # The event was not applied; let the retry (or a redelivery) process it.
                await self.redis.delete(key)
            return outcome

    async def _send(
        self, topic: str, msg: Message, *, attempt: int, error: str, not_before: float | None = None
    ) -> None:
        headers = [
            (HDR_ATTEMPT, str(attempt).encode()),
            (HDR_ORIGINAL_TOPIC, base_topic(msg.topic).encode()),
            (HDR_ERROR, error[:500].encode()),
        ]
        if not_before is not None:
            headers.append((HDR_NOT_BEFORE, f"{not_before:.3f}".encode()))
        await self.producer.send_and_wait(topic, msg.value, key=msg.key, headers=headers)


def envelope_bytes(event: EventEnvelope) -> bytes:
    return json.dumps(event.model_dump(mode="json")).encode()
