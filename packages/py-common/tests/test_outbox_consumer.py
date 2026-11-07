from __future__ import annotations

import asyncio
import json
from typing import Any

import fakeredis.aioredis

from cimh_common.consumer import HDR_ATTEMPT, IdempotentConsumer, Message, Outcome
from cimh_common.locks import RedisLock
from cimh_common.outbox import EventEnvelope, OutboxRelay, new_event, outbox_push, topic_by_prefix


class FakeProducer:
    def __init__(self, fail_times: int = 0) -> None:
        self.sent: list[tuple[str, bytes, bytes | None, list[tuple[str, bytes]] | None]] = []
        self.fail_times = fail_times

    async def send_and_wait(
        self, topic: str, value: bytes, key: bytes | None = None, headers: list[tuple[str, bytes]] | None = None
    ) -> None:
        if self.fail_times:
            self.fail_times -= 1
            raise ConnectionError("kafka down")
        self.sent.append((topic, value, key, headers))


class FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs

    def __aiter__(self) -> FakeCursor:
        self._it = iter(self.docs)
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeCollection:
    """Just enough of a Mongo collection for the relay."""

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def find(self, filter: dict[str, Any], projection: dict[str, Any] | None = None) -> FakeCursor:
        return FakeCursor([d for d in self.docs.values() if d.get("outbox")])

    async def update_one(self, filter: dict[str, Any], update: dict[str, Any]) -> None:
        doc = self.docs[filter["_id"]]
        if "$pull" in update:
            eid = update["$pull"]["outbox"]["eventId"]
            doc["outbox"] = [e for e in doc["outbox"] if e["eventId"] != eid]
        if "$inc" in update:
            eid = filter["outbox.eventId"]
            for e in doc["outbox"]:
                if e["eventId"] == eid:
                    e["attempts"] += 1


TOPICS = topic_by_prefix({"order.": "order.events", "catalog.": "catalog.product.events"})


def seed(coll: FakeCollection, n: int = 2) -> list[str]:
    events = [new_event(f"order.e{i}", {"i": i}, correlation_id="c1", actor_id="USR1") for i in range(n)]
    coll.docs["d1"] = {"_id": "d1", "id": "ORD1", **{"outbox": outbox_push(*events)["$push"]["outbox"]["$each"]}}
    return [e.eventId for e in events]


def test_outbox_push_shape() -> None:
    e = new_event("order.submitted", {"x": 1}, correlation_id="c")
    frag = outbox_push(e)
    doc = frag["$push"]["outbox"]["$each"][0]
    assert doc["type"] == "order.submitted"
    assert doc["attempts"] == 0
    assert len(doc["eventId"]) == 26


def test_relay_publishes_in_order_with_entity_key() -> None:
    coll, prod = FakeCollection(), FakeProducer()
    ids = seed(coll)
    sent = asyncio.run(OutboxRelay(coll, prod, TOPICS).sweep())
    assert sent == 2
    assert [json.loads(v)["eventId"] for _, v, _, _ in prod.sent] == ids
    assert all(t == "order.events" and k == b"ORD1" for t, _, k, _ in prod.sent)
    assert "attempts" not in json.loads(prod.sent[0][1])
    assert coll.docs["d1"]["outbox"] == []


def test_relay_stops_at_failure_to_keep_order() -> None:
    coll, prod = FakeCollection(), FakeProducer(fail_times=1)
    seed(coll)
    relay = OutboxRelay(coll, prod, TOPICS)
    assert asyncio.run(relay.sweep()) == 0
    assert len(coll.docs["d1"]["outbox"]) == 2
    assert coll.docs["d1"]["outbox"][0]["attempts"] == 1
    assert asyncio.run(relay.sweep()) == 2


def test_topic_mapping_unknown() -> None:
    try:
        TOPICS("weird.event")
    except KeyError:
        return
    raise AssertionError


def msg(event: EventEnvelope, topic: str = "order.events", attempt: int | None = None) -> Message:
    headers = [(HDR_ATTEMPT, str(attempt).encode())] if attempt is not None else None
    return Message(topic=topic, value=event.model_dump_json().encode(), key=b"ORD1", headers=headers)


def test_consumer_dedupes() -> None:
    async def run() -> None:
        seen: list[str] = []

        async def handler(e: EventEnvelope) -> None:
            seen.append(e.eventId)

        redis = fakeredis.aioredis.FakeRedis()
        c = IdempotentConsumer("notification-order.events", handler, redis, FakeProducer())
        ev = new_event("order.submitted", {}, correlation_id="c").envelope()
        assert await c.handle(msg(ev)) == Outcome.PROCESSED
        assert await c.handle(msg(ev)) == Outcome.DUPLICATE
        assert seen == [ev.eventId]

    asyncio.run(run())


def test_consumer_retry_then_dlq() -> None:
    async def run() -> None:
        async def handler(e: EventEnvelope) -> None:
            raise ValueError("boom")

        redis = fakeredis.aioredis.FakeRedis()
        prod = FakeProducer()
        now = [1000.0]
        c = IdempotentConsumer("g", handler, redis, prod, clock=lambda: now[0])
        ev = new_event("order.submitted", {}, correlation_id="c").envelope()

        assert await c.handle(msg(ev)) == Outcome.RETRY
        topic, _, _, headers = prod.sent[-1]
        assert topic == "order.events.retry"
        hdr = dict(headers or [])
        assert hdr["x-attempt"] == b"1"
        assert float(hdr["x-not-before"]) == 1060.0

        retry_msg = Message("order.events.retry", ev.model_dump_json().encode(), b"ORD1", headers)
        assert await c.handle(retry_msg) == Outcome.DELAYED
        now[0] = 1061.0
        assert await c.handle(retry_msg) == Outcome.RETRY  # attempt 2
        assert await c.handle(msg(ev, "order.events.retry", attempt=2)) == Outcome.RETRY  # attempt 3
        assert await c.handle(msg(ev, "order.events.retry", attempt=3)) == Outcome.DLQ
        assert prod.sent[-1][0] == "order.events.dlq"

    asyncio.run(run())


def test_consumer_bad_envelope_goes_to_dlq() -> None:
    async def run() -> None:
        async def handler(e: EventEnvelope) -> None:
            raise AssertionError("must not be called")

        prod = FakeProducer()
        c = IdempotentConsumer("g", handler, fakeredis.aioredis.FakeRedis(), prod)
        assert await c.handle(Message("order.events", b"{not json")) == Outcome.DLQ
        assert prod.sent[0][0] == "order.events.dlq"

    asyncio.run(run())


def test_redis_lock() -> None:
    async def run() -> None:
        r = fakeredis.aioredis.FakeRedis()
        a, b = RedisLock(r, "relay-order"), RedisLock(r, "relay-order")
        assert await a.acquire()
        assert not await b.acquire()
        assert not await b.release()  # b can't release a's lock
        assert await a.extend()
        assert await a.release()
        assert await b.acquire()

    asyncio.run(run())
