"""Calls document-svc makes: order-svc over HTTP (service token from identity-svc), Kafka for document.events.

  order  GET  /internal/requests/{id}/access?user=   may the user see / act on the request, and its status
         GET  /internal/requests/{id}                staff view, for rendering PDFs
         POST /internal/requests/{id}/files          attach an upload at once (so "Accept" works immediately)

Transport errors and 5xx become 503 DEPENDENCY_UNAVAILABLE.

document-svc owns no collection, so it has no outbox: events are published straight to Kafka (acks=all) and the
caller decides what a failed publish means (upload: refuse and remove the file; generated PDF: the consumer
retries the order event).
"""

from __future__ import annotations

import time
from typing import Any, Protocol

import httpx

from cimh_common.consumer import envelope_bytes
from cimh_common.errors import ProblemError
from cimh_common.outbox import EventEnvelope

TOPIC = "document.events"
AUDIT_TOPIC = "audit.events"


def unavailable(what: str) -> ProblemError:
    return ProblemError(503, "DEPENDENCY_UNAVAILABLE", f"{what} is unavailable; try again shortly")


class Orders(Protocol):
    async def access(self, rid: str, user: str) -> dict[str, Any] | None: ...
    async def request(self, rid: str) -> dict[str, Any] | None: ...
    async def attach(self, rid: str, file: dict[str, Any]) -> None: ...


class Publisher(Protocol):
    async def publish(self, topic: str, key: str, event: EventEnvelope) -> None: ...


class HttpOrders:
    def __init__(
        self,
        *,
        identity_url: str,
        order_url: str,
        secret: str,
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.identity = identity_url.rstrip("/") + "/api/identity/v1"
        self.orders = order_url.rstrip("/") + "/api/orders/v1/internal/requests"
        self.secret = secret
        self.timeout = timeout
        self.transport = transport
        self._token: str | None = None
        self._until = 0.0

    async def _auth(self, client: httpx.AsyncClient) -> dict[str, str]:
        if not self._token or time.monotonic() >= self._until:
            r = await client.post(
                self.identity + "/internal/service-token", json={"service": "document", "secret": self.secret}
            )
            r.raise_for_status()
            body = r.json()
            self._token = str(body["token"])
            self._until = time.monotonic() + max(30, int(body.get("expiresIn", 300)) - 30)
        return {"Authorization": f"Bearer {self._token}"}

    async def _call(self, method: str, url: str, **kw: Any) -> httpx.Response | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                r = await client.request(method, url, headers=await self._auth(client), **kw)
        except httpx.HTTPError as exc:
            raise unavailable("order-svc") from exc
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise unavailable("order-svc")
        return r

    async def access(self, rid: str, user: str) -> dict[str, Any] | None:
        r = await self._call("GET", f"{self.orders}/{rid}/access", params={"user": user})
        return None if r is None else dict(r.json())

    async def request(self, rid: str) -> dict[str, Any] | None:
        r = await self._call("GET", f"{self.orders}/{rid}")
        return None if r is None else dict(r.json())

    async def attach(self, rid: str, file: dict[str, Any]) -> None:
        body = {k: file[k] for k in ("id", "kind", "name", "mime", "size")}
        await self._call("POST", f"{self.orders}/{rid}/files", json=body)


class KafkaPublisher:
    def __init__(self, bootstrap: str, security: dict[str, Any]) -> None:
        self.bootstrap, self.security = bootstrap, security
        self._producer: Any = None

    async def start(self) -> None:
        from aiokafka import AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap, acks="all", enable_idempotence=True, **self.security
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()

    async def publish(self, topic: str, key: str, event: EventEnvelope) -> None:
        if self._producer is None:
            raise unavailable("Kafka")
        try:
            await self._producer.send_and_wait(topic, envelope_bytes(event), key=key.encode())
        except Exception as exc:  # any producer error: the caller must not report success
            raise unavailable("Kafka") from exc
