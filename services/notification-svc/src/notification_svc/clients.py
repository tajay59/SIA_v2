"""What notification-svc talks to (TAD §4.6).

identity  GET /internal/accounts/{id}   name + email of the person an event is about
          GET /internal/codes/{ref}     a one-time code, claimable ONCE (5th sync call, TAD)
catalog   GET /internal/email-lists     staff distribution lists, cached in Redis for 5 minutes
SMTP      the CIMH mail relay (production) or Mailpit (dev, staging-lite: nothing reaches real people)
"""

from __future__ import annotations

import asyncio
import json
import os
import smtplib
import ssl
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any, Protocol

import httpx

from cimh_common.settings import read_secret

from .templates import Rendered


class Unavailable(Exception):
    """A dependency failed; the event is retried (retry topic), then dead-lettered."""


@dataclass(frozen=True)
class Settings:
    shop_url: str = "http://localhost:15173"
    sia_url: str = "http://localhost:15174"
    identity_url: str = "http://identity-svc:8000"
    catalog_url: str = "http://catalog-svc:8000"
    service_secret: str | None = None
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    mail_from: str = "CIMH Stores <stores@cimh.edu.bb>"
    max_event_age_hours: int = 48  # older events (a replay, a DLQ re-drive weeks later) are not emailed

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        return cls(
            shop_url=env("SHOP_URL", cls.shop_url).rstrip("/"),
            sia_url=env("SIA_URL", cls.sia_url).rstrip("/"),
            identity_url=env("IDENTITY_URL", cls.identity_url),
            catalog_url=env("CATALOG_URL", cls.catalog_url),
            service_secret=read_secret("SERVICE_SECRET"),
            smtp_host=env("SMTP_HOST", cls.smtp_host),
            smtp_port=int(env("SMTP_PORT", str(cls.smtp_port))),
            smtp_user=env("SMTP_USER") or None,
            smtp_password=read_secret("SMTP_PASSWORD"),
            smtp_starttls=(env("SMTP_STARTTLS", "false").lower() in ("1", "true", "yes")),
            mail_from=env("MAIL_FROM", cls.mail_from),
            max_event_age_hours=int(env("MAX_EVENT_AGE_HOURS", str(cls.max_event_age_hours))),
        )


class Directory(Protocol):
    async def account(self, account_id: str) -> dict[str, Any] | None: ...
    async def claim_code(self, code_ref: str) -> str | None: ...
    async def staff_list(self, name: str) -> list[str]: ...
    async def forget_code(self, code_ref: str) -> None: ...


class Mailer(Protocol):
    async def send(self, message: Rendered, message_id: str) -> None: ...


class HttpDirectory:
    LIST_TTL = 300

    def __init__(
        self,
        s: Settings,
        redis: Any,
        *,
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.identity = s.identity_url.rstrip("/") + "/api/identity/v1"
        self.catalog = s.catalog_url.rstrip("/") + "/api/catalog/v1"
        self.secret = s.service_secret or ""
        self.redis, self.timeout, self.transport = redis, timeout, transport
        self._token: str | None = None
        self._until = 0.0

    async def _get(self, url: str) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                if not self._token or time.monotonic() >= self._until:
                    t = await client.post(
                        self.identity + "/internal/service-token",
                        json={"service": "notification", "secret": self.secret},
                    )
                    t.raise_for_status()
                    body = t.json()
                    self._token = str(body["token"])
                    self._until = time.monotonic() + max(30, int(body.get("expiresIn", 300)) - 30)
                r = await client.get(url, headers={"Authorization": f"Bearer {self._token}"})
        except httpx.HTTPError as exc:
            raise Unavailable(str(exc)) from exc
        if r.status_code >= 500 or r.status_code in (401, 403):
            raise Unavailable(f"{url}: {r.status_code}")
        return r

    async def account(self, account_id: str) -> dict[str, Any] | None:
        r = await self._get(f"{self.identity}/internal/accounts/{account_id}")
        return None if r.status_code == 404 else dict(r.json())

    async def claim_code(self, code_ref: str) -> str | None:
        """Claimable once: the code is parked in Redis (15 min, our own key space) until the email is sent, so a
        failed send can be retried without losing it."""
        key = f"ntf:code:{code_ref}"
        cached = await self.redis.get(key)
        if cached is not None:
            return cached.decode() if isinstance(cached, bytes) else str(cached)
        r = await self._get(f"{self.identity}/internal/codes/{code_ref}")
        if r.status_code == 404:
            return None  # already used or expired
        code = str(r.json()["code"])
        await self.redis.set(key, code, ex=900)
        return code

    async def forget_code(self, code_ref: str) -> None:
        await self.redis.delete(f"ntf:code:{code_ref}")

    async def staff_list(self, name: str) -> list[str]:
        raw = await self.redis.get("ntf:lists")
        if raw is None:
            lists = (await self._get(f"{self.catalog}/internal/email-lists")).json()
            await self.redis.set("ntf:lists", json.dumps(lists), ex=self.LIST_TTL)
        else:
            lists = json.loads(raw)
        return sorted({m["email"] for m in lists.get(name) or [] if m.get("email")})


class SmtpMailer:
    def __init__(self, s: Settings) -> None:
        self.s = s

    def _send(self, m: Rendered, message_id: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.s.mail_from
        msg["To"] = m.to
        msg["Subject"] = m.subject
        msg["Message-ID"] = make_msgid(idstring=message_id, domain="stores.cimh.edu.bb")
        msg["Auto-Submitted"] = "auto-generated"
        msg.set_content(m.text)
        msg.add_alternative(m.html, subtype="html")
        with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=30) as smtp:
            if self.s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self.s.smtp_user and self.s.smtp_password:
                smtp.login(self.s.smtp_user, self.s.smtp_password)
            smtp.send_message(msg)

    async def send(self, message: Rendered, message_id: str) -> None:
        try:
            await asyncio.to_thread(self._send, message, message_id)
        except (OSError, smtplib.SMTPException) as exc:
            raise Unavailable(f"smtp: {exc}") from exc
