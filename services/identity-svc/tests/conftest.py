from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from cimh_common.testing import AsyncMongoMock
from identity_svc.config import Settings
from identity_svc.main import BASE, build_app
from identity_svc.security import hash_password, new_totp_secret, totp_now
from identity_svc.store import now

BREACHED = "password123456"  # treated as breached by the fake checker
GOOD_PW = "correct horse battery staple"


async def fake_breach(pw: str) -> bool:
    return pw == BREACHED


class Ctx:
    def __init__(self) -> None:
        self.db = AsyncMongoMock()
        self.redis = fakeredis.aioredis.FakeRedis()
        settings = Settings(service_secrets={"notification": "n-secret", "order": "o-secret"}, cookie_secure=True)
        self.app = build_app(settings, db=self.db, redis=self.redis, breach_check=fake_breach, configure_logs=False)
        self.client = TestClient(self.app, base_url="https://testserver")
        self.loop = asyncio.new_event_loop()

    def run(self, coro: Any) -> Any:
        return self.loop.run_until_complete(coro)

    def url(self, path: str) -> str:
        return BASE + path

    def code(self, email: str, kind: str = "verify_email") -> str:
        """Read the sealed code the way notification-svc would (without consuming it)."""
        svc = self.app.state.identity

        async def get() -> str:
            acc = await self.db["accounts"].find_one({"email": email})
            q: dict[str, Any] = {"kind": kind}
            if kind == "change_email":
                q["newEmail"] = email
            else:
                q["accountId"] = acc["id"]
            doc = await self.db["temp"].find_one(q)
            return str(svc.env.open(doc["codeEnc"], doc["id"]))

        return str(self.run(get()))

    def account(self, email: str) -> dict[str, Any]:
        return dict(self.run(self.db["accounts"].find_one({"email": email})))

    def seed_account(
        self,
        email: str,
        role: str = "user",
        status: str = "ACTIVE",
        mfa_secret: str | None = None,
        org: str | None = None,
        password: str = GOOD_PW,
    ) -> dict[str, Any]:
        svc = self.app.state.identity
        acc: dict[str, Any] = {
            "id": f"USR{abs(hash(email)) % 10**10:010d}",
            "email": email,
            "passwordHash": hash_password(password),
            "firstname": "Test",
            "lastname": email.split("@")[0],
            "role": role,
            "status": status,
            "isCimh": email.endswith("@cimh.edu.bb"),
            "organisationId": org,
            "addresses": [],
            "statusHistory": [],
            "failedLogins": {"count": 0, "lockouts": 0},
            "mfa": {"enabled": bool(mfa_secret)},
            "createdAt": now(),
            "version": 1,
            "outbox": [],
        }
        if mfa_secret:
            acc["mfa"]["totpSecretEnc"] = svc.env.seal(mfa_secret, acc["id"])
        self.run(self.db["accounts"].insert_one(acc))
        return acc

    def login(
        self, email: str, password: str = GOOD_PW, totp: str | None = None, client: str = "mobile"
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"email": email, "password": password, "client": client}
        if totp:
            body["totp"] = totp
        r = self.client.post(self.url("/auth/login"), json=body)
        assert r.status_code == 200, r.text
        return dict(r.json())

    def bearer(self, email: str, **kw: Any) -> dict[str, str]:
        return {"Authorization": "Bearer " + self.login(email, **kw)["accessToken"]}

    def admin(self) -> tuple[dict[str, Any], dict[str, str]]:
        secret = new_totp_secret()
        acc = self.seed_account("boss@cimh.edu.bb", role="admin", mfa_secret=secret)
        return acc, self.bearer(acc["email"], totp=totp_now(secret))


@pytest.fixture
def ctx() -> Iterator[Ctx]:
    c = Ctx()
    with c.client:
        yield c
    c.loop.close()
