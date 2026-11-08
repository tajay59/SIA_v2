"""Label PDFs from document-svc (POST /internal/labels). Optional: without DOCUMENT_URL, or when document-svc is
down, /labels still allocates the units and returns fileId null (the SIA screen draws the QR labels itself)."""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

import httpx

log = logging.getLogger("inventory.documents")


class LabelPdfs(Protocol):
    async def render(self, product_id: str, name: str | None, barcodes: list[str]) -> str | None: ...


class DocumentLabels:
    def __init__(
        self,
        document_url: str,
        identity_url: str,
        secret: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = document_url.rstrip("/") + "/api/documents/v1/internal/labels"
        self.token_url = identity_url.rstrip("/") + "/api/identity/v1/internal/service-token"
        self.secret, self.timeout, self.transport = secret, timeout, transport
        self._token: str | None = None
        self._until = 0.0

    async def render(self, product_id: str, name: str | None, barcodes: list[str]) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                if not self._token or time.monotonic() >= self._until:
                    t = await client.post(self.token_url, json={"service": "inventory", "secret": self.secret})
                    t.raise_for_status()
                    body = t.json()
                    self._token = str(body["token"])
                    self._until = time.monotonic() + max(30, int(body.get("expiresIn", 300)) - 30)
                r = await client.post(
                    self.url,
                    json={"productId": product_id, "productName": name, "barcodes": barcodes},
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                r.raise_for_status()
                out: Any = r.json().get("id")
                return str(out) if out else None
        except (httpx.HTTPError, ValueError):
            log.warning("label PDF unavailable", extra={"productId": product_id})
            return None
