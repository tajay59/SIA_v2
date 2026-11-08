"""notification-consumer: every email (TAD §4.6, APD §7).

    python -m notification_svc.consumer

Consumes identity.user.events, order.events, document.events, inventory.stock.events (group `notification`).
Dedupe by eventId (IdempotentConsumer) plus a per-recipient sent mark (handlers.py): each email goes out once per
event. A failed send (SMTP or a dependency down) raises, so the event goes to the retry topic and, after the
last retry, to the DLQ (alert). Codes are claimed from identity once and never logged.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from typing import Any

from cimh_common.outbox import EventEnvelope

from .handlers import Notifier

log = logging.getLogger("notification.consumer")
TOPICS = ["identity.user.events", "order.events", "document.events", "inventory.stock.events"]


def make_handler(notifier: Notifier) -> Any:
    async def handle(event: EventEnvelope) -> None:
        await notifier.handle(event)

    return handle


async def main() -> None:
    from aiokafka import AIOKafkaProducer
    from redis.asyncio import from_url

    from cimh_common.consume_loop import kafka_security, run_service_consumer
    from cimh_common.consumer import IdempotentConsumer
    from cimh_common.logging import configure_logging
    from cimh_common.settings import env_secret

    from .clients import HttpDirectory, Settings, SmtpMailer

    configure_logging("notification-consumer", os.environ.get("LOG_LEVEL", "INFO"))
    s = Settings.from_env()
    if not s.service_secret:
        raise RuntimeError("SERVICE_SECRET is required (codes, accounts, email lists)")
    redis: Any = from_url(env_secret("REDIS_URL"))
    security = kafka_security(dict(os.environ))
    bootstrap = os.environ["KAFKA_BOOTSTRAP"]
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap, acks="all", **security)
    await producer.start()
    notifier = Notifier(s, HttpDirectory(s, redis), SmtpMailer(s), redis)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    handler = IdempotentConsumer("notification", make_handler(notifier), redis, producer)
    try:
        await run_service_consumer(
            group="notification",
            topics=TOPICS,
            handler=handler,
            bootstrap=bootstrap,
            security=security,
            stop=stop,
            start_at="latest",  # a new group must not mail the retained history
        )
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
