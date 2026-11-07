"""Registration, verification, login, lockout, MFA, refresh rotation, logout, passwords (A1-A9, TR-AUTH-*)."""

from __future__ import annotations

import time

import pytest

from identity_svc.security import new_totp_secret, totp_now

from .conftest import BREACHED, GOOD_PW, Ctx

REG = {
    "firstname": "Ana",
    "lastname": "Lee",
    "email": "ana@met.gd",
    "password": GOOD_PW,
    "organisationText": "Grenada Met Office",
    "country": "GD",
}


def register(ctx: Ctx, **over: object) -> None:
    r = ctx.client.post(ctx.url("/auth/register"), json={**REG, **over})
    assert r.status_code == 202, r.text


@pytest.mark.req("A1")
def test_register_verify_pending_approval(ctx: Ctx) -> None:
    register(ctx)
    acc = ctx.account("ana@met.gd")
    assert acc["status"] == "PENDING_VERIFICATION"
    assert acc["passwordHash"].startswith("$argon2id$")
    assert [e["type"] for e in acc["outbox"]] == ["user.registered"]
    assert "codeRef" in acc["outbox"][0]["payload"]
    assert "code" not in acc["outbox"][0]["payload"]  # code never in an event

    r = ctx.client.post(ctx.url("/auth/verify"), json={"email": "ana@met.gd", "code": ctx.code("ana@met.gd")})
    assert r.json() == {"status": "PENDING_APPROVAL"}
    acc = ctx.account("ana@met.gd")
    assert acc["outbox"][-1]["type"] == "user.verified"
    assert acc["version"] == 2

    # not ACTIVE yet -> 403 with a specific code
    r = ctx.client.post(ctx.url("/auth/login"), json={"email": "ana@met.gd", "password": GOOD_PW})
    assert r.status_code == 403
    assert r.json()["code"] == "ACCOUNT_PENDING_APPROVAL"


@pytest.mark.req("A2")
def test_cimh_email_auto_activates(ctx: Ctx) -> None:
    register(ctx, email="tech@cimh.edu.bb", organisationText=None)
    r = ctx.client.post(
        ctx.url("/auth/verify"), json={"email": "tech@cimh.edu.bb", "code": ctx.code("tech@cimh.edu.bb")}
    )
    assert r.json()["status"] == "ACTIVE"
    evt = ctx.account("tech@cimh.edu.bb")["outbox"][-1]
    assert evt["type"] == "user.approved"
    assert evt["payload"]["auto"] is True
    assert ctx.login("tech@cimh.edu.bb")["account"]["isCimh"] is True


def test_register_requires_org_for_members_and_rejects_unknown_fields(ctx: Ctx) -> None:
    r = ctx.client.post(ctx.url("/auth/register"), json={**REG, "organisationText": ""})
    assert r.status_code == 422
    r = ctx.client.post(ctx.url("/auth/register"), json={**REG, "role": "admin"})
    assert r.status_code == 422


@pytest.mark.req("TR-AUTH-7")
def test_password_policy(ctx: Ctx) -> None:
    r = ctx.client.post(ctx.url("/auth/register"), json={**REG, "password": "short"})
    assert r.status_code == 422
    r = ctx.client.post(ctx.url("/auth/register"), json={**REG, "password": BREACHED})
    assert r.status_code == 422
    assert r.json()["code"] == "PASSWORD_BREACHED"


def test_duplicate_registration_is_silent(ctx: Ctx) -> None:
    register(ctx)
    register(ctx)  # still 202; no enumeration
    assert ctx.run(ctx.db["accounts"].count_documents({"email": "ana@met.gd"})) == 1


@pytest.mark.req("TR-AUTH-8")
def test_code_attempts_and_expiry(ctx: Ctx) -> None:
    register(ctx)
    good = ctx.code("ana@met.gd")
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        r = ctx.client.post(ctx.url("/auth/verify"), json={"email": "ana@met.gd", "code": bad})
        assert r.json()["code"] == "CODE_INVALID"
    r = ctx.client.post(ctx.url("/auth/verify"), json={"email": "ana@met.gd", "code": good})
    assert r.json()["code"] == "CODE_EXPIRED"  # 5 attempts used
    # unknown email looks the same as a wrong code
    r = ctx.client.post(ctx.url("/auth/verify"), json={"email": "nobody@x.org", "code": "123456"})
    assert r.json()["code"] == "CODE_INVALID"


def test_resend_limited_to_three_per_hour(ctx: Ctx) -> None:
    register(ctx)  # first send
    assert ctx.client.post(ctx.url("/auth/verify/resend"), json={"email": "ana@met.gd"}).status_code == 202
    assert ctx.client.post(ctx.url("/auth/verify/resend"), json={"email": "ana@met.gd"}).status_code == 202
    assert ctx.client.post(ctx.url("/auth/verify/resend"), json={"email": "ana@met.gd"}).status_code == 429
    # unknown address: still 202
    assert ctx.client.post(ctx.url("/auth/verify/resend"), json={"email": "x@y.org"}).status_code == 202


@pytest.mark.req("A6")
def test_web_login_sets_cookies_and_csrf(ctx: Ctx) -> None:
    ctx.seed_account("u@met.bb")
    r = ctx.client.post(ctx.url("/auth/login"), json={"email": "u@met.bb", "password": GOOD_PW})
    assert r.status_code == 200
    assert "accessToken" not in r.json()
    cookies = r.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith("access_token="))
    assert "HttpOnly" in access
    assert "Secure" in access
    assert "samesite=lax" in access.lower()
    assert any(c.startswith("csrf_token=") and "HttpOnly" not in c for c in cookies)
    # cookie auth works for reads; writes need the CSRF header
    assert ctx.client.get(ctx.url("/me")).status_code == 200
    csrf = ctx.client.cookies.get("csrf_token")
    r = ctx.client.post(ctx.url("/me/password"), json={"currentPassword": GOOD_PW, "newPassword": "another long pass"})
    assert r.status_code == 403
    r = ctx.client.post(
        ctx.url("/me/password"),
        headers={"X-CSRF-Token": csrf},
        json={"currentPassword": GOOD_PW, "newPassword": "another long pass"},
    )
    assert r.status_code == 204


def test_login_wrong_password_generic(ctx: Ctx) -> None:
    ctx.seed_account("u@met.bb")
    for email in ("u@met.bb", "ghost@met.bb"):
        r = ctx.client.post(ctx.url("/auth/login"), json={"email": email, "password": "wrong password!"})
        assert r.status_code == 401
        assert r.json()["code"] == "INVALID_CREDENTIALS"


@pytest.mark.req("TR-AUTH-6")
def test_lockout_after_five_failures_and_audit(ctx: Ctx) -> None:
    ctx.seed_account("u@met.bb")
    for _ in range(5):
        ctx.client.post(ctx.url("/auth/login"), json={"email": "u@met.bb", "password": "wrong password!"})
    r = ctx.client.post(ctx.url("/auth/login"), json={"email": "u@met.bb", "password": GOOD_PW})
    assert r.status_code == 403
    assert r.json()["code"] == "ACCOUNT_LOCKED"
    assert int(r.headers["Retry-After"]) > 800
    assert ctx.run(ctx.db["auditlog"].count_documents({"action": "auth.locked"})) == 1


def test_legacy_werkzeug_hash_upgraded(ctx: Ctx) -> None:
    import hashlib

    salt = "abc123"
    digest = hashlib.pbkdf2_hmac("sha256", GOOD_PW.encode(), salt.encode(), 1000).hex()
    acc = ctx.seed_account("old@met.bb")
    ctx.run(
        ctx.db["accounts"].update_one(
            {"id": acc["id"]},
            {"$unset": {"passwordHash": ""}, "$set": {"legacyPasswordHash": f"pbkdf2:sha256:1000${salt}${digest}"}},
        )
    )
    ctx.login("old@met.bb")
    upgraded = ctx.account("old@met.bb")
    assert upgraded["passwordHash"].startswith("$argon2id$")
    assert "legacyPasswordHash" not in upgraded


@pytest.mark.req("TR-AUTH-9")
def test_admin_mfa_flow(ctx: Ctx) -> None:
    ctx.seed_account("root@cimh.edu.bb", role="admin")
    tokens = ctx.login("root@cimh.edu.bb")
    h = {"Authorization": "Bearer " + tokens["accessToken"]}
    # admin without MFA: admin endpoints refused, setup allowed
    r = ctx.client.get(ctx.url("/admin/accounts"), headers=h)
    assert r.json()["code"] == "MFA_REQUIRED"
    uri = ctx.client.post(ctx.url("/auth/mfa/setup"), headers=h).json()["otpauthUri"]
    secret = uri.split("secret=")[1].split("&")[0]
    r = ctx.client.post(ctx.url("/auth/mfa/confirm"), headers=h, json={"totp": totp_now(secret)})
    assert r.status_code == 204
    # login now needs TOTP
    r = ctx.client.post(ctx.url("/auth/login"), json={"email": "root@cimh.edu.bb", "password": GOOD_PW})
    assert r.json()["code"] == "MFA_REQUIRED"
    r = ctx.client.post(
        ctx.url("/auth/login"),
        json={"email": "root@cimh.edu.bb", "password": GOOD_PW, "totp": "000000", "client": "mobile"},
    )
    assert r.status_code in (401, 200)  # 000000 could theoretically be valid
    future = totp_now(secret, time.time() + 30)  # next step: not used yet
    good = ctx.login("root@cimh.edu.bb", totp=future)
    r = ctx.client.get(ctx.url("/admin/accounts"), headers={"Authorization": "Bearer " + good["accessToken"]})
    assert r.status_code == 200
    # replaying the same TOTP step is refused
    r = ctx.client.post(
        ctx.url("/auth/login"),
        json={"email": "root@cimh.edu.bb", "password": GOOD_PW, "totp": future, "client": "mobile"},
    )
    assert r.status_code == 401


def test_mfa_setup_only_for_admins(ctx: Ctx) -> None:
    ctx.seed_account("s@cimh.edu.bb", role="staff")
    h = ctx.bearer("s@cimh.edu.bb")
    assert ctx.client.post(ctx.url("/auth/mfa/setup"), headers=h).status_code == 403


@pytest.mark.req("TR-AUTH-1")
def test_refresh_rotation_and_reuse_detection(ctx: Ctx) -> None:
    ctx.seed_account("u@met.bb")
    t1 = ctx.login("u@met.bb")
    r = ctx.client.post(ctx.url("/auth/refresh"), json={"refreshToken": t1["refreshToken"]})
    assert r.status_code == 200
    t2 = r.json()
    assert t2["refreshToken"] != t1["refreshToken"]
    # reuse of the old token revokes everything
    r = ctx.client.post(ctx.url("/auth/refresh"), json={"refreshToken": t1["refreshToken"]})
    assert r.status_code == 401
    assert r.json()["code"] == "TOKEN_REUSE"
    r = ctx.client.post(ctx.url("/auth/refresh"), json={"refreshToken": t2["refreshToken"]})
    assert r.status_code == 401
    r = ctx.client.get(ctx.url("/me"), headers={"Authorization": "Bearer " + t2["accessToken"]})
    assert r.status_code == 401  # session revoked -> access token dead too


def test_web_refresh_uses_cookie_and_csrf(ctx: Ctx) -> None:
    ctx.seed_account("u@met.bb")
    ctx.client.post(ctx.url("/auth/login"), json={"email": "u@met.bb", "password": GOOD_PW})
    assert ctx.client.post(ctx.url("/auth/refresh")).status_code == 403  # no CSRF header
    csrf = ctx.client.cookies.get("csrf_token")
    r = ctx.client.post(ctx.url("/auth/refresh"), headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert "refreshToken" not in r.json()


def test_logout_revokes_session(ctx: Ctx) -> None:
    ctx.seed_account("u@met.bb")
    t = ctx.login("u@met.bb")
    h = {"Authorization": "Bearer " + t["accessToken"]}
    assert ctx.client.post(ctx.url("/auth/logout"), headers=h).status_code == 204
    assert ctx.client.get(ctx.url("/me"), headers=h).status_code == 401
    assert ctx.client.post(ctx.url("/auth/refresh"), json={"refreshToken": t["refreshToken"]}).status_code == 401


@pytest.mark.req("A8")
def test_password_reset_flow_revokes_sessions(ctx: Ctx) -> None:
    ctx.seed_account("u@met.bb")
    t = ctx.login("u@met.bb")
    assert ctx.client.post(ctx.url("/auth/password/forgot"), json={"email": "u@met.bb"}).status_code == 202
    assert ctx.client.post(ctx.url("/auth/password/forgot"), json={"email": "no@x.org"}).status_code == 202
    assert ctx.account("u@met.bb")["outbox"][-1]["type"] == "user.password_reset_requested"
    code = ctx.code("u@met.bb", "reset_password")
    r = ctx.client.post(
        ctx.url("/auth/password/reset"), json={"email": "u@met.bb", "code": code, "newPassword": "a brand new password"}
    )
    assert r.status_code == 204
    assert ctx.client.get(ctx.url("/me"), headers={"Authorization": "Bearer " + t["accessToken"]}).status_code == 401
    ctx.login("u@met.bb", password="a brand new password")


def test_change_email_flow(ctx: Ctx) -> None:
    ctx.seed_account("u@met.bb")
    h = ctx.bearer("u@met.bb")
    r = ctx.client.post(ctx.url("/me/email"), headers=h, json={"newEmail": "new@met.bb", "password": GOOD_PW})
    assert r.status_code == 202
    r = ctx.client.post(
        ctx.url("/auth/verify"), json={"email": "new@met.bb", "code": ctx.code("new@met.bb", "change_email")}
    )
    assert r.json()["status"] == "ACTIVE"
    assert ctx.account("new@met.bb")["outbox"][-1]["type"] == "user.profile_updated"
    ctx.login("new@met.bb")


def test_jwks_and_token_claims(ctx: Ctx) -> None:
    import jwt

    jwks = ctx.client.get(ctx.url("/.well-known/jwks.json")).json()
    assert jwks["keys"][0]["crv"] == "Ed25519"
    assert "d" not in jwks["keys"][0]  # never the private part
    ctx.seed_account("u@met.bb", org="ORG1")
    tok = ctx.login("u@met.bb")["accessToken"]
    claims = jwt.decode(tok, options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 900
    assert claims["org"] == "ORG1"
    assert claims["role"] == "user"


def test_suspended_and_unverified_cannot_login(ctx: Ctx) -> None:
    ctx.seed_account("s@met.bb", status="SUSPENDED")
    r = ctx.client.post(ctx.url("/auth/login"), json={"email": "s@met.bb", "password": GOOD_PW})
    assert r.json()["code"] == "ACCOUNT_SUSPENDED"
    ctx.seed_account("p@met.bb", status="PENDING_VERIFICATION")
    r = ctx.client.post(ctx.url("/auth/login"), json={"email": "p@met.bb", "password": GOOD_PW})
    assert r.json()["code"] == "ACCOUNT_PENDING_VERIFICATION"


def test_admin_session_is_at_most_8h(ctx: Ctx) -> None:
    import json

    secret = new_totp_secret()
    ctx.seed_account("a@cimh.edu.bb", role="admin", mfa_secret=secret)
    t = ctx.login("a@cimh.edu.bb", totp=totp_now(secret))
    import jwt

    sid = jwt.decode(t["accessToken"], options={"verify_signature": False})["sid"]
    sess = json.loads(ctx.run(ctx.redis.get(f"sess:{sid}")))
    assert sess["exp"] - time.time() <= 8 * 3600 + 5
