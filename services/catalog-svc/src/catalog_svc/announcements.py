"""Announcements: admin messages shown as a banner on every SHOP/SIA page (plan 2026-11-23, BSD §5.12).

Storage: collection `announcements`; a TTL index on `expiresAt` makes MongoDB delete a message once it has run out
(the TTL monitor runs about once a minute, so every read also filters on `expiresAt`). Audit entries ride on the
`misc` document `announcements` (kind `announcements`): an announcement can vanish (End now, TTL) before the relay
has read an outbox on it, the misc carrier never does.

Live push: after a write the writer publishes `cat:ann:changed` on Redis. Every catalog-push worker (`PushHub`)
listens, re-reads the live set from MongoDB (the source of truth) and sends each socket the difference for its app.
A reconcile tick does the same every `PUSH_RECONCILE_SECONDS`, which also covers expiry, scheduled starts and a lost
pub/sub message (Redis restart).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pymongo import ReturnDocument

from cimh_common.auth import Principal
from cimh_common.errors import ProblemError, conflict, not_found

from .service import _audit, actor_of, iso
from .store import PUBLIC_FILTER, Store, now

log = logging.getLogger("catalog.announcements")

App = Literal["shop", "sia"]
CHANNEL = "cat:ann:changed"
CARRIER_ID = "announcements"  # misc document holding the audit outbox
MAX_DAYS = 90
MAX_LIVE_SHOWN = 50  # a safety bound on the snapshot; the banner shows 3 (D6)
PRESETS = {"1h": timedelta(hours=1), "1d": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}
AUDIENCES_FOR: dict[str, tuple[str, ...]] = {"shop": ("SHOP", "BOTH"), "sia": ("SIA", "BOTH")}

Publish = Callable[[str], Awaitable[None]]


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def view(doc: dict[str, Any]) -> dict[str, Any]:
    """Announcement as the API returns it (public and admin share the shape; Actors only for admins)."""
    out: dict[str, Any] = {
        "id": doc["id"],
        "message": doc["message"],
        "tone": doc["tone"],
        "audience": doc["audience"],
        "link": doc.get("link"),
        "dismissible": bool(doc.get("dismissible")),
        "startsAt": iso(doc["startsAt"]),
        "expiresAt": iso(doc["expiresAt"]),
        "version": doc["version"],
    }
    return out


def admin_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        **view(doc),
        "createdAt": iso(doc.get("createdAt")),
        "updatedAt": iso(doc.get("updatedAt")),
        "createdBy": doc.get("createdBy"),
        "updatedBy": doc.get("updatedBy"),
    }


def _invalid(code: str, field: str, message: str) -> ProblemError:
    return ProblemError(422, code, message, errors=[{"field": field, "message": message}])


def check_url_link(link: dict[str, Any]) -> dict[str, Any]:
    """`https://…` or a site path (`/catalogue/…`). Never `//host`, `javascript:` or plain http."""
    url = link["url"].strip()
    label = (link.get("label") or "").strip()
    if not label:
        raise _invalid("VALIDATION_FAILED", "link.label", "Give the link a label")
    site_path = url.startswith("/") and not url.startswith("//") and "\\" not in url
    if not (site_path or url.lower().startswith("https://")) or any(c.isspace() for c in url):
        raise _invalid("LINK_NOT_ALLOWED", "link.url", "Use an https:// address or a page on this site (/…)")
    return {"label": label, "url": url}


def resolve_ttl(ttl: dict[str, Any], starts: datetime, at: datetime) -> datetime:
    """`{preset}` counts from the start; `{until}` is an end time. At most MAX_DAYS from now (D4)."""
    end = starts + PRESETS[ttl["preset"]] if ttl.get("preset") else _aware(ttl["until"])
    if end <= starts:
        raise _invalid("STARTS_AFTER_EXPIRY", "ttl", "The end must be after the start")
    if end <= at or end > at + timedelta(days=MAX_DAYS, minutes=5):
        raise _invalid("TTL_OUT_OF_RANGE", "ttl", f"Keep it between now and {MAX_DAYS} days from now")
    return end


class AnnouncementService:
    def __init__(self, store: Store, publish: Publish | None = None) -> None:
        self.store = store
        self.col = store.announcements
        self._publish = publish

    # ------------------------------------------------------------ reads

    async def live(self, app: App, at: datetime | None = None) -> list[dict[str, Any]]:
        t = at or now()
        cur = self.col.find(
            {"audience": {"$in": list(AUDIENCES_FOR[app])}, "startsAt": {"$lte": t}, "expiresAt": {"$gt": t}},
            {"_id": 0},
        )
        docs = [d async for d in cur]
        # Alerts first, then newest (D6).
        docs.sort(key=lambda d: (d["tone"] != "ALERT", -_aware(d["startsAt"]).timestamp(), d["id"]))
        return [view(d) for d in docs[:MAX_LIVE_SHOWN]]

    async def admin_list(self) -> list[dict[str, Any]]:
        cur = self.col.find({"expiresAt": {"$gt": now()}}, {"_id": 0})
        docs = [d async for d in cur]
        docs.sort(key=lambda d: (-_aware(d["startsAt"]).timestamp(), d["id"]))
        return [admin_view(d) for d in docs]

    async def get(self, ann_id: str) -> dict[str, Any]:
        doc = await self.col.find_one({"id": ann_id, "expiresAt": {"$gt": now()}}, {"_id": 0})
        if doc is None:
            raise not_found("Announcement not found")
        return admin_view(doc)

    # ------------------------------------------------------------ writes

    async def check_link(self, link: dict[str, Any] | None, audience: str) -> dict[str, Any] | None:
        """A web address, or a product (owner 2026-11-23: a banner about a product change opens that product).
        A product link stores the id; each app builds its own page address (SHOP /catalogue/<id>, SIA
        /products/<id>). The product must exist and be active, and be on SHOP when SHOP shows the banner."""
        if link is None:
            return None
        pid = link.get("productId")
        if not pid:
            if not link.get("url"):
                raise _invalid("VALIDATION_FAILED", "link", "Choose a product or give a web address")
            return check_url_link(link)
        doc = await self.store.product.find_one({"id": pid, "active": True}, {"_id": 0, "id": 1, "name": 1})
        if doc is None:
            raise _invalid("PRODUCT_NOT_FOUND", "link.productId", "That product does not exist or is inactive")
        if (
            audience in ("SHOP", "BOTH")
            and await self.store.product.find_one({**PUBLIC_FILTER, "id": pid}, {"_id": 0, "id": 1}) is None
        ):
            raise _invalid(
                "PRODUCT_NOT_ON_SHOP",
                "link.productId",
                "Customers can't open this product on SHOP; show it on SIA only",
            )
        label = (link.get("label") or "").strip() or str(doc.get("name") or pid)[:40]
        return {"label": label, "productId": pid}

    async def _audit(self, p: Principal, action: str, ann_id: str, cid: str, **extra: Any) -> None:
        await self.store.misc.update_one(
            {"id": CARRIER_ID},
            {
                "$set": {"kind": "announcements", "updatedAt": now()},
                "$push": {"outbox": _audit(p, action, "announcement", ann_id, cid, **extra)},
            },
            upsert=True,
        )

    async def _changed(self, ann_id: str) -> None:
        if self._publish is None:
            return
        try:
            await self._publish(ann_id)
        except Exception:
            log.warning("announcement change not published", extra={"announcement": ann_id})

    async def create(self, p: Principal, body: dict[str, Any], cid: str) -> dict[str, Any]:
        at = now()
        starts = _aware(body["startsAt"]) if body.get("startsAt") else at
        if starts > at + timedelta(days=MAX_DAYS):
            raise _invalid("TTL_OUT_OF_RANGE", "startsAt", f"Start within {MAX_DAYS} days")
        starts = max(starts, at - timedelta(minutes=5))  # a start in the past means now
        expires = resolve_ttl(body["ttl"], starts, at)
        tone = body["tone"]
        doc = {
            "id": "ANN" + secrets.token_hex(16),
            "message": body["message"].strip(),
            "tone": tone,
            "audience": body["audience"],
            "link": await self.check_link(body.get("link"), body["audience"]),
            "dismissible": body.get("dismissible") is not False and tone != "ALERT",  # D5
            "startsAt": starts,
            "expiresAt": expires,
            "createdAt": at,
            "updatedAt": at,
            "createdBy": actor_of(p),
            "updatedBy": actor_of(p),
            "version": 1,
        }
        if not doc["message"]:
            raise _invalid("VALIDATION_FAILED", "message", "Write the message")
        await self.col.insert_one(dict(doc))
        await self._audit(
            p,
            "announcement.created",
            doc["id"],
            cid,
            to={"message": doc["message"], "tone": tone, "audience": doc["audience"], "expiresAt": iso(expires)},
        )
        await self._changed(doc["id"])
        return admin_view(doc)

    async def update(self, p: Principal, ann_id: str, version: int, fields: dict[str, Any], cid: str) -> dict[str, Any]:
        current = await self.col.find_one({"id": ann_id, "expiresAt": {"$gt": now()}})
        if current is None:
            raise not_found("Announcement not found")
        if current["version"] != version:
            raise conflict("VERSION_CONFLICT", "The announcement was changed by someone else; reload it")
        at = now()
        update: dict[str, Any] = {}
        if "message" in fields:
            msg = fields["message"].strip()
            if not msg:
                raise _invalid("VALIDATION_FAILED", "message", "Write the message")
            update["message"] = msg
        for key in ("tone", "audience"):
            if key in fields:
                update[key] = fields[key]
        audience = update.get("audience", current["audience"])
        if "link" in fields:
            update["link"] = await self.check_link(fields["link"], audience)
        elif "audience" in update and (current.get("link") or {}).get("productId"):
            # Moving a product banner onto SHOP: the product must be on SHOP too.
            await self.check_link(current["link"], audience)
        tone = update.get("tone", current["tone"])
        if "dismissible" in fields or "tone" in update:
            want = fields.get("dismissible", current.get("dismissible", True))
            update["dismissible"] = bool(want) and tone != "ALERT"
        starts = _aware(current["startsAt"])
        if fields.get("startsAt") is not None:
            starts = max(_aware(fields["startsAt"]), at - timedelta(minutes=5))
            if starts > at + timedelta(days=MAX_DAYS):
                raise _invalid("TTL_OUT_OF_RANGE", "startsAt", f"Start within {MAX_DAYS} days")
            update["startsAt"] = starts
        if fields.get("ttl") is not None:
            update["expiresAt"] = resolve_ttl(fields["ttl"], starts, at)
        elif starts >= _aware(current["expiresAt"]):
            raise _invalid("STARTS_AFTER_EXPIRY", "startsAt", "The start must be before the end")
        update |= {"updatedAt": at, "updatedBy": actor_of(p)}
        doc = await self.col.find_one_and_update(
            {"id": ann_id, "version": version},
            {"$set": update, "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            raise conflict("VERSION_CONFLICT", "The announcement was changed by someone else; reload it")
        changed = {
            k: (iso(v) if isinstance(v, datetime) else v)
            for k, v in update.items()
            if k not in ("updatedAt", "updatedBy")
        }
        await self._audit(p, "announcement.updated", ann_id, cid, to=changed)
        await self._changed(ann_id)
        return admin_view(doc)

    async def delete(self, p: Principal, ann_id: str, version: int, cid: str) -> None:
        res = await self.col.delete_one({"id": ann_id, "version": version, "expiresAt": {"$gt": now()}})
        if res.deleted_count == 0:
            if await self.col.find_one({"id": ann_id, "expiresAt": {"$gt": now()}}) is None:
                raise not_found("Announcement not found")
            raise conflict("VERSION_CONFLICT", "The announcement was changed by someone else; reload it")
        await self._audit(p, "announcement.ended", ann_id, cid)
        await self._changed(ann_id)


# ---------------------------------------------------------------- push hub (catalog-push)


class Client:
    """One open socket: what it was last sent, so the hub only sends differences."""

    def __init__(self, app: App, send: Callable[[str], Awaitable[None]]) -> None:
        self.app = app
        self.send = send
        self.seen: dict[str, int] = {}  # id -> version


class PushHub:
    """Holds this worker's sockets and keeps each one in step with the live announcements."""

    def __init__(
        self,
        service: AnnouncementService,
        *,
        max_sockets: int = 5000,
        reconcile_seconds: float = 30.0,
        redis: Any = None,
        metrics: Any = None,
    ) -> None:
        self.service = service
        self.max_sockets = max_sockets
        self.reconcile_seconds = reconcile_seconds
        self.redis = redis
        self.clients: set[Client] = set()
        self.sent: Any = None
        self.refused: Any = None
        if metrics is not None:
            from prometheus_client import Counter, Gauge

            reg = metrics.registry
            self.sent = Counter("push_messages_total", "Announcement frames sent", registry=reg)
            self.refused = Counter("push_refused_total", "Sockets refused", ["reason"], registry=reg)
            gauge = Gauge("push_sockets", "Open announcement sockets", ["app"], registry=reg)
            for app in ("shop", "sia"):
                gauge.labels(app).set_function(self._counter(app))
            Gauge("push_sockets_max", "Socket cap per worker", registry=reg).set(max_sockets)
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[None]] = []

    def _counter(self, app: str) -> Callable[[], float]:
        return lambda: float(sum(1 for c in self.clients if c.app == app))

    @property
    def full(self) -> bool:
        return len(self.clients) >= self.max_sockets

    async def join(self, client: Client) -> None:
        items = await self.service.live(client.app)
        client.seen = {i["id"]: i["version"] for i in items}
        self.clients.add(client)
        await client.send(json.dumps({"type": "snapshot", "items": items, "serverTime": iso(now())}))

    def refuse(self, reason: str) -> None:
        if self.refused is not None:
            self.refused.labels(reason).inc()

    def leave(self, client: Client) -> None:
        self.clients.discard(client)

    async def sync(self) -> None:
        """Re-read the live set once per app and send every socket its difference."""
        async with self._lock:
            if not self.clients:
                return
            apps: tuple[App, ...] = ("shop", "sia")
            live = {app: await self.service.live(app) for app in apps}
            for client in list(self.clients):
                items = live[client.app]
                now_ids = {i["id"] for i in items}
                frames = [{"type": "upsert", "item": i} for i in items if client.seen.get(i["id"]) != i["version"]] + [
                    {"type": "remove", "id": gone} for gone in client.seen.keys() - now_ids
                ]
                if not frames:
                    continue
                client.seen = {i["id"]: i["version"] for i in items}
                for frame in frames:
                    try:
                        await client.send(json.dumps(frame))
                    except Exception:
                        self.leave(client)
                        break
                if self.sent is not None:
                    self.sent.inc(len(frames))

    async def _reconcile_loop(self) -> None:
        while True:
            await asyncio.sleep(self.reconcile_seconds)
            try:
                await self.sync()
            except Exception:
                log.exception("announcement reconcile failed")

    async def _listen(self) -> None:
        """Redis pub/sub: a write anywhere pokes every worker. Reconnects on its own after a Redis restart."""
        while True:
            pubsub = self.redis.pubsub()
            try:
                await pubsub.subscribe(CHANNEL)
                while True:
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if msg is not None:
                        await self.sync()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("announcement subscription lost; retrying")
                await asyncio.sleep(2)
            finally:
                with contextlib.suppress(Exception):
                    await pubsub.aclose()

    def start(self) -> None:
        self._tasks.append(asyncio.create_task(self._reconcile_loop()))
        if self.redis is not None:
            self._tasks.append(asyncio.create_task(self._listen()))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self._tasks.clear()


def redis_publisher(redis: Any) -> Publish:
    async def publish(ann_id: str) -> None:
        await redis.publish(CHANNEL, ann_id)

    return publish
