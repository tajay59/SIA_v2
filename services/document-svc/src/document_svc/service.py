"""document-svc rules (TAD §4.5, API documents.openapi.yaml).

Upload:   staff/admin any upload kind on any request; a customer only `signed_agreement` on a request they may act
          on (the requester, or an admin) while it is AWAITING_AGREEMENT. Size ≤ 20 MB, every file virus-scanned
          first, then type from the bytes, images re-encoded (infected → quarantine, 422 FILE_INFECTED; scanner down →
          503, fail closed). Then: bytes + sidecar on the volume → document.uploaded on Kafka (if that fails the
          file is removed and the upload refused) → attached to the request at once (best effort; the event does
          it anyway), so the customer can accept straight after uploading.
Download: staff/admin, or whoever order-svc says may see the request; otherwise 404 (never reveal a file exists).
          Label batches: staff only. nginx streams the bytes (X-Accel-Redirect to the internal /_protected/).
Delete:   staff; uploads only (generated documents stay); soft (sidecar flag) + document.deleted + audit.
Generate: from order events (consumer.py); the file id is derived from the event id, so a redelivered event
          rewrites the same file and order-svc attaches it once.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from cimh_common.auth import Principal
from cimh_common.errors import ProblemError, conflict, forbidden, not_found
from cimh_common.outbox import EventEnvelope

from . import pdfs
from .clients import AUDIT_TOPIC, TOPIC, Orders, Publisher
from .files import EXT, FileStore, Scanner, ScannerDown, reencode, safe_name, sniff

log = logging.getLogger("document")

UPLOAD_KINDS = ("supplier_quote", "signed_agreement", "upload", "commercial_invoice")
NAMES = {
    "cimh_quote": "CIMH-quote",
    "agreement": "Agreement",
    "invoice": "Invoice",
    "probono_invoice": "Pro-Bono-delivery-note",
    "commercial_invoice": "Commercial-invoice",
    "labels": "Labels",
}


def now() -> datetime:
    return datetime.now(UTC)


def public(meta: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "requestId", "kind", "name", "mime", "size", "sha256", "uploadedBy", "uploadedAt")
    return {k: meta.get(k) for k in keys}


def actor(p: Principal) -> dict[str, Any]:
    return {"id": p.sub, "name": p.email or p.sub, "role": p.role}


class DocumentService:
    def __init__(
        self,
        files: FileStore,
        orders: Orders,
        publisher: Publisher,
        scanner: Scanner,
        *,
        max_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        self.files, self.orders, self.publisher, self.scanner = files, orders, publisher, scanner
        self.max_bytes = max_bytes

    # ------------------------------------------------------------------ upload

    async def upload(
        self, p: Principal, rid: str, kind: str, filename: str | None, data: bytes, cid: str
    ) -> dict[str, Any]:
        if len(data) > self.max_bytes:
            raise ProblemError(413, "FILE_TOO_LARGE", f"Files can be at most {self.max_bytes // (1024 * 1024)} MB")
        if not data:
            raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": "file", "message": "empty file"}])
        await self._may_upload(p, rid, kind)
        fid = "FIL" + secrets.token_hex(16)
        # Scan before the type check: every infected upload is quarantined and audited, whatever its type.
        try:
            found = await self.scanner.scan(data)
        except ScannerDown as exc:
            log.error("virus scanner unavailable", extra={"error": str(exc)})
            raise ProblemError(
                503, "DEPENDENCY_UNAVAILABLE", "Virus scanning is unavailable; try again shortly"
            ) from exc
        if found:
            self.files.quarantine(fid, data, {"id": fid, "requestId": rid, "kind": kind, "signature": found,
                                              "by": p.sub, "at": now().isoformat(), "name": filename})  # fmt: skip
            log.warning("upload quarantined", extra={"fileId": fid, "requestId": rid, "signature": found})
            await self._audit(p, "file.quarantined", fid, cid, requestId=rid, signature=found)
            raise ProblemError(422, "FILE_INFECTED", "The file contains malware and was not stored")
        mime = sniff(data)
        if mime is None:
            raise ProblemError(415, "UNSUPPORTED_FILE_TYPE", "Upload a PDF, JPEG, PNG or WebP file")
        if mime != "application/pdf":
            try:
                data = reencode(data, mime)
            except Exception as exc:
                raise ProblemError(415, "UNSUPPORTED_FILE_TYPE", "The image could not be read") from exc
        meta = {
            "id": fid,
            "requestId": rid,
            "kind": kind,
            "name": safe_name(filename, EXT[mime]),
            "mime": mime,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "uploadedBy": actor(p),
            "uploadedAt": now().isoformat(),
            "generated": False,
        }
        self.files.save(meta, data)
        try:
            await self._emit("document.uploaded", meta, cid, p.sub)
        except ProblemError:
            self.files.remove(meta)
            raise
        try:
            await self.orders.attach(rid, meta)
        except ProblemError:
            log.warning("sync attach failed; document.uploaded will attach it", extra={"fileId": fid})
        return public(meta)

    async def _may_upload(self, p: Principal, rid: str, kind: str) -> None:
        if p.is_staff:
            if await self.orders.access(rid, p.sub) is None:
                raise not_found("No request with this id")
            return
        if kind != "signed_agreement":
            raise forbidden("Customers can only upload the signed agreement")
        acc = await self.orders.access(rid, p.sub)
        if acc is None or not acc.get("allowed"):
            raise not_found("No request with this id")
        if not acc.get("canAct"):
            raise forbidden("Only the requester or an admin can do this")
        if acc.get("status") != "AWAITING_AGREEMENT":
            raise conflict("INVALID_STATE", "The signed agreement can be uploaded only while it is awaited")

    # ------------------------------------------------------------------ download / delete

    async def download(self, p: Principal, fid: str) -> tuple[dict[str, Any], str]:
        meta = self.files.meta(fid)
        if meta is None or meta.get("deleted"):
            raise not_found("No file with this id")
        if not p.is_staff:
            rid = meta.get("requestId")
            acc = await self.orders.access(rid, p.sub) if rid else None
            if not acc or not acc.get("allowed"):
                raise not_found("No file with this id")
        return meta, self.files.rel_path(meta)

    async def delete(self, p: Principal, fid: str, reason: str, cid: str) -> None:
        meta = self.files.meta(fid)
        if meta is None or meta.get("deleted"):
            raise not_found("No file with this id")
        if meta.get("generated"):
            raise conflict("GENERATED_DOCUMENT", "Generated documents cannot be deleted")
        meta |= {"deleted": True, "deletedBy": actor(p), "deletedAt": now().isoformat(), "deletedReason": reason}
        payload = {"orderId": meta["requestId"], "fileId": fid, "reason": reason}
        await self.publisher.publish(TOPIC, meta["requestId"], self._event("document.deleted", payload, cid, p.sub))
        self.files.write_meta(meta)
        await self._audit(p, "file.deleted", fid, cid, requestId=meta["requestId"], reason=reason)

    # ------------------------------------------------------------------ generated

    async def labels(
        self, p: Principal, product_id: str, name: str | None, barcodes: list[str], cid: str
    ) -> dict[str, Any]:
        fid = "FIL" + secrets.token_hex(16)
        data = await asyncio.to_thread(pdfs.labels, product_id, name, barcodes)
        meta = self._generated_meta(fid, None, "labels", f"Labels-{product_id}.pdf", data, p.sub)
        self.files.save(meta, data)
        return public(meta)

    async def generate(self, kind: str, rid: str, event: EventEnvelope, **opts: Any) -> dict[str, Any] | None:
        """Render `kind` for request `rid` and publish document.generated. Same event → same file id."""
        req = await self.orders.request(rid)
        if req is None:
            log.warning("request gone; nothing to render", extra={"requestId": rid, "kind": kind})
            return None
        render: dict[str, Callable[..., bytes]] = {
            "cimh_quote": pdfs.cimh_quote,
            "agreement": pdfs.agreement,
            "invoice": pdfs.invoice,
            "probono_invoice": pdfs.probono_invoice,
            "commercial_invoice": pdfs.commercial_invoice,
        }
        data = await asyncio.to_thread(render[kind], req, **opts)
        fid = "FIL" + hashlib.sha256(f"{event.eventId}:{kind}".encode()).hexdigest()[:32]
        meta = self._generated_meta(fid, rid, kind, f"{NAMES[kind]}-{rid}.pdf", data, "system")
        self.files.save(meta, data)
        await self._emit("document.generated", meta, event.correlationId, event.actorId)
        return public(meta)

    @staticmethod
    def _generated_meta(fid: str, rid: str | None, kind: str, name: str, data: bytes, by: str) -> dict[str, Any]:
        return {
            "id": fid,
            "requestId": rid,
            "kind": kind,
            "name": name,
            "mime": "application/pdf",
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "uploadedBy": {"id": by, "name": "CIMH Stores", "role": "system" if by == "system" else "service"},
            "uploadedAt": now().isoformat(),
            "generated": True,
        }

    # ------------------------------------------------------------------ events

    @staticmethod
    def _event(etype: str, payload: dict[str, Any], cid: str, actor_id: str | None) -> EventEnvelope:
        return EventEnvelope(type=etype, payload=payload, correlationId=cid, actorId=actor_id)

    async def _emit(self, etype: str, meta: dict[str, Any], cid: str, actor_id: str | None) -> None:
        payload = {"orderId": meta["requestId"], "fileId": meta["id"]}
        payload |= {k: meta[k] for k in ("kind", "name", "mime", "size", "sha256")}
        await self.publisher.publish(TOPIC, meta["requestId"], self._event(etype, payload, cid, actor_id))

    async def _audit(self, p: Principal, action: str, fid: str, cid: str, **extra: Any) -> None:
        payload = {"action": action, "entity": {"type": "file", "id": fid}, "actor": actor(p), **extra}
        try:
            await self.publisher.publish(AUDIT_TOPIC, fid, self._event("audit.recorded", payload, cid, p.sub))
        except ProblemError:
            log.error("audit event not published", extra={"action": action, "fileId": fid})
