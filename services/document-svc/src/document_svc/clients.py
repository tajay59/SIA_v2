"""Calls document-svc makes: order-svc over HTTP (service token from identity-svc), Kafka for document.events.

  order  GET  /internal/requests/{id}/access?user=   may the user see / act on the request, and its status
         GET  /internal/requests/{id}                staff view, for rendering PDFs
         POST /internal/requests/{id}/files          attach an upload at once (so "Accept" works immediately)
         GET  /internal/requests/{id}/quote-preview  the request as Send quote would leave it (agreement preview)
         PUT  /internal/requests/{id}/invoices/{kind}       record a rendered invoice as the current one (new / rev)
         POST /internal/requests/{id}/invoices/{kind}/void  withdraw the current invoice
         GET  /internal/invoice-numbers/next?kind=          the builder's suggested number

Transport errors and 5xx become 503 DEPENDENCY_UNAVAILABLE. The quote preview passes order-svc's 409/422 on: they
say why the draft can't be sent yet, which is what staff need to read. The invoice calls pass order-svc's
403/409 on (INVOICE_EXISTS, INVOICE_NUMBER_TAKEN, INVOICE_LOCKED, VERSION_CONFLICT) and turn 404 into one.

document-svc owns no collection, so it has no outbox: events are published straight to Kafka (acks=all) and the
caller decides what a failed publish means (upload: refuse and remove the file; generated PDF: the consumer
retries the order event).
"""

from __future__ import annotations

import time
from typing import Any, Protocol

import httpx

from cimh_common.consumer import envelope_bytes
from cimh_common.errors import ProblemError, not_found
from cimh_common.outbox import EventEnvelope

TOPIC = "document.events"
AUDIT_TOPIC = "audit.events"


def unavailable(what: str) -> ProblemError:
    return ProblemError(503, "DEPENDENCY_UNAVAILABLE", f"{what} is unavailable; try again shortly")


class Orders(Protocol):
    async def access(self, rid: str, user: str) -> dict[str, Any] | None: ...
    async def request(self, rid: str) -> dict[str, Any] | None: ...
    async def attach(self, rid: str, file: dict[str, Any]) -> None: ...
    async def quote_preview(self, rid: str) -> dict[str, Any] | None: ...
    async def record_invoice(self, rid: str, kind: str, body: dict[str, Any]) -> dict[str, Any]: ...
    async def void_invoice(self, rid: str, kind: str, body: dict[str, Any]) -> dict[str, Any]: ...
    async def next_invoice_number(self, kind: str) -> str | None: ...


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
        self.internal = order_url.rstrip("/") + "/api/orders/v1/internal"
        self.orders = self.internal + "/requests"
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

    async def _call(self, method: str, url: str, *, relay: tuple[int, ...] = (), **kw: Any) -> httpx.Response | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                r = await client.request(method, url, headers=await self._auth(client), **kw)
        except httpx.HTTPError as exc:
            raise unavailable("order-svc") from exc
        if r.status_code == 404:
            return None
        if r.status_code in relay:
            raise _relayed(r)
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
        if file.get("quoteVersion") is not None:
            body["quoteVersion"] = file["quoteVersion"]
        await self._call("POST", f"{self.orders}/{rid}/files", json=body)

    async def quote_preview(self, rid: str) -> dict[str, Any] | None:
        r = await self._call("GET", f"{self.orders}/{rid}/quote-preview", relay=(409, 422))
        return None if r is None else dict(r.json())

    async def record_invoice(self, rid: str, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        r = await self._call("PUT", f"{self.orders}/{rid}/invoices/{kind}", json=body, relay=INVOICE_RELAY)
        if r is None:
            raise not_found("Request not found")
        return dict(r.json())

    async def void_invoice(self, rid: str, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        r = await self._call("POST", f"{self.orders}/{rid}/invoices/{kind}/void", json=body, relay=INVOICE_RELAY)
        if r is None:
            raise not_found("This request has no invoice of that kind")
        return dict(r.json())

    async def next_invoice_number(self, kind: str) -> str | None:
        r = await self._call("GET", f"{self.internal}/invoice-numbers/next", params={"kind": kind})
        number = None if r is None else r.json().get("number")
        return number if isinstance(number, str) else None


INVOICE_RELAY = (403, 409, 422)


def _relayed(r: httpx.Response) -> ProblemError:
    """order-svc's own problem (code, detail, field errors), returned to the caller unchanged."""
    try:
        body = r.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    errors = body.get("errors")
    return ProblemError(
        r.status_code,
        body.get("code") if isinstance(body.get("code"), str) else None,
        body.get("detail") if isinstance(body.get("detail"), str) else None,
        errors=[e for e in errors if isinstance(e, dict)] if isinstance(errors, list) else None,
    )


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
