"""Sync HTTP calls order-svc makes (TAD §4.5 "immediate questions"), all with a service token from identity-svc.

  catalog    POST /internal/products/summaries    product snapshots, cost, Pro Bono limits
             GET  /internal/fees                   admin fee (BBD)
  inventory  POST /internal/availability           full-quantity check when quoting starts
             POST /internal/picks                  pick a unit reserved for a request
  identity   GET  /internal/accounts/{id}          names + organisation at submission, file-access checks

Any transport error or 5xx becomes 503 DEPENDENCY_UNAVAILABLE; 4xx answers from inventory picks are passed on.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Protocol

import httpx

from cimh_common.errors import ProblemError


class Deps(Protocol):
    async def products(self, ids: list[str]) -> list[dict[str, Any]]: ...
    async def admin_fee(self) -> Decimal: ...
    async def availability(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
    async def pick(self, unit: str, order_id: str, picked_by: str, key: str) -> dict[str, Any]: ...
    async def account(self, account_id: str) -> dict[str, Any] | None: ...


def _unavailable(what: str) -> ProblemError:
    return ProblemError(503, "DEPENDENCY_UNAVAILABLE", f"{what} is unavailable; try again shortly")


class HttpDeps:
    def __init__(
        self,
        *,
        identity_url: str,
        catalog_url: str,
        inventory_url: str,
        secret: str,
        timeout: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.identity = identity_url.rstrip("/") + "/api/identity/v1"
        self.catalog = catalog_url.rstrip("/") + "/api/catalog/v1/internal"
        self.inventory = inventory_url.rstrip("/") + "/api/inventory/v1/internal"
        self.secret = secret
        self.timeout = timeout
        self.transport = transport
        self._token: str | None = None
        self._until = 0.0

    async def _auth(self, client: httpx.AsyncClient) -> dict[str, str]:
        if not self._token or time.monotonic() >= self._until:
            r = await client.post(
                self.identity + "/internal/service-token", json={"service": "order", "secret": self.secret}
            )
            r.raise_for_status()
            body = r.json()
            self._token = str(body["token"])
            self._until = time.monotonic() + max(30, int(body.get("expiresIn", 300)) - 30)
        return {"Authorization": f"Bearer {self._token}"}

    async def _call(self, what: str, method: str, url: str, *, ok404: bool = False, **kw: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                headers = {**kw.pop("headers", {}), **await self._auth(client)}
                r = await client.request(method, url, headers=headers, **kw)
        except httpx.HTTPError as exc:
            raise _unavailable(what) from exc
        if r.status_code >= 500 or (r.status_code >= 400 and not (ok404 and r.status_code == 404)):
            if r.status_code < 500 and what == "inventory":
                return r  # caller maps inventory's 4xx (unit not reserved, already picked...)
            raise _unavailable(what)
        return r

    async def products(self, ids: list[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for i in range(0, len(ids), 200):
            r = await self._call(
                "catalog", "POST", self.catalog + "/products/summaries", json={"ids": ids[i : i + 200]}
            )
            out += list(r.json()["items"])
        return out

    async def admin_fee(self) -> Decimal:
        r = await self._call("catalog", "GET", self.catalog + "/fees")
        for t in r.json().get("types", []):
            if t.get("name") == "admin":
                return Decimal(str(t.get("fee") or "0"))
        return Decimal("0")

    async def availability(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        r = await self._call("inventory", "POST", self.inventory + "/availability", json={"lines": lines})
        if r.status_code >= 400:
            raise _unavailable("inventory")
        return list(r.json()["lines"])

    async def pick(self, unit: str, order_id: str, picked_by: str, key: str) -> dict[str, Any]:
        r = await self._call(
            "inventory",
            "POST",
            self.inventory + "/picks",
            json={"unit": unit, "orderId": order_id, "pickedBy": picked_by},
            headers={"Idempotency-Key": key},
        )
        if r.status_code >= 400:
            err = r.json() if r.headers.get("content-type", "").endswith("json") else {}
            raise ProblemError(r.status_code, err.get("code"), err.get("detail") or "Pick refused by inventory")
        out: dict[str, Any] = r.json()
        return out

    async def account(self, account_id: str) -> dict[str, Any] | None:
        r = await self._call("identity", "GET", self.identity + f"/internal/accounts/{account_id}", ok404=True)
        if r.status_code == 404:
            return None
        body: dict[str, Any] = r.json()
        return body
