"""Transactional outbox (TAD §5, BSD OutboxEvent).

Write side: `outbox_push(event)` returns the `$push` fragment to add to the SAME update
that changes the entity, so state and event are saved atomically:

    await coll.update_one(
        {"_id": order_id, "status": "QUOTED", "version": v},
        {"$set": {...}, "$inc": {"version": 1}, **outbox_push(evt)},
    )

Relay side: `OutboxRelay` watches documents with pending events (change stream + 30 s
sweep), produces each to Kafka with key = entity id, then `$pull`s it. Events may be
published more than once; consumers are idempotent.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .ids import ulid

log = logging.getLogger(__name__)

MAX_ATTEMPTS_BEFORE_ALERT = 10


def _now() -> datetime:
    return datetime.now(UTC)


class EventEnvelope(BaseModel):
    """Kafka envelope: eventId, type, version, occurredAt, correlationId, actorId, payload."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    eventId: str = Field(default_factory=ulid)
    type: str
    version: int = 1
    occurredAt: datetime = Field(default_factory=_now)
    correlationId: str
    actorId: str | None = None
    payload: dict[str, Any]


class OutboxEvent(EventEnvelope):
    """Envelope + delivery bookkeeping stored in the entity's `outbox` array."""

    attempts: int = 0

    def envelope(self) -> EventEnvelope:
        return EventEnvelope(**self.model_dump(exclude={"attempts"}))


def new_event(
    type: str, payload: dict[str, Any], *, correlation_id: str, actor_id: str | None = None, version: int = 1
) -> OutboxEvent:
    return OutboxEvent(type=type, version=version, correlationId=correlation_id, actorId=actor_id, payload=payload)


def outbox_push(*events: OutboxEvent) -> dict[str, Any]:
    docs = [e.model_dump(mode="python") for e in events]
    return {"$push": {"outbox": {"$each": docs}}}


class Producer(Protocol):
    async def send_and_wait(self, topic: str, value: bytes, key: bytes | None = None) -> Any: ...


class Collection(Protocol):
    def find(self, filter: dict[str, Any], projection: dict[str, Any] | None = None) -> Any: ...
    async def update_one(self, filter: dict[str, Any], update: dict[str, Any]) -> Any: ...


TopicFor = Callable[[str], str]


class OutboxRelay:
    """Publishes pending outbox events for one collection.

    `topic_for(event_type)` maps e.g. "order.quoted" -> "order.events".
    `key_field` is the entity id field used as the Kafka key ("id" for legacy collections).
    Run one active relay per service (leader lock in Redis, see `RedisLock`).
    """

    def __init__(
        self,
        collection: Collection,
        producer: Producer,
        topic_for: TopicFor,
        *,
        key_field: str = "id",
        sweep_interval: float = 30.0,
        batch_size: int = 100,
    ) -> None:
        self.collection = collection
        self.producer = producer
        self.topic_for = topic_for
        self.key_field = key_field
        self.sweep_interval = sweep_interval
        self.batch_size = batch_size
        self._stop = asyncio.Event()

    async def publish_document(self, doc: dict[str, Any]) -> int:
        """Publish every pending event on one document, in order. Returns how many were sent."""
        sent = 0
        key = str(doc.get(self.key_field) or doc["_id"])
        for raw in list(doc.get("outbox") or []):
            event = OutboxEvent.model_validate(raw)
            try:
                await self.producer.send_and_wait(
                    self.topic_for(event.type),
                    event.envelope().model_dump_json().encode(),
                    key=key.encode(),
                )
            except Exception:
                log.exception("outbox publish failed", extra={"eventId": event.eventId, "type": event.type})
                await self.collection.update_one(
                    {"_id": doc["_id"], "outbox.eventId": event.eventId}, {"$inc": {"outbox.$.attempts": 1}}
                )
                if event.attempts + 1 >= MAX_ATTEMPTS_BEFORE_ALERT:
                    log.error("outbox event stuck", extra={"eventId": event.eventId})
                break  # keep per-entity order: don't send later events before this one
            await self.collection.update_one({"_id": doc["_id"]}, {"$pull": {"outbox": {"eventId": event.eventId}}})
            sent += 1
        return sent

    async def sweep(self) -> int:
        """Fallback scan for documents with pending events (sparse index `{outbox.0: 1}`)."""
        total = 0
        cursor = self.collection.find({"outbox.0": {"$exists": True}}, {"_id": 1, self.key_field: 1, "outbox": 1})
        count = 0
        async for doc in cursor:
            total += await self.publish_document(doc)
            count += 1
            if count >= self.batch_size:
                break
        return total

    async def run(self, change_stream: Callable[[], Awaitable[Any]] | None = None) -> None:
        """Sweep on an interval; if `change_stream` is given, also react to inserts/updates.

        `change_stream()` must return an async iterator of change events with `fullDocument`.
        """
        watcher: asyncio.Task[None] | None = None
        if change_stream is not None:
            watcher = asyncio.create_task(self._watch(change_stream))
        try:
            while not self._stop.is_set():
                try:
                    await self.sweep()
                except Exception:
                    log.exception("outbox sweep failed")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=self.sweep_interval)
        finally:
            if watcher:
                watcher.cancel()

    async def _watch(self, change_stream: Callable[[], Awaitable[Any]]) -> None:
        stream = await change_stream()
        async for change in stream:
            doc = change.get("fullDocument")
            if doc and doc.get("outbox"):
                try:
                    await self.publish_document(doc)
                except Exception:
                    log.exception("outbox publish from change stream failed")

    def stop(self) -> None:
        self._stop.set()


def topic_by_prefix(mapping: dict[str, str]) -> TopicFor:
    """topic_by_prefix({"order.": "order.events"}) -> function for OutboxRelay."""

    def topic_for(event_type: str) -> str:
        for prefix, topic in mapping.items():
            if event_type.startswith(prefix):
                return topic
        raise KeyError(f"no topic for event type {event_type!r}")

    return topic_for


def outbox_backlog_hook(metrics: Any, collections: dict[str, Any], *, now: Callable[[], datetime] = _now) -> Any:
    """Scrape-time gauges of what the relay has not published yet (alert `OutboxBacklog`).

    Reported by the owning service, not the relay, so a stopped relay still shows up. Uses the sparse
    `{outbox.0: 1}` index and looks at no more than 10,000 documents.
    """

    async def hook() -> None:
        for name, coll in collections.items():
            pipeline = [
                {"$match": {"outbox.0": {"$exists": True}}},
                {"$limit": 10_000},
                {"$project": {"n": {"$size": "$outbox"}, "t": {"$min": "$outbox.occurredAt"}}},
                {"$group": {"_id": None, "n": {"$sum": "$n"}, "t": {"$min": "$t"}}},
            ]
            rows = await (await coll.aggregate(pipeline, maxTimeMS=2000)).to_list(1)
            pending = rows[0]["n"] if rows else 0
            oldest = rows[0]["t"] if rows else None
            age = 0.0
            if isinstance(oldest, datetime):
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=UTC)
                age = max(0.0, (now() - oldest).total_seconds())
            metrics.outbox_pending.labels(metrics.service, name).set(pending)
            metrics.outbox_oldest.labels(metrics.service, name).set(age)

    return hook
