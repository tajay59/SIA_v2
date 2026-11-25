"""document-svc rules (TAD §4.5, API documents.openapi.yaml).

Upload:   staff/admin any upload kind on any request; a customer only `signed_agreement` on a request they may act
          on (the requester, or an admin) while it is QUOTED ("view and sign"). A signed agreement is stamped with
          the request's current quote version, so a copy signed for an older version can't accept a revised quote.
          Size ≤ 20 MB, every file virus-scanned
          first, then type from the bytes, images re-encoded (infected → quarantine, 422 FILE_INFECTED; scanner down →
          503, fail closed). Then: bytes + sidecar on the volume → document.uploaded on Kafka (if that fails the
          file is removed and the upload refused) → attached to the request at once (best effort; the event does
          it anyway), so the customer can accept straight after uploading.
Download: staff/admin, or whoever order-svc says may see the request; otherwise 404 (never reveal a file exists).
          Label batches: staff only. nginx streams the bytes (X-Accel-Redirect to the internal /_protected/).
Delete:   staff; uploads only (generated documents stay); soft (sidecar flag) + document.deleted + audit.
Invoices: one current invoice and one commercial invoice per request (plan 2026-11-24-invoice-crud). document-svc
          renders and stores the PDF; order-svc records which is current (rev, number, lines, total) and refuses
          a second one, a stale revision, a change once paid or a number already used. Saving again = a new PDF
          (rev + 1); the earlier PDF is flagged replaced, voiding flags it voided: both are staff-only downloads.
Generate: from order events (consumer.py); the file id is derived from the event id, so a redelivered event
          rewrites the same file and order-svc attaches it once. An agreement / CIMH quote is rendered only while
          its quote version is still the current one (a revision sent meanwhile renders its own).
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
from .files import EXT, FileStore, Scanner, ScannerDown, pdf_pages, reencode, safe_name, sniff

log = logging.getLogger("document")

UPLOAD_KINDS = ("supplier_quote", "signed_agreement", "payment_proof", "upload", "commercial_invoice")
NAMES = {
    "cimh_quote": "CIMH-quote",
    "agreement": "Agreement",
    "invoice": "Invoice",
    "probono_invoice": "Pro-Bono-delivery-note",
    "commercial_invoice": "Commercial-invoice",
    "labels": "Labels",
}


SYSTEM_ACTOR = {"id": "system", "name": "CIMH Stores", "role": "system"}


def now() -> datetime:
    return datetime.now(UTC)


def public(meta: dict[str, Any]) -> dict[str, Any]:
    keys: tuple[str, ...] = ("id", "requestId", "kind", "name", "mime", "size", "sha256", "uploadedBy", "uploadedAt")
    keys += ("quoteVersion",)
    keys += ("number", "rev") if meta.get("rev") else ()
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
        self.on_event: Callable[[str, str], None] = lambda event, role: None  # main.py → metrics

    # ------------------------------------------------------------------ upload

    async def upload(
        self, p: Principal, rid: str, kind: str, filename: str | None, data: bytes, cid: str
    ) -> dict[str, Any]:
        if len(data) > self.max_bytes:
            raise ProblemError(413, "FILE_TOO_LARGE", f"Files can be at most {self.max_bytes // (1024 * 1024)} MB")
        if not data:
            raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": "file", "message": "empty file"}])
        acc = await self._may_upload(p, rid, kind)
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
            self.on_event("malware_detected", p.role)
            await self._audit(p, "file.quarantined", fid, cid, requestId=rid, signature=found)
            raise ProblemError(422, "FILE_INFECTED", "The file contains malware and was not stored")
        mime = sniff(data)
        if mime is None:
            raise ProblemError(415, "UNSUPPORTED_FILE_TYPE", "Upload a PDF, JPEG, PNG or WebP file")
        if mime == "application/pdf":
            if await asyncio.to_thread(pdf_pages, data) < 1:
                msg = "The PDF could not be read; save it again and upload it"
                raise ProblemError(415, "UNSUPPORTED_FILE_TYPE", msg)
        else:
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
        if kind == "signed_agreement" and isinstance(acc.get("quoteVersion"), int):
            meta["quoteVersion"] = acc["quoteVersion"]
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

    async def _may_upload(self, p: Principal, rid: str, kind: str) -> dict[str, Any]:
        """The access answer for the request (status, quote version) when the upload is allowed."""
        if p.is_staff:
            staff_acc = await self.orders.access(rid, p.sub)
            if staff_acc is None:
                raise not_found("No request with this id")
            return staff_acc
        if kind not in ("signed_agreement", "payment_proof"):
            raise forbidden("Customers can only upload the signed agreement or a proof of payment")
        acc = await self.orders.access(rid, p.sub)
        if acc is None or not acc.get("allowed"):
            raise not_found("No request with this id")
        if not acc.get("canAct"):
            raise forbidden("Only the requester or an admin can do this")
        if kind == "payment_proof":
            if acc.get("type") != "PAID" or acc.get("status") != "DELIVERED":
                raise conflict("INVALID_STATE", "A proof of payment can be sent once a paid request is delivered")
            return acc
        if acc.get("status") != "QUOTED":
            raise conflict("INVALID_STATE", "The signed agreement can be uploaded only while the quote is open")
        return acc

    # ------------------------------------------------------------------ download / delete

    async def download(self, p: Principal, fid: str) -> tuple[dict[str, Any], str]:
        meta = self.files.meta(fid)
        if meta is None or meta.get("deleted"):
            raise not_found("No file with this id")
        if not p.is_staff:
            if meta.get("replaced") or meta.get("voided"):  # an earlier or withdrawn invoice: staff only
                raise not_found("No file with this id")
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

    async def generate(
        self, kind: str, rid: str, event: EventEnvelope, *, quote_version: int | None = None, **opts: Any
    ) -> dict[str, Any] | None:
        """Render `kind` for request `rid` and publish document.generated. Same event → same file id.
        With `quote_version` (agreement, CIMH quote) nothing is rendered once a newer version was sent."""
        req = await self.orders.request(rid)
        if req is None:
            log.warning("request gone; nothing to render", extra={"requestId": rid, "kind": kind})
            return None
        if quote_version is not None:
            current = (req.get("agreement") if kind == "agreement" else req.get("cimhQuote")) or {}
            if current.get("quoteVersion" if kind == "agreement" else "version") != quote_version:
                log.info("quote revised meanwhile; not rendered", extra={"requestId": rid, "kind": kind})
                return None
        render: dict[str, Callable[..., bytes]] = {
            "cimh_quote": pdfs.cimh_quote,
            "agreement": pdfs.agreement,
            "probono_invoice": pdfs.probono_invoice,
        }
        data = await asyncio.to_thread(render[kind], req, **opts)
        fid = "FIL" + hashlib.sha256(f"{event.eventId}:{kind}".encode()).hexdigest()[:32]
        name = f"{NAMES[kind]}-{rid}" + (f"-v{quote_version}" if quote_version else "") + ".pdf"
        meta = self._generated_meta(fid, rid, kind, name, data, "system")
        if quote_version is not None:
            meta["quoteVersion"] = quote_version
        self.files.save(meta, data)
        extra = {"customer": req["customer"]} if isinstance(req.get("customer"), str) else {}
        await self._emit("document.generated", meta, event.correlationId, event.actorId, **extra)
        return public(meta)

    async def agreement_preview(self, p: Principal, rid: str) -> bytes:
        """Staff see the agreement a Send quote would email, before sending it: rendered from order-svc's priced
        draft, marked as a preview, never stored and never published."""
        if not p.is_staff:
            raise forbidden("Only staff can preview an agreement")
        req = await self.orders.quote_preview(rid)
        if req is None:
            raise not_found("Request not found")
        return await asyncio.to_thread(pdfs.agreement, req, preview=True)

    # ------------------------------------------------------------------ invoices (one current per kind, revisions)

    async def _staff_request(self, p: Principal, rid: str) -> dict[str, Any]:
        if not p.is_staff:
            raise forbidden("Only staff can build invoices")
        req = await self.orders.request(rid)
        if req is None or req.get("status") == "CART":
            raise not_found("Request not found")
        return req

    async def invoice_draft(self, p: Principal, rid: str, kind: str) -> dict[str, Any]:
        """The lines, fee and shipping the invoice builder starts from (staff edit them before creating), plus the
        suggested number (the latest invoice number of this kind + 1)."""
        draft = pdfs.invoice_draft(await self._staff_request(p, rid), kind)
        draft["suggestedNumber"] = await self.orders.next_invoice_number(kind)
        return draft

    async def invoice_get(self, p: Principal, rid: str, kind: str) -> dict[str, Any]:
        """The request's current invoice of `kind` as the builder reopens it (404 when there is none)."""
        req = await self._staff_request(p, rid)
        rec = (req.get("invoices") or {}).get(kind)
        if not rec:
            raise not_found("This request has no invoice of that kind")
        return {**rec, "kind": kind, "recipient": pdfs.invoice_recipient(req, kind)}

    async def invoice_preview(self, p: Principal, rid: str, body: dict[str, Any]) -> bytes:
        req = await self._staff_request(p, rid)
        return await asyncio.to_thread(pdfs.built_invoice, req, body, preview=True)

    async def create_invoice(self, p: Principal, rid: str, body: dict[str, Any], cid: str) -> dict[str, Any]:
        """A new invoice / commercial invoice (rev 1); 409 INVOICE_EXISTS when the request already has one."""
        return await self._save_invoice(p, rid, body["kind"], body, None, cid)

    async def revise_invoice(
        self, p: Principal, rid: str, kind: str, body: dict[str, Any], rev: int, cid: str
    ) -> dict[str, Any]:
        """Changes to the current invoice: a new PDF (rev + 1, same or new number) replaces it for the customer;
        the earlier PDF stays for staff. 409 VERSION_CONFLICT when someone saved first, 409 INVOICE_LOCKED once
        marked paid."""
        if body["kind"] != kind:
            raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": "kind", "message": "must match the path"}])
        return await self._save_invoice(p, rid, kind, body, rev, cid)

    async def _save_invoice(
        self, p: Principal, rid: str, kind: str, body: dict[str, Any], rev: int | None, cid: str
    ) -> dict[str, Any]:
        """Render, store, let order-svc record it as the current invoice (it decides: one per kind, revision,
        lock, unique number; a refusal removes the new file), then publish document.generated (`notify` says who
        is emailed; `rev` > 1 = a corrected invoice) and audit it."""
        req = await self._staff_request(p, rid)
        new_rev = 1 if rev is None else rev + 1
        data = await asyncio.to_thread(pdfs.built_invoice, req, body | {"rev": new_rev})
        meta = self._invoice_meta("FIL" + secrets.token_hex(16), rid, kind, body["number"], new_rev, data, actor(p))
        self.files.save(meta, data)
        try:
            out = await self.orders.record_invoice(rid, kind, self._record_body(body, rev, "STAFF", actor(p), meta))
        except ProblemError:
            self.files.remove(meta)
            raise
        self._mark_old(out.get("replacedFileId"), {"replaced": True, "replacedBy": meta["id"]})
        notify = {"customer": bool(body.get("emailCustomer")), "staff": bool(body.get("emailStaff"))}
        extra: dict[str, Any] = {"notify": notify, "number": body["number"], "rev": new_rev}
        if isinstance(req.get("customer"), str):
            extra["customer"] = req["customer"]
        try:
            await self._emit("document.generated", meta, cid, p.sub, **extra)
        except ProblemError:
            # Recorded and attached already: the invoice stands; only its email is lost (staff can re-save).
            log.error("document.generated not published; the invoice is recorded", extra={"fileId": meta["id"]})
        action = f"{kind}.created" if rev is None else f"{kind}.revised"
        await self._audit(p, action, meta["id"], cid, requestId=rid, number=body["number"], rev=new_rev)
        return public(meta) | {"invoice": out.get("invoice")}

    async def void_invoice(self, p: Principal, rid: str, kind: str, rev: int, reason: str, cid: str) -> None:
        """Withdraw the current invoice: it leaves the customer's papers (nobody is emailed) and its number stays
        used. Once the request is marked paid only an administrator may (order-svc answers 403)."""
        await self._staff_request(p, rid)
        body = {"rev": rev, "reason": reason, "by": actor(p), "admin": p.is_admin}
        out = await self.orders.void_invoice(rid, kind, body)
        fid = out.get("voidedFileId")
        flags = {"voided": True, "voidedBy": actor(p), "voidedAt": now().isoformat(), "voidedReason": reason}
        self._mark_old(fid, flags)
        await self._audit(
            p, f"{kind}.voided", fid or rid, cid, requestId=rid, number=out.get("number"), rev=out.get("rev"),
            reason=reason,
        )  # fmt: skip

    async def generate_invoice(
        self, kind: str, rid: str, event: EventEnvelope, *, shipment_id: str | None = None
    ) -> dict[str, Any] | None:
        """An invoice made on delivery, or a commercial invoice for a CIMH parcel leaving Barbados: only when the
        request has no invoice of that kind yet (a voided one counts: staff withdrew it on purpose). Rendered from
        the request like the builder's draft (an invoice charges the signed total: estimated shipping, not parcel
        costs), recorded as the current invoice (source AUTO), so staff can open and change it later. Same event
        -> same file id; a redelivery after the record re-publishes document.generated only."""
        req = await self.orders.request(rid)
        if req is None:
            log.warning("request gone; nothing to render", extra={"requestId": rid, "kind": kind})
            return None
        fid = "FIL" + hashlib.sha256(f"{event.eventId}:{kind}".encode()).hexdigest()[:32]
        cur = (req.get("invoices") or {}).get(kind)
        voided = any(v.get("kind") == kind for v in req.get("voidedInvoices") or [])
        meta: dict[str, Any] | None = None
        if cur or voided:
            meta = self.files.meta(fid) if cur and cur.get("fileId") == fid else None
            if meta is None:
                log.info("invoice already on the request; none generated", extra={"requestId": rid, "kind": kind})
                return None
        else:
            data = pdfs.auto_invoice_data(req, kind, shipment_id)
            if not data["lines"]:
                log.info("nothing to invoice", extra={"requestId": rid, "kind": kind})
                return None
            number = data["number"] or await self.orders.next_invoice_number(kind) or rid
            data["date"] = event.occurredAt
            for _ in range(5):  # another request took the number a moment ago: the next one
                data["number"] = number
                pdf = await asyncio.to_thread(pdfs.built_invoice, req, data | {"rev": 1})
                meta = self._invoice_meta(fid, rid, kind, number, 1, pdf, SYSTEM_ACTOR)
                self.files.save(meta, pdf)
                try:
                    await self.orders.record_invoice(
                        rid, kind, self._record_body(data, None, "AUTO", SYSTEM_ACTOR, meta)
                    )
                    break
                except ProblemError as exc:
                    self.files.remove(meta)
                    meta = None
                    if exc.code == "INVOICE_EXISTS":
                        return None
                    if exc.code != "INVOICE_NUMBER_TAKEN":
                        raise
                    number = await self.orders.next_invoice_number(kind) or f"{rid}-{secrets.token_hex(2)}"
            if meta is None:
                raise RuntimeError(f"no free invoice number for {rid}")  # -> retry topic
        extra = {"customer": req["customer"]} if isinstance(req.get("customer"), str) else {}
        await self._emit(
            "document.generated", meta, event.correlationId, event.actorId, number=meta["number"], rev=1, **extra
        )
        return public(meta)

    @staticmethod
    def _record_body(
        data: dict[str, Any], rev: int | None, source: str, by: dict[str, Any], meta: dict[str, Any]
    ) -> dict[str, Any]:
        when = data["date"]
        day = when.date().isoformat() if isinstance(when, datetime) else str(when)[:10]
        return {
            "rev": rev,
            "number": data["number"],
            "date": day,
            "lines": [{k: ln.get(k) for k in ("lineId", "description", "qty", "unitPrice")} for ln in data["lines"]],
            "fees": data.get("fees") or "0.00",
            "discount": data.get("discount") or "0.00",
            "shipping": data.get("shipping") or "0.00",
            "source": source,
            "by": by,
            "file": {k: meta[k] for k in ("id", "kind", "name", "mime", "size")},
        }

    def _invoice_meta(
        self, fid: str, rid: str, kind: str, number: str, rev: int, data: bytes, by: dict[str, Any]
    ) -> dict[str, Any]:
        clean = "".join(ch for ch in str(number) if ch.isalnum() or ch in "-_")[:40]
        name = f"{NAMES[kind]}-{clean or rid}" + (f"-rev{rev}" if rev > 1 else "") + ".pdf"
        meta = self._generated_meta(fid, rid, kind, name, data, by["id"])
        if by["id"] != "system":
            meta["uploadedBy"] = by
        return meta | {"number": number, "rev": rev}

    def _mark_old(self, fid: str | None, flags: dict[str, Any]) -> None:
        """Flag an earlier invoice PDF on its sidecar (replaced / voided): customers can no longer download it."""
        old = self.files.meta(fid) if fid else None
        if old is not None:
            self.files.write_meta(old | flags)

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

    async def _emit(self, etype: str, meta: dict[str, Any], cid: str, actor_id: str | None, **extra: Any) -> None:
        payload = {"orderId": meta["requestId"], "fileId": meta["id"], **extra}
        payload |= {k: meta[k] for k in ("kind", "name", "mime", "size", "sha256")}
        if meta.get("quoteVersion") is not None:
            payload["quoteVersion"] = meta["quoteVersion"]
        await self.publisher.publish(TOPIC, meta["requestId"], self._event(etype, payload, cid, actor_id))

    async def _audit(self, p: Principal, action: str, fid: str, cid: str, **extra: Any) -> None:
        payload = {"action": action, "entity": {"type": "file", "id": fid}, "actor": actor(p), **extra}
        try:
            await self.publisher.publish(AUDIT_TOPIC, fid, self._event("audit.recorded", payload, cid, p.sub))
        except ProblemError:
            log.error("audit event not published", extra={"action": action, "fileId": fid})
