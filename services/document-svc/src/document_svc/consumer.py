"""document-consumer: renders PDFs from order events (TAD §4.5).

    python -m document_svc.consumer

  order.quoted              with cimhLineIds          -> cimh_quote
  order.quote_revised       with CIMH lines           -> cimh_quote (new version)
  order.agreement_requested                            -> agreement
  order.shipped             ship-to outside Barbados   -> commercial_invoice (customs)
  order.delivered           PAID -> invoice, PROBONO -> probono_invoice
Each produces document.generated, which order-svc attaches to the request and notification-svc may mail.
Delivery is at-least-once; the file id comes from the event id, so a redelivery rewrites the same file.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from typing import Any

from cimh_common.outbox import EventEnvelope
from cimh_common.redis_client import redis_client

from .service import DocumentService

log = logging.getLogger("document.consumer")
TOPICS = ["order.events"]
HOME_COUNTRY = "BB"


def make_handler(service: DocumentService) -> Any:
    async def handle(event: EventEnvelope) -> None:
        p, t = event.payload, event.type
        rid = p.get("orderId")
        if t not in ("order.quoted", "order.quote_revised", "order.agreement_requested", "order.shipped",
                     "order.delivered"):  # fmt: skip
            return
        if not isinstance(rid, str):
            raise ValueError(f"{t} {event.eventId} lacks orderId")  # -> DLQ
        if t == "order.quoted":
            ids = p.get("cimhLineIds") or []
            if ids:
                await service.generate("cimh_quote", rid, event, line_ids=list(ids))
        elif t == "order.quote_revised":
            req = await service.orders.request(rid)
            ids = [x["lineId"] for x in ((req or {}).get("cimhQuote") or {}).get("lines") or []]
            if ids:
                await service.generate("cimh_quote", rid, event, line_ids=ids)
        elif t == "order.agreement_requested":
            await service.generate("agreement", rid, event)
        elif t == "order.shipped":
            req = await service.orders.request(rid)
            country = ((req or {}).get("shipTo") or {}).get("country")
            if req and country and country != HOME_COUNTRY:
                await service.generate("commercial_invoice", rid, event)
        else:
            kind = "probono_invoice" if p.get("orderType") == "PROBONO" else "invoice"
            await service.generate(kind, rid, event)

    return handle


async def main() -> None:

    from cimh_common.consume_loop import kafka_security, run_service_consumer
    from cimh_common.consumer import IdempotentConsumer
    from cimh_common.logging import configure_logging
    from cimh_common.settings import env_secret

    from .clients import HttpOrders, KafkaPublisher
    from .config import Settings
    from .files import FileStore, NoScanner

    configure_logging("document-consumer", os.environ.get("LOG_LEVEL", "INFO"))
    s = Settings.from_env()
    redis: Any = redis_client(env_secret("REDIS_URL"))
    security = kafka_security(dict(os.environ))
    bootstrap = os.environ["KAFKA_BOOTSTRAP"]
    publisher = KafkaPublisher(bootstrap, security)
    await publisher.start()
    if not (s.identity_url and s.order_url and s.service_secret):
        raise RuntimeError("IDENTITY_URL, ORDER_URL and SERVICE_SECRET are required")
    orders = HttpOrders(identity_url=s.identity_url, order_url=s.order_url, secret=s.service_secret)
    service = DocumentService(FileStore(s.data_dir), orders, publisher, NoScanner())  # renders only; no uploads
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    handler = IdempotentConsumer("document", make_handler(service), redis, publisher._producer)
    try:
        await run_service_consumer(
            group="document", topics=TOPICS, handler=handler, bootstrap=bootstrap, security=security, stop=stop
        )
    finally:
        await publisher.stop()


if __name__ == "__main__":
    asyncio.run(main())
