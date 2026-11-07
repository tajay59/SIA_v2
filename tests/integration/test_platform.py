"""Integration: identity-svc, outbox relay, idempotent consumer and lock on real Mongo RS, Redis, Kafka.

What the unit tests (mongomock/fakeredis/fake producers) cannot show: real transactions and indexes, the
change-stream path of the relay, real Kafka keys/headers, Redis Lua scripts.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cimh_common.consumer import IdempotentConsumer, Message, Outcome
from cimh_common.locks import RedisLock
from cimh_common.outbox import OutboxRelay, new_event, outbox_push, topic_by_prefix

pytestmark = pytest.mark.integration

PW = "correct horse battery staple"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _read(bootstrap: str, topic: str, n: int, wait_s: float = 20.0) -> list[Any]:
    from aiokafka import AIOKafkaConsumer

    consumer = AIOKafkaConsumer(
        topic, bootstrap_servers=bootstrap, group_id=f"itest-{uuid.uuid4().hex}", auto_offset_reset="earliest"
    )
    await consumer.start()
    out: list[Any] = []
    try:
        deadline = asyncio.get_running_loop().time() + wait_s
        while len(out) < n and asyncio.get_running_loop().time() < deadline:
            batch = await consumer.getmany(timeout_ms=500)
            for records in batch.values():
                out.extend(records)
    finally:
        await consumer.stop()
    return out


def test_identity_register_verify_login_on_real_mongo_and_redis(stack: Any) -> None:
    from identity_svc.config import Settings
    from identity_svc.main import BASE, build_app

    db_name = f"itest_{uuid.uuid4().hex[:8]}"
    settings = Settings(mongo_url=stack.mongo_url, redis_url=stack.redis_url, db_name=db_name, hibp_enabled=False)

    async def no_breach(_: str) -> bool:
        return False

    app = build_app(settings, breach_check=no_breach, configure_logs=False)
    email = f"member.{uuid.uuid4().hex[:6]}@example.org"
    with TestClient(app, base_url="https://testserver") as c:  # runs the lifespan: real index creation
        r = c.post(
            BASE + "/auth/register",
            json={
                "firstname": "In",
                "lastname": "Tegration",
                "email": email,
                "password": PW,
                "organisationText": "Example Met",
                "country": "BB",
            },
        )
        assert r.status_code == 202, r.text
        r = c.post(
            BASE + "/auth/register",
            json={
                "firstname": "In",
                "lastname": "Tegration",
                "email": email,
                "password": PW,
                "organisationText": "Example Met",
                "country": "BB",
            },
        )
        assert r.status_code == 202  # no account enumeration

        svc = app.state.identity

        async def code() -> str:
            from pymongo import AsyncMongoClient

            db = AsyncMongoClient(stack.mongo_url)[db_name]
            acc = await db.accounts.find_one({"email": email})
            assert acc is not None
            assert [e["type"] for e in acc.get("outbox", [])][:1] == ["user.registered"]
            assert await db.accounts.count_documents({"email": email}) == 1  # unique index held
            doc = await db.temp.find_one({"accountId": acc["id"], "kind": "verify_email"})
            assert doc is not None
            assert "code" not in doc
            return str(svc.env.open(doc["codeEnc"], doc["id"]))

        verify_code = _run(code())
        r = c.post(BASE + "/auth/verify", json={"email": email, "code": verify_code})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "PENDING_APPROVAL"
        r = c.get("/health/ready")
        assert r.status_code == 200


def test_outbox_relay_change_stream_publishes_to_kafka_in_order(stack: Any) -> None:
    async def scenario() -> list[Any]:
        from aiokafka import AIOKafkaProducer
        from pymongo import AsyncMongoClient

        coll = AsyncMongoClient(stack.mongo_url, tz_aware=True)[f"itest_{uuid.uuid4().hex[:8]}"]["accounts"]
        await coll.insert_one({"id": "seed", "outbox": []})  # the collection must exist before watch()
        producer = AIOKafkaProducer(bootstrap_servers=stack.kafka, acks="all", enable_idempotence=True)
        await producer.start()
        relay = OutboxRelay(
            coll,
            producer,
            topic_by_prefix({"user.": "identity.user.events", "audit.": "audit.events"}),
            sweep_interval=60,
        )

        async def stream() -> Any:
            return await coll.watch(
                [{"$match": {"operationType": {"$in": ["insert", "update"]}}}], full_document="updateLookup"
            )

        task = asyncio.create_task(relay.run(stream))
        await asyncio.sleep(1.5)  # sweep done, change stream open
        acc_id = f"acc_{uuid.uuid4().hex[:8]}"
        e1 = new_event("user.registered", {"accountId": acc_id}, correlation_id="itest", actor_id=acc_id)
        e2 = new_event("user.verified", {"accountId": acc_id}, correlation_id="itest", actor_id=acc_id)
        e3 = new_event("audit.recorded", {"accountId": acc_id}, correlation_id="itest", actor_id=acc_id)
        await coll.insert_one({"id": acc_id, "outbox": [e.model_dump(mode="python") for e in (e1, e2)]})
        await coll.update_one({"id": acc_id}, outbox_push(e3))
        for _ in range(40):
            doc = await coll.find_one({"id": acc_id})
            if doc and not doc.get("outbox"):
                break
            await asyncio.sleep(0.25)
        relay.stop()
        await asyncio.wait_for(task, 10)
        await producer.stop()
        doc = await coll.find_one({"id": acc_id})
        assert doc is not None
        assert doc.get("outbox") == [], "outbox drained"
        users = await _read(stack.kafka, "identity.user.events", 2)
        audits = await _read(stack.kafka, "audit.events", 1)
        return [users, audits, acc_id]

    users, audits, acc_id = _run(scenario())
    mine = [r for r in users if r.key == acc_id.encode()]
    assert [json.loads(r.value)["type"] for r in mine] == ["user.registered", "user.verified"]
    assert any(json.loads(r.value)["type"] == "audit.recorded" for r in audits)


def test_idempotent_consumer_retry_then_dlq_and_duplicates(stack: Any) -> None:
    async def scenario() -> tuple[list[str], list[Any], list[Any]]:
        import redis.asyncio as aioredis
        from aiokafka import AIOKafkaProducer

        redis = aioredis.from_url(stack.redis_url)
        producer = AIOKafkaProducer(bootstrap_servers=stack.kafka)
        await producer.start()
        calls: list[str] = []

        async def failing(event: Any) -> None:
            calls.append(event.eventId)
            raise RuntimeError("boom")

        async def fine(event: Any) -> None:
            calls.append("ok:" + event.eventId)

        event = new_event("itest.happened", {"n": 1}, correlation_id="itest", actor_id="t")
        value = event.envelope().model_dump_json().encode()
        bad = IdempotentConsumer(f"g{uuid.uuid4().hex[:6]}", failing, redis, producer, retry_delays=(0, 0))
        outcomes = [await bad.handle(Message("itest.events", value, b"k1"))]
        retried = await _read(stack.kafka, "itest.events.retry", 1)
        msg = Message("itest.events.retry", retried[0].value, retried[0].key, list(retried[0].headers))
        outcomes.append(await bad.handle(msg))  # attempt 2 -> retry again
        retried = await _read(stack.kafka, "itest.events.retry", 2)
        last = retried[-1]
        outcomes.append(await bad.handle(Message("itest.events.retry", last.value, last.key, list(last.headers))))
        dlq = await _read(stack.kafka, "itest.events.dlq", 1)

        good = IdempotentConsumer(f"g{uuid.uuid4().hex[:6]}", fine, redis, producer)
        outcomes.append(await good.handle(Message("itest.events", value, b"k1")))
        outcomes.append(await good.handle(Message("itest.events", value, b"k1")))  # redelivery
        await producer.stop()
        await redis.aclose()
        return outcomes, retried, dlq

    outcomes, _retried, dlq = _run(scenario())
    assert outcomes == [Outcome.RETRY, Outcome.RETRY, Outcome.DLQ, Outcome.PROCESSED, Outcome.DUPLICATE]
    headers = dict(dlq[0].headers)
    assert headers["x-original-topic"] == b"itest.events"
    assert headers["x-attempt"] == b"3"
    assert dlq[0].key == b"k1"


def test_redis_lock_is_exclusive_and_token_safe(stack: Any) -> None:
    async def scenario() -> list[bool]:
        import redis.asyncio as aioredis

        r = aioredis.from_url(stack.redis_url)
        name = f"itest:{uuid.uuid4().hex[:6]}"
        a, b = RedisLock(r, name, ttl_ms=2000), RedisLock(r, name, ttl_ms=2000)
        res = [await a.acquire(), await b.acquire(), await b.extend(), await b.release(), await a.extend()]
        res += [await a.release(), await b.acquire()]
        await r.aclose()
        return res

    assert _run(scenario()) == [True, False, False, False, True, True, True]


def test_jobs_and_audit_consumer_on_real_stack(stack: Any) -> None:
    """Jobs' date comparisons and update operators on a real server; the audit consumer on real Kafka."""
    from datetime import UTC, datetime, timedelta

    from cimh_common.consume_loop import run_service_consumer
    from cimh_common.consumer import IdempotentConsumer
    from identity_svc.audit_consumer import make_handler
    from identity_svc.jobs import Jobs
    from identity_svc.store import Store

    async def scenario() -> tuple[dict[str, int], dict[str, Any] | None, int]:
        import redis.asyncio as aioredis
        from aiokafka import AIOKafkaProducer
        from pymongo import AsyncMongoClient

        db = AsyncMongoClient(stack.mongo_url, tz_aware=True)[f"itest_{uuid.uuid4().hex[:8]}"]
        store = Store(db)
        now = datetime.now(UTC)
        await store.accounts.insert_many(
            [
                {
                    "id": "USR_A",
                    "email": "a@x.org",
                    "status": "PENDING_VERIFICATION",
                    "version": 1,
                    "createdAt": now - timedelta(hours=30),
                    "updatedAt": now - timedelta(hours=30),
                    "outbox": [],
                },
                {
                    "id": "USR_B",
                    "email": "b@x.org",
                    "status": "PENDING_APPROVAL",
                    "version": 1,
                    "firstname": "B",
                    "lastname": "B",
                    "role": "user",
                    "isCimh": False,
                    "verifiedAt": now - timedelta(hours=50),
                    "createdAt": now - timedelta(days=3),
                    "updatedAt": now,
                    "outbox": [],
                },
                {
                    "id": "USR_C",
                    "email": "c@x.org",
                    "status": "REJECTED",
                    "version": 1,
                    "firstname": "C",
                    "lastname": "C",
                    "createdAt": now - timedelta(days=200),
                    "updatedAt": now - timedelta(days=100),
                    "outbox": [],
                },
            ]
        )
        counts = await Jobs(store).run_all(now)

        redis = aioredis.from_url(stack.redis_url)
        producer = AIOKafkaProducer(bootstrap_servers=stack.kafka)
        await producer.start()
        evt = new_event(
            "audit.recorded",
            {
                "action": "order.quoted",
                "entity": {"type": "request", "id": "ORD1"},
                "actor": {"id": "USR_S", "name": "Sam", "role": "staff"},
            },
            correlation_id="itest",
        )
        await producer.send_and_wait("audit.events", evt.envelope().model_dump_json().encode(), key=b"ORD1")
        stop = asyncio.Event()
        handler = IdempotentConsumer(f"identity-{uuid.uuid4().hex[:6]}", make_handler(store), redis, producer)
        task = asyncio.create_task(
            run_service_consumer(
                group=handler.group,
                topics=["audit.events"],
                handler=handler,
                bootstrap=stack.kafka,
                security={},
                stop=stop,
            )
        )
        entry = None
        for _ in range(120):
            entry = await store.audit.find_one({"id": f"AUD{evt.eventId}"})
            if entry:
                break
            await asyncio.sleep(0.5)
        stop.set()
        await asyncio.wait_for(task, 15)
        await producer.stop()
        await redis.aclose()
        remaining = await store.accounts.count_documents({"deletedAt": {"$exists": True}})
        return counts, entry, remaining

    counts, entry, tombstones = _run(scenario())
    assert counts == {"expired": 1, "reminded": 1, "purged": 1, "removed": 0}
    assert tombstones == 1  # waits for the relay to publish user.deleted
    assert entry is not None
    assert entry["action"] == "order.quoted"
