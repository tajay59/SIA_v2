"""Event → emails (APD §7 is the list of emails and where each link opens).

Exactly once per event and recipient: the consumer skips an event id it has processed (IdempotentConsumer), and
each recipient gets a Redis mark `ntf:sent:<eventId>:<hash>` after a successful send, so a retry after a partial
failure (SMTP down halfway through a staff list) only sends to the ones still missing.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from urllib.parse import quote

from cimh_common.outbox import EventEnvelope

from .clients import Directory, Mailer, Settings
from .templates import Message, render

log = logging.getLogger("notification")
SENT_TTL = 14 * 24 * 3600  # longer than any retry path (retry topics + DLQ replay window)

SUCCESS, WARNING, ERROR, INFO = "#1A7F37", "#B54708", "#B42318", "#006FA8"
CARRIERS = {"FEDEX": "FedEx", "DHL": "DHL", "HAND": "Hand delivery"}
TRACK = {
    "FEDEX": "https://www.fedex.com/fedextrack/?trknbr={}",
    "DHL": "https://www.dhl.com/global-en/home/tracking/tracking-express.html?tracking-id={}",
}
STAFF_WHY = "you are on a CIMH Stores staff notification list"
REQUEST_WHY = "you made a request on CIMH Stores"


def _date(value: Any) -> str:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d %B %Y")
    except ValueError:
        return str(value or "")


class Notifier:
    def __init__(self, s: Settings, directory: Directory, mailer: Mailer, redis: Any) -> None:
        self.s, self.dir, self.mailer, self.redis = s, directory, mailer, redis

    # ------------------------------------------------------------------ plumbing

    async def handle(self, event: EventEnvelope) -> int:
        """Send every email this event calls for; returns how many were sent now."""
        build = self.ROUTES.get(event.type)
        if build is None:
            return 0
        age = datetime.now(UTC) - event.occurredAt
        if age > timedelta(hours=self.s.max_event_age_hours):
            log.warning("event too old to email", extra={"type": event.type, "eventId": event.eventId})
            return 0
        messages = await build(self, event)
        sent = 0
        for m in messages:
            key = f"ntf:sent:{event.eventId}:{hashlib.sha256(m.to.lower().encode()).hexdigest()[:16]}"
            if await self.redis.get(key):
                continue
            await self.mailer.send(render(m), f"{event.eventId}.{sent}")
            await self.redis.set(key, "1", ex=SENT_TTL)
            sent += 1
        if event.payload.get("codeRef"):
            await self.dir.forget_code(event.payload["codeRef"])
        log.info("emails sent", extra={"type": event.type, "eventId": event.eventId, "sent": sent})
        return sent

    def shop(self, path: str) -> str:
        return self.s.shop_url + path

    def sia(self, path: str) -> str:
        return self.s.sia_url + path

    def app_for(self, role: str | None) -> str:
        return self.s.sia_url if role in ("staff", "admin") else self.s.shop_url

    async def customer(self, account_id: str | None) -> dict[str, Any] | None:
        if not account_id:
            return None
        acc = await self.dir.account(account_id)
        if not acc or acc.get("status") not in ("ACTIVE", None) or not acc.get("email"):
            return None  # suspended, erased or gone: no email
        return acc

    async def staff(self, list_name: str, **kw: Any) -> list[Message]:
        addrs = await self.dir.staff_list(list_name)
        if not addrs:
            # Nobody is on this list (SIA Settings -> Email lists): the email is dropped, so say so in the log.
            log.warning("staff email list %r is empty: %r not sent", list_name, kw.get("subject"))
        return [Message(to=addr, why=STAFF_WHY, **kw) for addr in addrs]

    async def to_customer(self, event: EventEnvelope, **kw: Any) -> list[Message]:
        acc = await self.customer(event.payload.get("customer"))
        if acc is None:
            return []
        return [Message(to=acc["email"], why=REQUEST_WHY, **kw)]

    # ------------------------------------------------------------------ identity

    async def _code(
        self, event: EventEnvelope, *, to: str, subject: str, heading: str, text: str, link: str, button: str
    ) -> list[Message]:
        code = await self.dir.claim_code(event.payload["codeRef"])
        if code is None:
            log.warning("code already claimed or expired", extra={"eventId": event.eventId})
            return []
        return [
            Message(
                to=to,
                subject=subject,
                heading=heading,
                paragraphs=[text, "The code expires in 15 minutes. If you didn't ask for it, ignore this email."],
                code=code,
                link=link,
                button=button,
            )
        ]

    async def registered(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        return await self._code(
            e,
            to=p["email"],
            subject="Your CIMH Stores verification code",
            heading="Confirm your email",
            text=f"Hello {p.get('firstname', '')}, enter this code to confirm your email address.",
            link=self.shop(f"/verify?email={quote(p['email'])}"),
            button="Enter the code",
        )

    async def password_reset(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        return await self._code(
            e,
            to=p["email"],
            subject="Reset your CIMH Stores password",
            heading="Reset your password",
            text="Enter this code to choose a new password.",
            link=f"{self.app_for(p.get('role'))}/reset-password?email={quote(p['email'])}",
            button="Reset password",
        )

    async def email_change(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        page = "/profile" if p.get("role") in ("staff", "admin") else "/account"
        return await self._code(
            e,
            to=p["newEmail"],
            subject="Confirm your new email address",
            heading="Confirm your new email",
            text="Enter this code in your account to start using this address for CIMH Stores.",
            link=self.app_for(p.get("role")) + page,
            button="Open my account",
        )

    async def verified(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        if p.get("status") != "PENDING_APPROVAL":
            return []  # @cimh.edu.bb accounts are active at once (user.approved auto)
        name = f"{p.get('firstname', '')} {p.get('lastname', '')}".strip()
        out = [
            Message(
                to=p["email"],
                subject="Your CIMH Stores account is waiting for approval",
                heading="Thanks, your email is confirmed",
                paragraphs=["An administrator now checks new accounts. We'll email you when yours is approved."],
                link=self.shop("/pending-approval"),
                button="See your account status",
            )
        ]
        out += await self.staff(
            "registration",
            subject=f"New account to approve: {name}",
            heading="A new account is waiting for approval",
            paragraphs=[f"{name} ({p['email']}) confirmed their email."],
            link=self.sia("/admin/approvals"),
            button="Review accounts",
        )
        return out

    async def approval_pending(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        name = f"{p.get('firstname', '')} {p.get('lastname', '')}".strip()
        since = f" since {_date(p['waitingSince'])}" if p.get("waitingSince") else ""
        return await self.staff(
            "registration",
            subject=f"Reminder: {name} is still waiting for approval",
            heading="An account is still waiting for approval",
            paragraphs=[f"{name} ({p['email']}) has been waiting{since}."],
            status=("Waiting", WARNING),
            link=self.sia("/admin/approvals"),
            button="Review accounts",
        )

    async def approved(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        return [
            Message(
                to=p["email"],
                subject="Your CIMH Stores account is ready",
                heading="Your account is ready",
                paragraphs=[f"Hello {p.get('firstname', '')}, you can now sign in to CIMH Stores."],
                status=("Approved", SUCCESS),
                link=f"{self.app_for(p.get('role'))}/login",
                button="Sign in",
            )
        ]

    async def rejected(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        return [
            Message(
                to=p["email"],
                subject="Your CIMH Stores account request",
                heading="We couldn't approve your account",
                paragraphs=[f"Reason: {p.get('reason', '')}", "If you think this is a mistake, reply to this email."],
                link=self.shop("/"),
                button="Visit CIMH Stores",
            )
        ]

    async def erasure_requested(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        name = f"{p.get('firstname', '')} {p.get('lastname', '')}".strip()
        return await self.staff(
            "registration",
            subject=f"Data deletion request: {name}",
            heading="Someone asked for their personal data to be deleted",
            paragraphs=[
                f"{name} ({p['email']}) asked to have their data erased "
                "(Barbados Data Protection Act 2019). An administrator erases the account."
            ],
            link=self.sia(f"/admin/accounts/{p['userId']}"),
            button="Open the account",
        )

    # ------------------------------------------------------------------ requests

    async def submitted(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        kind = "Pro Bono request" if p.get("type") == "PROBONO" else "Request"
        return await self.staff(
            "order",
            subject=f"New {kind.lower()} {p['orderId']}",
            heading=f"New {kind.lower()}",
            request_id=p["orderId"],
            facts=[("Items", str(len(p.get("lines") or [])))],
            link=self.sia(f"/requests/{p['orderId']}"),
            button="Open the request",
        )

    async def quoted(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        return await self.to_customer(
            e,
            subject=f"Your quote is ready ({p['orderId']})",
            heading="Your quote is ready",
            paragraphs=["Choose CIMH stock or the supplier for each item, then sign the agreement."],
            request_id=p["orderId"],
            status=("Quoted", INFO),
            facts=[("Valid until", _date(p.get("expiresAt"))), ("Currency", p.get("currency", ""))],
            link=self.shop(f"/requests/{p['orderId']}"),
            button="View the quote",
        )

    async def quote_revised(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        return await self.to_customer(
            e,
            subject=f"Your quote was updated ({p['orderId']})",
            heading="Your quote was updated",
            paragraphs=[f"CIMH sent a new {p.get('reason') or 'quote version'}. Please review it before you choose."],
            request_id=p["orderId"],
            status=("Quoted", INFO),
            link=self.shop(f"/requests/{p['orderId']}"),
            button="View the quote",
        )

    async def quote_expiring(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        return await self.to_customer(
            e,
            subject=f"Your quote expires soon ({p['orderId']})",
            heading="Your quote expires soon",
            paragraphs=["Accept it with a signed agreement before it expires, or it will be cancelled."],
            request_id=p["orderId"],
            status=("Expires soon", WARNING),
            facts=[("Valid until", _date(p.get("expiresAt")))],
            link=self.shop(f"/requests/{p['orderId']}"),
            button="View the quote",
        )

    async def expired(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        return await self.to_customer(
            e,
            subject=f"Your quote has expired ({p['orderId']})",
            heading="Your quote has expired",
            paragraphs=["The request was cancelled. You can submit a new request at any time."],
            request_id=p["orderId"],
            status=("Cancelled", ERROR),
            link=self.shop(f"/requests/{p['orderId']}"),
            button="View the request",
        )

    async def agreement_rejected(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        return await self.to_customer(
            e,
            subject=f"Please upload the signed agreement again ({p['orderId']})",
            heading="We couldn't accept the signed agreement",
            paragraphs=[
                f"Reason: {p.get('reason') or 'not given'}",
                "Download the agreement, sign it and upload it again.",
            ],
            request_id=p["orderId"],
            status=("Agreement to sign", WARNING),
            link=self.shop(f"/requests/{p['orderId']}/agreement"),
            button="Upload it again",
        )

    async def shipped(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        if p.get("notifyCustomer") is False:
            return []
        carrier = p.get("carrier") or ""
        facts = [("Carrier", CARRIERS.get(carrier, carrier))]
        if p.get("tracking"):
            facts.append(("Tracking number", p["tracking"]))
            if carrier in TRACK:
                facts.append(("Track it", TRACK[carrier].format(quote(p["tracking"]))))
        return await self.to_customer(
            e,
            subject=f"Your request has shipped ({p['orderId']})",
            heading="On its way",
            request_id=p["orderId"],
            status=("Shipped", INFO),
            facts=facts,
            paragraphs=["Supplier items may arrive separately, straight from the supplier."],
            link=self.shop(f"/requests/{p['orderId']}"),
            button="View the request",
        )

    async def delivered(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        note = (
            "The delivery note is attached to the request."
            if p.get("orderType") == "PROBONO"
            else "The invoice is attached to the request."
        )
        return await self.to_customer(
            e,
            subject=f"Delivered ({p['orderId']})",
            heading="Your request was delivered",
            paragraphs=[note],
            request_id=p["orderId"],
            status=("Delivered", SUCCESS),
            link=self.shop(f"/requests/{p['orderId']}"),
            button="View the request",
        )

    async def probono_rejected(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        return await self.to_customer(
            e,
            subject=f"Your Pro Bono request ({p['orderId']})",
            heading="We couldn't approve your Pro Bono request",
            paragraphs=[f"Reason: {p.get('reason') or 'not given'}"],
            request_id=p["orderId"],
            status=("Rejected", ERROR),
            link=self.shop(f"/requests/{p['orderId']}"),
            button="View the request",
        )

    async def cancelled(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        reason = [f"Reason: {p['reason']}"] if p.get("reason") else []
        out = await self.to_customer(
            e,
            subject=f"Request cancelled ({p['orderId']})",
            heading="Your request was cancelled",
            paragraphs=reason,
            request_id=p["orderId"],
            status=("Cancelled", ERROR),
            link=self.shop(f"/requests/{p['orderId']}"),
            button="View the request",
        )
        out += await self.staff(
            "cancellation",
            subject=f"Request cancelled: {p['orderId']}",
            heading="A request was cancelled",
            paragraphs=reason,
            request_id=p["orderId"],
            link=self.sia(f"/requests/{p['orderId']}"),
            button="Open the request",
        )
        return out

    async def declined(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        reason = [f"Reason: {p['reason']}"] if p.get("reason") else []
        return await self.staff(
            "cancellation",
            subject=f"Quote declined: {p['orderId']}",
            heading="The customer declined the quote",
            paragraphs=reason,
            request_id=p["orderId"],
            link=self.sia(f"/requests/{p['orderId']}"),
            button="Open the request",
        )

    # ------------------------------------------------------------------ documents and stock

    async def document(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        rid, kind = p["orderId"], p.get("kind")
        if e.type == "document.generated" and kind == "agreement":
            acc = await self.customer(p.get("customer"))
            if acc is None:
                return []
            return [
                Message(
                    to=acc["email"],
                    why=REQUEST_WHY,
                    subject=f"Your agreement is ready to sign ({rid})",
                    heading="Your agreement is ready",
                    paragraphs=["Download it, sign it, and upload the signed copy to accept the quote."],
                    request_id=rid,
                    status=("Agreement to sign", WARNING),
                    link=self.shop(f"/requests/{rid}/agreement"),
                    button="Download and sign",
                )
            ]
        if e.type == "document.uploaded" and kind == "signed_agreement":
            return await self.staff(
                "order",
                subject=f"Signed agreement received: {rid}",
                heading="A signed agreement was uploaded",
                paragraphs=["Check the signature, then verify it or reject it with a reason."],
                request_id=rid,
                link=self.sia(f"/requests/{rid}"),
                button="Check the signature",
            )
        if e.type == "document.generated" and kind in ("invoice", "probono_invoice"):
            return await self.staff(
                "invoice",
                subject=f"Invoice ready: {rid}",
                heading="An invoice was generated",
                request_id=rid,
                link=self.sia(f"/requests/{rid}"),
                button="Open the request",
            )
        return []

    async def stock_low(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        return await self.staff(
            "lowStock",
            subject=f"Low stock: {p['productId']}",
            heading="A product is running low",
            status=("Low stock", WARNING),
            facts=[
                ("Product", p["productId"]),
                ("Available", str(p.get("available"))),
                ("Threshold", str(p.get("threshold"))),
            ],
            link=self.sia("/reports/stock"),
            button="Open the stock report",
        )

    async def reservation_failed(self, e: EventEnvelope) -> list[Message]:
        p = e.payload
        short = ", ".join(f"{x['lineId']}: {x.get('available')} of {x.get('requested')}" for x in p.get("lines") or [])
        return await self.staff(
            "order",
            subject=f"Stock could not be reserved: {p['orderId']}",
            heading="Stock could not be reserved",
            paragraphs=["CIMH stock ran out between the quote and the acceptance. Requote the short lines."],
            request_id=p["orderId"],
            status=("Reservation failed", ERROR),
            facts=[("Short", short)],
            link=self.sia(f"/requests/{p['orderId']}/quote"),
            button="Requote",
        )

    ROUTES: ClassVar[dict[str, Callable[[Notifier, EventEnvelope], Awaitable[list[Message]]]]] = {}


Notifier.ROUTES = {
    "user.registered": Notifier.registered,
    "user.password_reset_requested": Notifier.password_reset,
    "user.email_change_requested": Notifier.email_change,
    "user.verified": Notifier.verified,
    "user.approval_pending": Notifier.approval_pending,
    "user.approved": Notifier.approved,
    "user.rejected": Notifier.rejected,
    "user.erasure_requested": Notifier.erasure_requested,
    "order.submitted": Notifier.submitted,
    "order.quoted": Notifier.quoted,
    "order.quote_revised": Notifier.quote_revised,
    "order.quote_expiring": Notifier.quote_expiring,
    "order.expired": Notifier.expired,
    "order.agreement_rejected": Notifier.agreement_rejected,
    "order.shipped": Notifier.shipped,
    "order.delivered": Notifier.delivered,
    "order.probono_rejected": Notifier.probono_rejected,
    "order.cancelled": Notifier.cancelled,
    "order.declined": Notifier.declined,
    "document.generated": Notifier.document,
    "document.uploaded": Notifier.document,
    "stock.low": Notifier.stock_low,
    "stock.reservation_failed": Notifier.reservation_failed,
}
