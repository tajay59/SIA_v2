"""P6 exit criterion: each email is sent exactly once per event, with the right link (APD §7)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fakeredis.aioredis
import httpx
import pytest
from jsonschema import Draft202012Validator

from cimh_common.consumer import envelope_bytes
from cimh_common.outbox import EventEnvelope
from notification_svc.clients import HttpDirectory, Settings, Unavailable
from notification_svc.handlers import Notifier
from notification_svc.templates import Message, Rendered, render

SCHEMAS = Path(__file__).resolve().parents[3] / "packages" / "event-schemas" / "schemas"
SHOP, SIA = "https://store.test", "https://sia.test"
LISTS = {
    "registration": ["admin1@cimh.edu.bb", "admin2@cimh.edu.bb"],
    "order": ["orders@cimh.edu.bb"],
    "invoice": ["finance@cimh.edu.bb"],
    "cancellation": ["orders@cimh.edu.bb"],
    "lowStock": ["stores@cimh.edu.bb"],
}
ACCOUNTS = {
    "USRUSER": {"id": "USRUSER", "email": "una@met.bb", "firstname": "Una", "status": "ACTIVE"},
    "USRGONE": {"id": "USRGONE", "email": "gone@met.bb", "firstname": "Gone", "status": "SUSPENDED"},
}


@dataclass
class FakeDirectory:
    codes: dict[str, str] = field(default_factory=lambda: {"TMP1": "123456"})
    claimed: list[str] = field(default_factory=list)
    forgotten: list[str] = field(default_factory=list)

    async def account(self, account_id: str) -> dict[str, Any] | None:
        return ACCOUNTS.get(account_id)

    async def claim_code(self, code_ref: str) -> str | None:
        self.claimed.append(code_ref)
        return self.codes.get(code_ref)

    async def forget_code(self, code_ref: str) -> None:
        self.forgotten.append(code_ref)

    async def staff_list(self, name: str) -> list[str]:
        return LISTS[name]


@dataclass
class FakeMailer:
    sent: list[Rendered] = field(default_factory=list)
    fail_after: int | None = None

    async def send(self, message: Rendered, message_id: str) -> None:
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise Unavailable("smtp down")
        self.sent.append(message)


@pytest.fixture
def env() -> tuple[Notifier, FakeMailer, FakeDirectory]:
    mailer, directory = FakeMailer(), FakeDirectory()
    s = Settings(shop_url=SHOP, sia_url=SIA)
    return Notifier(s, directory, mailer, fakeredis.aioredis.FakeRedis()), mailer, directory


def user(**kw: Any) -> dict[str, Any]:
    return {
        "userId": "USRUSER",
        "email": "una@met.bb",
        "firstname": "Una",
        "lastname": "User",
        "role": "user",
        "status": "ACTIVE",
        "isCimh": False,
        "organisationId": None,
        **kw,
    }


def ev(etype: str, payload: dict[str, Any]) -> EventEnvelope:
    e = EventEnvelope(type=etype, correlationId="c1", payload=payload)
    index = json.loads((SCHEMAS / "index.json").read_text(encoding="utf-8"))
    schema = json.loads((SCHEMAS / index[etype]).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(json.loads(envelope_bytes(e)))  # only real event shapes
    return e


def run(n: Notifier, e: EventEnvelope) -> int:
    return asyncio.run(n.handle(e))


ORDER = {"orderId": "ORD9", "customer": "USRUSER"}
MOVE = {**ORDER, "orderType": "PAID", "from": "X", "to": "Y"}

# (event type, payload, recipients, link the button opens)
CASES = [
    (
        "user.registered",
        user(status="PENDING_VERIFICATION", codeRef="TMP1"),
        ["una@met.bb"],
        f"{SHOP}/verify?email=una%40met.bb",
    ),
    (
        "user.password_reset_requested",
        user(codeRef="TMP1"),
        ["una@met.bb"],
        f"{SHOP}/reset-password?email=una%40met.bb",
    ),
    (
        "user.password_reset_requested",
        user(role="staff", codeRef="TMP1"),
        ["una@met.bb"],
        f"{SIA}/reset-password?email=una%40met.bb",
    ),
    ("user.email_change_requested", user(codeRef="TMP1", newEmail="new@met.bb"), ["new@met.bb"], f"{SHOP}/account"),
    ("user.verified", user(status="PENDING_APPROVAL"), ["una@met.bb", *LISTS["registration"]], None),
    (
        "user.approval_pending",
        user(status="PENDING_APPROVAL", waitingSince="2026-11-01T00:00:00Z"),
        LISTS["registration"],
        f"{SIA}/admin/approvals",
    ),
    ("user.approved", user(), ["una@met.bb"], f"{SHOP}/login"),
    ("user.rejected", user(status="REJECTED", reason="Unknown organisation"), ["una@met.bb"], f"{SHOP}/"),
    (
        "user.erasure_requested",
        user(requestedAt="2026-11-08T00:00:00Z"),
        LISTS["registration"],
        f"{SIA}/admin/accounts/USRUSER",
    ),
    ("order.submitted", {**ORDER, "type": "PAID", "lines": []}, LISTS["order"], f"{SIA}/requests/ORD9"),
    (
        "order.quoted",
        {**ORDER, "quoteVersion": 1, "expiresAt": "2026-12-08T00:00:00Z", "currency": "BBD"},
        ["una@met.bb"],
        f"{SHOP}/requests/ORD9",
    ),
    ("order.quote_revised", MOVE, ["una@met.bb"], f"{SHOP}/requests/ORD9"),
    (
        "order.quote_expiring",
        {**ORDER, "quoteVersion": 1, "expiresAt": "2026-12-08T00:00:00Z"},
        ["una@met.bb"],
        f"{SHOP}/requests/ORD9",
    ),
    ("order.expired", MOVE, ["una@met.bb"], f"{SHOP}/requests/ORD9"),
    ("order.agreement_rejected", {**MOVE, "reason": "Not signed"}, ["una@met.bb"], f"{SHOP}/requests/ORD9/agreement"),
    (
        "order.shipped",
        {**ORDER, "carrier": "DHL", "tracking": "JD0001", "notifyCustomer": True},
        ["una@met.bb"],
        f"{SHOP}/requests/ORD9",
    ),
    ("order.delivered", MOVE, ["una@met.bb"], f"{SHOP}/requests/ORD9"),
    (
        "order.probono_rejected",
        {**MOVE, "orderType": "PROBONO", "reason": "Limit"},
        ["una@met.bb"],
        f"{SHOP}/requests/ORD9",
    ),
    (
        "order.cancelled",
        {**ORDER, "reason": "No longer needed", "auto": False},
        ["una@met.bb", *LISTS["cancellation"]],
        None,
    ),
    ("order.declined", {**MOVE, "reason": "Too expensive"}, LISTS["cancellation"], f"{SIA}/requests/ORD9"),
    (
        "document.generated",
        {
            "orderId": "ORD9",
            "customer": "USRUSER",
            "fileId": "FIL1",
            "kind": "agreement",
            "name": "a.pdf",
            "mime": "application/pdf",
            "size": 1,
            "sha256": "0",
        },
        ["una@met.bb"],
        f"{SHOP}/requests/ORD9/agreement",
    ),
    (
        "document.generated",
        {
            "orderId": "ORD9",
            "fileId": "FIL2",
            "kind": "invoice",
            "name": "i.pdf",
            "mime": "application/pdf",
            "size": 1,
            "sha256": "0",
        },
        LISTS["invoice"],
        f"{SIA}/requests/ORD9",
    ),
    (
        "document.uploaded",
        {
            "orderId": "ORD9",
            "fileId": "FIL3",
            "kind": "signed_agreement",
            "name": "s.pdf",
            "mime": "application/pdf",
            "size": 1,
            "sha256": "0",
        },
        LISTS["order"],
        f"{SIA}/requests/ORD9",
    ),
    ("stock.low", {"productId": "MET1", "available": 1, "threshold": 2}, LISTS["lowStock"], f"{SIA}/reports/stock"),
    (
        "stock.reservation_failed",
        {"orderId": "ORD9", "lines": [{"lineId": "L1", "requested": 2, "available": 1}]},
        LISTS["order"],
        f"{SIA}/requests/ORD9/quote",
    ),
]


@pytest.mark.req("N1")
@pytest.mark.parametrize(("etype", "payload", "to", "link"), CASES, ids=[f"{c[0]}-{i}" for i, c in enumerate(CASES)])
def test_each_email_once_with_the_right_link(
    env: tuple[Notifier, FakeMailer, FakeDirectory],
    etype: str,
    payload: dict[str, Any],
    to: list[str],
    link: str | None,
) -> None:
    n, mailer, _ = env
    e = ev(etype, payload)
    assert run(n, e) == len(to)
    assert sorted(m.to for m in mailer.sent) == sorted(to)
    for m in mailer.sent:
        assert m.subject
        assert m.text.strip()
        assert m.html.startswith("<!doctype html>")
    if link:
        for m in mailer.sent:
            assert f'href="{link.replace("&", "&amp;")}"' in m.html
            assert link in m.text  # plain-text part carries the link too
    assert run(n, e) == 0  # redelivery of the same event: nothing more
    assert len(mailer.sent) == len(to)


def test_verify_code_is_shown_claimed_once_and_forgotten(env: tuple[Notifier, FakeMailer, FakeDirectory]) -> None:
    n, mailer, directory = env
    run(n, ev("user.registered", user(status="PENDING_VERIFICATION", codeRef="TMP1")))
    assert "123456" in mailer.sent[0].html
    assert "123456" in mailer.sent[0].text
    assert directory.claimed == ["TMP1"]
    assert directory.forgotten == ["TMP1"]


def test_code_already_claimed_sends_nothing(env: tuple[Notifier, FakeMailer, FakeDirectory]) -> None:
    n, mailer, _ = env
    assert run(n, ev("user.registered", user(status="PENDING_VERIFICATION", codeRef="TMPGONE"))) == 0
    assert mailer.sent == []


def test_retry_after_a_partial_failure_sends_only_the_missing(env: tuple[Notifier, FakeMailer, FakeDirectory]) -> None:
    n, mailer, _ = env
    e = ev("user.verified", user(status="PENDING_APPROVAL"))  # 3 recipients
    mailer.fail_after = 1
    with pytest.raises(Unavailable):
        run(n, e)  # -> retry topic
    mailer.fail_after = None
    assert run(n, e) == 2
    assert sorted(m.to for m in mailer.sent) == sorted(["una@met.bb", *LISTS["registration"]])


@pytest.mark.parametrize(
    ("etype", "payload"),
    [
        (
            "order.quoted",
            {**ORDER, "customer": "USRGONE", "quoteVersion": 1, "expiresAt": "2026-12-08T00:00:00Z", "currency": "BBD"},
        ),  # suspended
        ("order.delivered", {**MOVE, "customer": "USRNOBODY"}),  # erased
        ("order.shipped", {**ORDER, "carrier": "HAND", "tracking": None, "notifyCustomer": False}),
        ("user.verified", user(status="ACTIVE", isCimh=True)),  # @cimh: user.approved (auto) mails them
        (
            "document.generated",
            {
                "orderId": "ORD9",
                "fileId": "F",
                "kind": "labels",
                "name": "l.pdf",
                "mime": "application/pdf",
                "size": 1,
                "sha256": "0",
            },
        ),
        ("stock.changed", {"productId": "MET1", "available": 3, "reserved": 0}),
        ("order.accepted", {**ORDER, "quoteVersion": 1, "lines": []}),
    ],
)
def test_no_email(env: tuple[Notifier, FakeMailer, FakeDirectory], etype: str, payload: dict[str, Any]) -> None:
    n, mailer, _ = env
    assert run(n, ev(etype, payload)) == 0
    assert mailer.sent == []


def test_shipped_has_tracking_and_carrier_link(env: tuple[Notifier, FakeMailer, FakeDirectory]) -> None:
    n, mailer, _ = env
    run(n, ev("order.shipped", {**ORDER, "carrier": "FEDEX", "tracking": "7777", "notifyCustomer": True}))
    text = mailer.sent[0].text
    assert "FedEx" in text
    assert "7777" in text
    assert "fedex.com/fedextrack/?trknbr=7777" in text


def test_values_are_escaped() -> None:
    r = render(
        Message(
            to="a@b.c",
            subject="<x>",
            heading="<script>alert(1)</script>",
            paragraphs=["a & b"],
            link='https://x.test/"onmouseover=',
            button="Go",
        )
    )
    assert "<script>" not in r.html
    assert "&lt;script&gt;" in r.html
    assert "a &amp; b" in r.html
    assert '"onmouseover' not in r.html


# ---------------------------------------------------------------- HTTP directory


def _transport(calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/service-token"):
            return httpx.Response(200, json={"token": "t", "expiresIn": 300})
        if request.url.path.endswith("/internal/email-lists"):
            members = [{"accountId": "A", "email": "a@cimh.edu.bb"}, {"accountId": "B", "email": "a@cimh.edu.bb"}]
            return httpx.Response(
                200, json={"registration": [], "order": members, "invoice": [], "cancellation": [], "lowStock": []}
            )
        if request.url.path.endswith("/internal/codes/TMP1") and calls.count(request.url.path) == 1:
            return httpx.Response(
                200,
                json={"code": "654321", "kind": "verify_email", "accountId": "A", "expiresAt": "2026-11-08T00:00:00Z"},
            )
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


def test_lists_are_cached_and_codes_parked_until_sent() -> None:
    calls: list[str] = []
    d = HttpDirectory(Settings(service_secret="s"), fakeredis.aioredis.FakeRedis(), transport=_transport(calls))

    async def go() -> None:
        assert await d.staff_list("order") == ["a@cimh.edu.bb"]  # deduplicated
        assert await d.staff_list("order") == ["a@cimh.edu.bb"]
        assert await d.claim_code("TMP1") == "654321"
        assert await d.claim_code("TMP1") == "654321"  # a retry after a failed send still has it
        await d.forget_code("TMP1")
        assert await d.claim_code("TMP1") is None  # identity gives it once
        assert await d.account("USRX") is None

    asyncio.run(go())
    assert calls.count("/api/catalog/v1/internal/email-lists") == 1
    assert calls.count("/api/identity/v1/internal/codes/TMP1") == 2  # first claim + the one after forgetting


def test_old_events_are_not_emailed(env: tuple[Notifier, FakeMailer, FakeDirectory]) -> None:
    from datetime import UTC, datetime, timedelta

    n, mailer, _ = env
    e = ev("order.delivered", MOVE).model_copy(update={"occurredAt": datetime.now(UTC) - timedelta(days=3)})
    assert run(n, e) == 0
    assert mailer.sent == []
