"""media-worker: `media.jobs` (image.process) -> WebP files on the volume -> `media.results` (image.processed).

    python -m media_worker.worker

Layout (BSD §2): originals wait in `<MEDIA_ROOT>/incoming/`; results go to
`<MEDIA_ROOT>/public/products/<productId>/<fileId>[@800|@320].webp`, served by nginx at `/media/products/…`.
The file id is derived from the job id, so a redelivered job writes the same files and reports the same
result (catalog-svc attaches each fileId once). The original is deleted after the result is published.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from cimh_common.outbox import EventEnvelope, new_event

from .imaging import BackgroundRemover, ImageRejected, process, size_of

log = logging.getLogger("media.worker")
JOBS_TOPIC = "media.jobs"
RESULTS_TOPIC = "media.results"
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
SAFE_SOURCE = re.compile(r"^incoming/[A-Za-z0-9_-]{8,64}\.(jpg|png|webp)$")


class Producer(Protocol):
    async def send_and_wait(self, topic: str, value: bytes, key: bytes | None = None) -> Any: ...


@dataclass(frozen=True)
class Settings:
    media_root: Path
    url_prefix: str = "/media/products/"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            media_root=Path(os.environ.get("MEDIA_ROOT", "/srv/sia-data")),
            url_prefix=os.environ.get("MEDIA_URL_PREFIX", "/media/products/"),
        )


def file_id_for(job_id: str) -> str:
    return "IMG" + job_id.removeprefix("JOB")


class MediaWorker:
    def __init__(self, settings: Settings, producer: Producer, remover: BackgroundRemover | None = None) -> None:
        self.s = settings
        self.producer = producer
        self.remover = remover

    async def _publish(self, event: EventEnvelope, payload: dict[str, Any]) -> None:
        result = new_event(
            "image.processed", payload, correlation_id=event.correlationId or event.eventId, actor_id=event.actorId
        )
        # .envelope(): the published message is the plain envelope (no outbox bookkeeping fields such as
        # `attempts`), exactly what consumers validate with EventEnvelope (extra fields are refused).
        await self.producer.send_and_wait(
            RESULTS_TOPIC, result.envelope().model_dump_json().encode(), key=str(payload["productId"]).encode()
        )

    async def handle(self, event: EventEnvelope) -> None:
        if event.type != "image.process":
            return
        p = event.payload
        job_id, product_id, source = p.get("jobId"), p.get("productId"), p.get("sourcePath")
        if not (isinstance(job_id, str) and SAFE_ID.match(job_id)) or not (
            isinstance(product_id, str) and SAFE_ID.match(product_id)
        ):
            raise ValueError(f"image.process {event.eventId}: bad jobId/productId")  # -> DLQ
        base = {"jobId": job_id, "productId": product_id}
        if not (isinstance(source, str) and SAFE_SOURCE.match(source)):
            # Never follow a path that isn't a plain file name in incoming/ (no traversal, no other folders).
            await self._publish(event, {**base, "ok": False, "error": "invalid source path"})
            return
        src = self.s.media_root / source
        file_id = file_id_for(job_id)
        out_dir = self.s.media_root / "public" / "products" / product_id
        main = out_dir / f"{file_id}.webp"
        url = f"{self.s.url_prefix}{product_id}/{file_id}.webp"

        if not src.exists():
            if main.exists():  # redelivery after success: report the same result again
                w, h = size_of(main)
                await self._publish(event, {**base, "ok": True, "fileId": file_id, "url": url, "w": w, "h": h})
            else:
                await self._publish(event, {**base, "ok": False, "error": "source file missing"})
            return

        wants_bg = bool(p.get("removeBackground"))
        if wants_bg and self.remover is None:
            log.warning("background removal requested but not available here", extra={"jobId": job_id})
        try:
            # Pillow work is CPU-bound: keep the event loop (and the Kafka heartbeat) free.
            done = await asyncio.to_thread(
                process, src, out_dir, file_id, remove_background=wants_bg, remover=self.remover
            )
        except ImageRejected as exc:
            await self._publish(event, {**base, "ok": False, "error": f"not a usable image: {exc}"})
            src.unlink(missing_ok=True)
            return
        await self._publish(
            event, {**base, "ok": True, "fileId": file_id, "url": url, "w": done.width, "h": done.height}
        )
        src.unlink(missing_ok=True)


async def main() -> None:
    from aiokafka import AIOKafkaProducer
    from redis.asyncio import from_url

    from cimh_common.consume_loop import kafka_security, run_service_consumer
    from cimh_common.consumer import IdempotentConsumer
    from cimh_common.logging import configure_logging
    from cimh_common.settings import env_secret

    from .imaging import rembg_remover

    configure_logging("media-worker", os.environ.get("LOG_LEVEL", "INFO"))
    redis: Any = from_url(env_secret("REDIS_URL"))
    security = kafka_security(dict(os.environ))
    bootstrap = os.environ["KAFKA_BOOTSTRAP"]
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap, acks="all", **security)
    await producer.start()
    remover = rembg_remover() if os.environ.get("REMBG_ENABLED", "false").lower() == "true" else None
    log.info("media-worker ready", extra={"backgroundRemoval": remover is not None})
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    worker = MediaWorker(Settings.from_env(), producer, remover)
    handler = IdempotentConsumer("media", worker.handle, redis, producer)
    try:
        await run_service_consumer(
            group="media", topics=[JOBS_TOPIC], handler=handler, bootstrap=bootstrap, security=security, stop=stop
        )
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
