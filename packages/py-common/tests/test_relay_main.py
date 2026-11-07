from __future__ import annotations

import asyncio
from pathlib import Path

import fakeredis.aioredis
import pytest

from cimh_common.locks import RedisLock
from cimh_common.outbox import OutboxRelay, topic_by_prefix
from cimh_common.relay_main import kafka_kwargs, parse_topics, run_leader

from .test_outbox_consumer import FakeCollection, FakeProducer, seed


def test_parse_topics() -> None:
    assert parse_topics("user.=identity.user.events, audit.=audit.events") == {
        "user.": "identity.user.events",
        "audit.": "audit.events",
    }
    with pytest.raises(ValueError, match="empty"):
        parse_topics("")


def test_kafka_kwargs_plain_and_sasl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KAFKA_BOOTSTRAP", "k1:9092")
    monkeypatch.setenv("RELAY_NAME", "identity")
    kw = kafka_kwargs()
    assert kw["acks"] == "all"
    assert kw["enable_idempotence"] is True
    assert "sasl_mechanism" not in kw
    (tmp_path / "pw").write_text("s3cret\n")
    monkeypatch.setenv("KAFKA_SASL_USER", "relay-identity")
    monkeypatch.setenv("KAFKA_SASL_PASSWORD_FILE", str(tmp_path / "pw"))
    kw = kafka_kwargs()
    assert kw["sasl_mechanism"] == "SCRAM-SHA-512"
    assert kw["sasl_plain_password"] == "s3cret"


class WatchableCollection(FakeCollection):
    async def watch(self, pipeline: list[dict[str, object]], full_document: str) -> object:
        async def gen() -> object:
            if False:
                yield {}

        return gen()


def test_run_leader_publishes_and_stops_when_lock_lost() -> None:
    async def run() -> None:
        redis = fakeredis.aioredis.FakeRedis()
        coll, prod = WatchableCollection(), FakeProducer()
        seed(coll, 2)
        lock = RedisLock(redis, "outbox-relay:test", ttl_ms=300)
        assert await lock.acquire()
        relay = OutboxRelay(coll, prod, topic_by_prefix({"order.": "order.events"}), sweep_interval=0.01)
        stop = asyncio.Event()
        task = asyncio.create_task(run_leader([relay], lock, [coll], stop))
        await asyncio.sleep(0.05)
        assert len(prod.sent) == 2
        await redis.delete(lock.key)  # someone else took over / lock expired
        await asyncio.wait_for(task, 2)  # leader notices and stops

    asyncio.run(run())
