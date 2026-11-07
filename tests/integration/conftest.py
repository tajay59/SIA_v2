"""Real MongoDB (replica set), Redis and Kafka in containers (TEST_STRATEGY §3, testcontainers).

    pytest -m integration --no-cov

One set of containers per session. Kafka runs single-node KRaft on a fixed host port so the advertised
listener is reachable from the test process.
"""

from __future__ import annotations

import asyncio
import socket
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest

pytest.importorskip("testcontainers")
from testcontainers.core.container import DockerContainer

TOPICS = ["identity.user.events", "audit.events", "itest.events", "itest.events.retry", "itest.events.dlq"]


@dataclass
class Stack:
    mongo_url: str
    redis_url: str
    kafka: str


def _until(ready: Callable[[], bool], seconds: float) -> None:
    """Poll a real readiness probe (log lines differ between image versions and CI runners)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if ready():
                return
        except Exception:  # noqa: S110 - container still starting
            pass
        time.sleep(1)
    raise TimeoutError(f"container not ready after {seconds}s")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _mongo() -> tuple[DockerContainer, str]:
    c = DockerContainer("mongo:8.0").with_command("--replSet rs0 --bind_ip_all").with_exposed_ports(27017)
    c.start()
    _until(lambda: c.exec(["mongosh", "--quiet", "--eval", "db.adminCommand('ping').ok"]).exit_code == 0, 120)
    c.exec(["mongosh", "--quiet", "--eval", "rs.initiate({_id:'rs0',members:[{_id:0,host:'localhost:27017'}]})"])
    url = f"mongodb://{c.get_container_host_ip()}:{c.get_exposed_port(27017)}/?directConnection=true"
    from pymongo import MongoClient

    client: MongoClient[dict[str, object]] = MongoClient(url)
    for _ in range(60):
        if client.admin.command("hello").get("isWritablePrimary"):
            break
        time.sleep(0.5)
    client.close()
    return c, url


def _redis() -> tuple[DockerContainer, str]:
    c = DockerContainer("redis:7.4-alpine").with_exposed_ports(6379)
    c.start()
    _until(lambda: c.exec(["redis-cli", "ping"]).output.strip() == b"PONG", 60)
    return c, f"redis://{c.get_container_host_ip()}:{c.get_exposed_port(6379)}/0"


def _kafka() -> tuple[DockerContainer, str]:
    port = _free_port()
    c = (
        DockerContainer("apache/kafka:3.9.0")
        .with_bind_ports(port, port)
        .with_env("KAFKA_NODE_ID", "1")
        .with_env("KAFKA_PROCESS_ROLES", "broker,controller")
        .with_env("KAFKA_LISTENERS", f"PLAINTEXT://:{port},CONTROLLER://:9093")
        .with_env("KAFKA_ADVERTISED_LISTENERS", f"PLAINTEXT://localhost:{port}")
        .with_env("KAFKA_CONTROLLER_LISTENER_NAMES", "CONTROLLER")
        .with_env("KAFKA_CONTROLLER_QUORUM_VOTERS", "1@localhost:9093")
        .with_env("KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR", "1")
        .with_env("KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR", "1")
        .with_env("KAFKA_TRANSACTION_STATE_LOG_MIN_ISR", "1")
        .with_env("KAFKA_AUTO_CREATE_TOPICS_ENABLE", "false")
    )
    c.start()
    probe = ["/opt/kafka/bin/kafka-topics.sh", "--bootstrap-server", f"localhost:{port}", "--list"]
    _until(lambda: c.exec(probe).exit_code == 0, 180)
    bootstrap = f"localhost:{port}"

    async def create() -> None:
        from aiokafka.admin import AIOKafkaAdminClient, NewTopic

        admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap)
        await admin.start()
        try:
            await admin.create_topics([NewTopic(t, num_partitions=1, replication_factor=1) for t in TOPICS])
        finally:
            await admin.close()

    asyncio.run(create())
    return c, bootstrap


@pytest.fixture(scope="session")
def stack() -> Iterator[Stack]:
    started: list[DockerContainer] = []
    try:
        m, mongo_url = _mongo()
        started.append(m)
        r, redis_url = _redis()
        started.append(r)
        k, kafka = _kafka()
        started.append(k)
        yield Stack(mongo_url, redis_url, kafka)
    finally:
        for c in started:
            c.stop()
