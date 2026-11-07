from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from typing import Any

import fakeredis.aioredis
import pytest

from cimh_common.consume_loop import consume, kafka_security
from cimh_common.consumer import HDR_NOT_BEFORE, IdempotentConsumer
from cimh_common.outbox import new_event

pytest.importorskip("aiokafka")


class FakeKafka:
    """getmany() hands out the queued batches once, then sets `stop`."""

    def __init__(self, batches: list[dict[Any, list[Any]]], stop: asyncio.Event) -> None:
        self.batches = batches
        self.stop = stop
        self.commits: list[dict[Any, int]] = []

    async def getmany(self, timeout_ms: int = 0) -> dict[Any, list[Any]]:
        if not self.batches:
            self.stop.set()
            return {}
        return self.batches.pop(0)

    async def commit(self, offsets: dict[Any, int]) -> None:
        self.commits.append(offsets)


class Producer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes]] = []

    async def send_and_wait(self, topic: str, value: bytes, key: bytes | None = None, headers: Any = None) -> None:
        self.sent.append((topic, value))


def record(topic: str, offset: int, value: bytes, headers: list[tuple[str, bytes]] | None = None) -> Any:
    return SimpleNamespace(topic=topic, partition=0, offset=offset, key=b"k", value=value, headers=headers or [])


def test_handles_commits_and_waits_for_retry_delay() -> None:
    async def scenario() -> tuple[list[str], list[int], list[float]]:
        stop = asyncio.Event()
        seen: list[str] = []

        async def handler(event: Any) -> None:
            seen.append(event.type)

        clock = [1000.0]
        slept: list[float] = []

        async def sleep(s: float) -> None:
            slept.append(s)
            clock[0] += s

        idem = IdempotentConsumer("g", handler, fakeredis.aioredis.FakeRedis(), Producer(), clock=lambda: clock[0])
        e1 = new_event("x.one", {}, correlation_id="c").envelope().model_dump_json().encode()
        e2 = new_event("x.two", {}, correlation_id="c").envelope().model_dump_json().encode()
        from aiokafka.structs import TopicPartition

        tp = TopicPartition("t.retry", 0)
        kafka = FakeKafka([{tp: [record("t", 5, e1), record("t.retry", 6, e2, [(HDR_NOT_BEFORE, b"1012.5")])]}], stop)
        await consume(kafka, idem, stop, sleep=sleep, clock=lambda: clock[0])
        return seen, [next(iter(c.values())) for c in kafka.commits], slept

    seen, commits, slept = asyncio.run(scenario())
    assert seen == ["x.one", "x.two"]
    assert commits == [6, 7]  # next offset after each handled record
    assert slept == [12.5]  # waited until the retry's not-before time


def test_kafka_security_reads_scram_settings(tmp_path: Any) -> None:
    assert kafka_security({}) == {}
    pw = tmp_path / "pw"
    pw.write_text("s3cret\n")
    sec = kafka_security({"KAFKA_SASL_USER": "identity", "KAFKA_SASL_PASSWORD_FILE": os.fspath(pw)})
    assert sec["security_protocol"] == "SASL_SSL"
    assert sec["sasl_mechanism"] == "SCRAM-SHA-512"
    assert sec["sasl_plain_username"] == "identity"
    assert sec["sasl_plain_password"] == "s3cret"
