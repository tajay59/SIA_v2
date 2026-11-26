"""Announcements: admin messages shown as a banner on every SHOP/SIA page (plan 2026-11-23, BSD §5.12).

Storage: collection `announcements`; a TTL index on `expiresAt` makes MongoDB delete a message once it has run out
(the TTL monitor runs about once a minute, so every read also filters on `expiresAt`). Audit entries ride on the
`misc` document `announcements` (kind `announcements`): an announcement can vanish (End now, TTL) before the relay
has read an outbox on it, the misc carrier never does.

Live push: after a write the writer publishes `cat:ann:changed` on Redis. Every catalog-push worker (`PushHub`)
listens, re-reads the live set from MongoDB (the source of truth) and sends each socket the difference for its app.
A reconcile tick does the same every `PUSH_RECONCILE_SECONDS`, which also covers expiry, scheduled starts and a lost
pub/sub message (Redis restart).

Images (owner 2026-11-26): an announcement may carry a `picture` (shown at the row's right; a product link without
one shows the product's primary photo there) and a `background` (behind the text, under a dark wash). Uploads go
the same way as product photos: the API writes `incoming/`, an `image.process` job (`target: announcement`) rides
on the misc carrier's outbox to media-worker (the only process that decodes images, SECURITY T-26), and
catalog-consumer records the result on the carrier (`images.<fileId>`: PROCESSING -> READY | FAILED). An
announcement can only use a READY image. Entries older than `IMAGE_KEEP` that no announcement uses are dropped,
with their files, at the next upload.
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
from cimh_common.outbox import new_event

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
IMAGE_SLOTS = ("picture", "background")
EFFECTS = ("sweep", "glint", "ring", "drift", "zoom", "nudge")  # owner 2026-11-26; order = how they're listed
IMAGE_KEEP = timedelta(days=2)  # an upload no announcement uses is dropped after this

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
        "link": dict(doc["link"]) if doc.get("link") else None,
        "picture": _image_out(doc.get("picture")),
        "background": _image_out(doc.get("background")),
        "height": doc.get("height"),
        "look": doc.get("look") or "SOFT",
        "effects": [e for e in EFFECTS if e in (doc.get("effects") or [])],
        "dismissible": bool(doc.get("dismissible")),
        "startsAt": iso(doc["startsAt"]),
        "expiresAt": iso(doc["expiresAt"]),
        "version": doc["version"],
    }
    return out


def _image_out(img: Any) -> dict[str, Any] | None:
    if not isinstance(img, dict) or not img.get("url"):
        return None
    return {k: img[k] for k in ("fileId", "url", "w", "h") if img.get(k) is not None}


def file_id_for(job_id: str) -> str:
    """media-worker's rule: the file id comes from the job id."""
    return "IMG" + job_id.removeprefix("JOB")


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
        return await self.with_product_photos([view(d) for d in docs[:MAX_LIVE_SHOWN]])

    async def with_product_photos(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """A product link carries the product's primary photo (`link.imageUrl`, null when it has none), read now:
        a new primary photo shows at the next read."""
        ids = {i["link"]["productId"] for i in items if i.get("link") and i["link"].get("productId")}
        if not ids:
            return items
        photos: dict[str, str | None] = {}
        async for d in self.store.product.find({"id": {"$in": list(ids)}}, {"_id": 0, "id": 1, "images": 1}):
            imgs = [x for x in d.get("images") or [] if isinstance(x, dict) and x.get("url")]
            best = next((x for x in imgs if x.get("primary")), imgs[0] if imgs else None)
            photos[d["id"]] = best["url"] if best else None
        for i in items:
            link = i.get("link")
            if link and link.get("productId"):
                link["imageUrl"] = photos.get(link["productId"])
        return items

    async def admin_list(self) -> list[dict[str, Any]]:
        cur = self.col.find({"expiresAt": {"$gt": now()}}, {"_id": 0})
        docs = [d async for d in cur]
        docs.sort(key=lambda d: (-_aware(d["startsAt"]).timestamp(), d["id"]))
        return await self.with_product_photos([admin_view(d) for d in docs])

    async def get(self, ann_id: str) -> dict[str, Any]:
        doc = await self.col.find_one({"id": ann_id, "expiresAt": {"$gt": now()}}, {"_id": 0})
        if doc is None:
            raise not_found("Announcement not found")
        return (await self.with_product_photos([admin_view(doc)]))[0]

    # ------------------------------------------------------------ images

    async def queue_image(self, p: Principal, source: str, cid: str) -> dict[str, Any]:
        """`source` is relative to MEDIA_ROOT (`incoming/<name>`), already written by the API layer."""
        job_id = f"JOB{secrets.token_hex(12).upper()}"
        fid = file_id_for(job_id)
        evt = new_event(
            "image.process",
            {"jobId": job_id, "target": "announcement", "sourcePath": source, "removeBackground": False},
            correlation_id=cid,
            actor_id=p.sub,
        ).model_dump(mode="python")
        at = now()
        await self.store.misc.update_one(
            {"id": CARRIER_ID},
            {
                "$set": {
                    "kind": "announcements",
                    "updatedAt": at,
                    f"images.{fid}": {"status": "PROCESSING", "createdAt": at},
                },
                "$push": {"outbox": evt},
            },
            upsert=True,
        )
        return {"fileId": fid, "status": "PROCESSING"}

    async def image_status(self, file_id: str) -> dict[str, Any]:
        entry = await self._image_entry(file_id)
        if entry is None:
            raise not_found("Image not found")
        out = {"fileId": file_id, "status": entry["status"]}
        for k in ("url", "w", "h", "error"):
            if entry.get(k) is not None:
                out[k] = entry[k]
        return out

    async def _image_entry(self, file_id: str) -> dict[str, Any] | None:
        if not file_id.startswith("IMG") or not file_id[3:].isalnum() or len(file_id) > 64:
            return None
        doc = await self.store.misc.find_one({"id": CARRIER_ID}, {"_id": 0, "images": 1})
        entry = ((doc or {}).get("images") or {}).get(file_id)
        return entry if isinstance(entry, dict) else None

    async def image_processed(self, payload: dict[str, Any]) -> bool:
        """media.results (target announcement): record READY with the URL, or FAILED. Idempotent; a result for an
        upload already dropped is ignored."""
        fid = payload.get("fileId") or file_id_for(str(payload["jobId"]))
        entry = await self._image_entry(fid)
        if entry is None or entry.get("status") != "PROCESSING":
            return False
        if payload.get("ok"):
            new = {"status": "READY", "url": payload["url"], "w": payload.get("w"), "h": payload.get("h")}
        else:
            new = {"status": "FAILED", "error": "That file isn't a usable image. Try a JPEG, PNG or WebP."}
        res = await self.store.misc.update_one(
            {"id": CARRIER_ID, f"images.{fid}.status": "PROCESSING"},
            {"$set": {f"images.{fid}": {**entry, **new}}},
        )
        return bool(res.modified_count)

    async def drop_stale_images(self) -> list[str]:
        """Uploads older than IMAGE_KEEP that no stored announcement uses. Returns their ids (the API deletes the
        files). An announcement that ran out is gone (TTL), so its images are dropped here too."""
        doc = await self.store.misc.find_one({"id": CARRIER_ID}, {"_id": 0, "images": 1})
        entries: dict[str, Any] = (doc or {}).get("images") or {}
        cutoff = now() - IMAGE_KEEP
        old = [
            f
            for f, e in entries.items()
            if isinstance(e, dict) and isinstance(e.get("createdAt"), datetime) and _aware(e["createdAt"]) < cutoff
        ]
        if not old:
            return []
        used: set[str] = set()
        async for a in self.col.find(
            {"$or": [{"picture.fileId": {"$in": old}}, {"background.fileId": {"$in": old}}]},
            {"_id": 0, "picture": 1, "background": 1},
        ):
            used |= {str((a.get(slot) or {}).get("fileId")) for slot in IMAGE_SLOTS}
        gone = [f for f in old if f not in used]
        if gone:
            await self.store.misc.update_one({"id": CARRIER_ID}, {"$unset": {f"images.{f}": "" for f in gone}})
        return gone

    async def check_image(self, ref: dict[str, Any] | None, slot: str) -> dict[str, Any] | None:
        if ref is None:
            return None
        entry = await self._image_entry(str(ref.get("fileId") or ""))
        if entry is None:
            raise _invalid("IMAGE_NOT_FOUND", f"{slot}.fileId", "Upload the image again")
        if entry["status"] == "PROCESSING":
            raise _invalid(
                "IMAGE_NOT_READY", f"{slot}.fileId", "The image is still being prepared; try again in a moment"
            )
        if entry["status"] != "READY":
            raise _invalid("IMAGE_NOT_USABLE", f"{slot}.fileId", entry.get("error") or "That image couldn't be used")
        out = {"fileId": ref["fileId"], "url": entry["url"], "w": entry.get("w"), "h": entry.get("h")}
        return {k: v for k, v in out.items() if v is not None}

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
            "picture": await self.check_image(body.get("picture"), "picture"),
            "background": await self.check_image(body.get("background"), "background"),
            "height": body.get("height"),
            "look": body.get("look") or "SOFT",
            "effects": [e for e in EFFECTS if e in (body.get("effects") or [])],
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
        return (await self.with_product_photos([admin_view(doc)]))[0]

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
        if "height" in fields:
            update["height"] = fields["height"]
        if "look" in fields:
            update["look"] = fields["look"]
        if "effects" in fields:
            update["effects"] = [e for e in EFFECTS if e in fields["effects"]]
        audience = update.get("audience", current["audience"])
        if "link" in fields:
            update["link"] = await self.check_link(fields["link"], audience)
        elif "audience" in update and (current.get("link") or {}).get("productId"):
            # Moving a product banner onto SHOP: the product must be on SHOP too.
            await self.check_link(current["link"], audience)
        for slot in IMAGE_SLOTS:
            if slot in fields:
                update[slot] = await self.check_image(fields[slot], slot)
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
        for slot in IMAGE_SLOTS:  # the audit names the image, not its URL and size
            if slot in changed:
                img = changed[slot]
                changed[slot] = img.get("fileId") if isinstance(img, dict) else None
        await self._audit(p, "announcement.updated", ann_id, cid, to=changed)
        await self._changed(ann_id)
        return (await self.with_product_photos([admin_view(doc)]))[0]

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
