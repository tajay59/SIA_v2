"""HTTP + WebSocket layer for announcements (docs/api/catalog.openapi.yaml, docs/api/push.asyncapi.yaml).

catalog-svc serves `public` + `admin`; catalog-push serves `public` + `push` (plan 2026-11-23, D9).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from cimh_common.auth import ACCESS_COOKIE, Principal, cookie_values
from cimh_common.authz import optional_principal, require_admin
from cimh_common.errors import ProblemError, forbidden, unauthorized

from .announcements import AnnouncementService, Client, PushHub
from .api import IfMatch, cid, if_match, with_etag

PING_SECONDS = 25
MAX_FRAME = 1024
SEND_TIMEOUT = 5.0


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


# Strict bodies, but a date arrives as an ISO string with an offset (strict would refuse any string).
When = Annotated[AwareDatetime, Field(strict=False)]


class LinkIn(Strict):
    """A web address (label required) or a product (label defaults to the product name)."""

    label: str | None = Field(default=None, min_length=1, max_length=40)
    url: str | None = Field(default=None, min_length=1, max_length=500)
    productId: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")

    @model_validator(mode="after")
    def one_target(self) -> LinkIn:
        if (self.url is None) == (self.productId is None):
            raise ValueError("give either url or productId")
        return self


class TtlIn(Strict):
    preset: Literal["1h", "1d", "7d", "30d"] | None = None
    until: When | None = None

    @model_validator(mode="after")
    def one_of(self) -> TtlIn:
        if (self.preset is None) == (self.until is None):
            raise ValueError("give either preset or until")
        return self


class AnnouncementPatch(Strict):
    message: str | None = Field(default=None, min_length=1, max_length=280)
    tone: Literal["INFO", "ALERT"] | None = None
    audience: Literal["SHOP", "SIA", "BOTH"] | None = None
    link: LinkIn | None = None
    dismissible: bool | None = None
    startsAt: When | None = None
    ttl: TtlIn | None = None


class AnnouncementInput(AnnouncementPatch):
    message: str = Field(min_length=1, max_length=280)
    tone: Literal["INFO", "ALERT"]
    audience: Literal["SHOP", "SIA", "BOTH"]
    ttl: TtlIn


def ann(request: Request) -> AnnouncementService:
    s: AnnouncementService = request.app.state.announcements
    return s


def _dump(body: BaseModel, *, unset: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = body.model_dump(exclude_unset=unset)
    return out


async def viewer_for(app: str, me: Principal | None) -> None:
    if app == "sia":
        if me is None:
            raise unauthorized()
        if not me.is_staff:
            raise forbidden("Staff only")


# ---------------------------------------------------------------- public (catalog-svc and catalog-push)

public = APIRouter()


@public.get("/announcements", tags=["announcements"])
async def live_announcements(
    request: Request,
    app: Annotated[Literal["shop", "sia"], Query()] = "shop",
    me: Principal | None = Depends(optional_principal),
) -> JSONResponse:
    await viewer_for(app, me)
    items = await ann(request).live(app)
    return JSONResponse({"items": items}, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- admin (catalog-svc)

admin = APIRouter()


@admin.get("/admin/announcements", tags=["announcements"])
async def list_admin(request: Request, me: Principal = Depends(require_admin)) -> dict[str, Any]:
    return {"items": await ann(request).admin_list()}


@admin.post("/admin/announcements", status_code=201, tags=["announcements"])
async def create(body: AnnouncementInput, request: Request, me: Principal = Depends(require_admin)) -> JSONResponse:
    return with_etag(await ann(request).create(me, _dump(body), cid(request)), 201)


@admin.get("/admin/announcements/{announcementId}", tags=["announcements"])
async def get_one(announcementId: str, request: Request, me: Principal = Depends(require_admin)) -> JSONResponse:
    return with_etag(await ann(request).get(announcementId))


@admin.patch("/admin/announcements/{announcementId}", tags=["announcements"])
async def patch(
    announcementId: str,
    body: AnnouncementPatch,
    request: Request,
    version: IfMatch = None,
    me: Principal = Depends(require_admin),
) -> JSONResponse:
    fields = _dump(body, unset=True)
    for required in ("message", "tone", "audience", "dismissible"):
        if required in fields and fields[required] is None:
            raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": required, "message": "cannot be empty"}])
    if not fields:
        raise ProblemError(422, "VALIDATION_FAILED", "Nothing to update")
    v = if_match(version)
    return with_etag(await ann(request).update(me, announcementId, v, fields, cid(request)))


@admin.delete("/admin/announcements/{announcementId}", status_code=204, tags=["announcements"])
async def end_now(
    announcementId: str, request: Request, version: IfMatch = None, me: Principal = Depends(require_admin)
) -> Response:
    await ann(request).delete(me, announcementId, if_match(version), cid(request))
    return Response(status_code=204)


# ---------------------------------------------------------------- push (catalog-push)

push = APIRouter()


def origin_allowed(ws: WebSocket, allowed: tuple[str, ...]) -> bool:
    """Cross-site WebSocket hijacking guard: a browser always sends Origin. No Origin = not a browser."""
    origin = ws.headers.get("origin")
    if origin is None:
        return True
    origin = origin.rstrip("/")
    if allowed:
        return origin in allowed
    host = ws.headers.get("x-forwarded-host") or ws.headers.get("host") or ""
    return urlsplit(origin).netloc == host.split(",")[0].strip()


async def socket_principal(ws: WebSocket) -> Principal | None:
    """The staff principal from the access cookie (a browser can't set headers on a WebSocket)."""
    verifier = getattr(ws.app.state, "token_verifier", None)
    tokens = cookie_values(ws, ACCESS_COOKIE)[:4]
    if verifier is None or not tokens:
        return None
    for t in tokens:
        try:
            p: Principal = await verifier.verify(t)
        except ProblemError:
            continue
        if p.role == "service" or (p.is_admin and not p.mfa):
            return None
        return p
    return None


@push.websocket("/announcements/stream")
async def stream(ws: WebSocket, app: Literal["shop", "sia"] = "shop") -> None:
    hub: PushHub = ws.app.state.push_hub
    settings = ws.app.state.settings
    if not origin_allowed(ws, settings.push_origins):
        hub.refuse("origin")
        await ws.close(code=1008)  # before accept: the browser sees HTTP 403
        return
    await ws.accept()
    deadline: float | None = None
    if app == "sia":
        me = await socket_principal(ws)
        if me is None or not me.is_staff:
            hub.refuse("auth")
            await ws.close(code=4401 if me is None else 4403)
            return
        deadline = float(me.claims.get("exp") or 0) or None
    if hub.full:
        hub.refuse("full")
        await ws.close(code=1013, reason="try again later")
        return

    lock = asyncio.Lock()

    async def send(text: str) -> None:
        async with lock:
            await asyncio.wait_for(ws.send_text(text), SEND_TIMEOUT)

    client = Client(app, send)

    async def pinger() -> None:
        ping = json.dumps({"type": "ping"})
        while True:
            await asyncio.sleep(PING_SECONDS)
            await send(ping)

    async def expiry() -> None:
        # The access token runs out: close 4401 so the client refreshes and reconnects.
        if deadline is None:
            return
        await asyncio.sleep(max(0.0, deadline - time.time()))
        with contextlib.suppress(Exception):
            await ws.close(code=4401, reason="token expired")

    tasks = [asyncio.create_task(pinger()), asyncio.create_task(expiry())]
    try:
        await hub.join(client)
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            data = msg.get("text") or msg.get("bytes") or b""
            if len(data) > MAX_FRAME:
                await ws.close(code=1009)
                break
            # Client frames carry nothing; ignored.
    except (TimeoutError, WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.leave(client)
        for t in tasks:
            t.cancel()
