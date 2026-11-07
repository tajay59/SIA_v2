"""identity-svc internal API with a cached service token (used to check email-list members, C8).

A short sync call is acceptable here: it only happens when an admin saves the email lists (TAD §6 lists the
service-to-service calls; this one is admin-only and rare).
"""

from __future__ import annotations

import time
from typing import Any

import httpx


class IdentityClient:
    def __init__(
        self,
        base_url: str,
        secret: str,
        *,
        service: str = "catalog",
        timeout: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base = base_url.rstrip("/") + "/api/identity/v1"
        self.secret = secret
        self.service = service
        self.timeout = timeout
        self.transport = transport
        self._token: str | None = None
        self._until = 0.0

    async def _service_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.monotonic() < self._until:
            return self._token
        r = await client.post(
            f"{self.base}/internal/service-token", json={"service": self.service, "secret": self.secret}
        )
        r.raise_for_status()
        body = r.json()
        self._token = str(body["token"])
        self._until = time.monotonic() + max(30, int(body.get("expiresIn", 300)) - 30)
        return self._token

    async def account(self, account_id: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            token = await self._service_token(client)
            r = await client.get(
                f"{self.base}/internal/accounts/{account_id}", headers={"Authorization": f"Bearer {token}"}
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            return data
