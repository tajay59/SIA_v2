"""Sites, locations and shelves: stored in `misc` by catalog-svc, read and written through its internal API.

TAD §4.3: inventory-svc owns the behaviour, catalog-svc owns the collection (existing names are kept). Reads
are cached in Redis by the service layer; every place write goes through inventory-svc, which refreshes the
cache, so a stale entry can only come from a direct DB edit (and expires after PLACE_CACHE_SECONDS).
"""

from __future__ import annotations

import builtins
import time
from typing import Any, Protocol

import httpx

from cimh_common.errors import ProblemError


class Places(Protocol):
    async def list(
        self,
        *,
        kind: str | None = None,
        site: str | None = None,
        location: str | None = None,
        barcode: str | None = None,
    ) -> list[dict[str, Any]]: ...

    async def put(self, place: dict[str, Any]) -> dict[str, Any]: ...

    async def products(self, ids: builtins.list[str]) -> builtins.list[dict[str, Any]]:
        """catalog /internal/products/summaries: products that exist (missing ids omitted)."""
        ...


class CatalogPlaces:
    def __init__(
        self,
        catalog_url: str,
        identity_url: str,
        secret: str,
        *,
        timeout: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.catalog = catalog_url.rstrip("/") + "/api/catalog/v1/internal"
        self.base = self.catalog + "/places"
        self.token_url = identity_url.rstrip("/") + "/api/identity/v1/internal/service-token"
        self.secret = secret
        self.timeout = timeout
        self.transport = transport
        self._token: str | None = None
        self._until = 0.0

    async def _auth(self, client: httpx.AsyncClient) -> dict[str, str]:
        if not self._token or time.monotonic() >= self._until:
            r = await client.post(self.token_url, json={"service": "inventory", "secret": self.secret})
            r.raise_for_status()
            body = r.json()
            self._token = str(body["token"])
            self._until = time.monotonic() + max(30, int(body.get("expiresIn", 300)) - 30)
        return {"Authorization": f"Bearer {self._token}"}

    async def _call(self, method: str, url: str | None = None, **kw: Any) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                r = await client.request(method, url or self.base, headers=await self._auth(client), **kw)
                r.raise_for_status()
                return r.json()
        except httpx.HTTPError as exc:
            raise ProblemError(503, "DEPENDENCY_UNAVAILABLE", "Places are unavailable (catalog-svc)") from exc

    async def list(
        self,
        *,
        kind: str | None = None,
        site: str | None = None,
        location: str | None = None,
        barcode: str | None = None,
    ) -> list[dict[str, Any]]:
        params = {k: v for k, v in {"kind": kind, "site": site, "location": location, "barcode": barcode}.items() if v}
        body = await self._call("GET", params=params)
        return list(body["items"])

    async def put(self, place: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = await self._call("PUT", json=place)
        return body

    async def products(self, ids: builtins.list[str]) -> builtins.list[dict[str, Any]]:
        body = await self._call("POST", self.catalog + "/products/summaries", json={"ids": ids})
        return list(body["items"])
