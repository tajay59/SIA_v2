from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from cimh_common.app import create_app
from cimh_common.auth import JwksCache, Principal, TokenVerifier
from cimh_common.authz import (
    can_see,
    current_principal,
    ensure_can_act,
    ensure_visible,
    require_admin,
    require_requester,
    require_staff,
)
from cimh_common.errors import ProblemError

from .conftest import AUDIENCE, ISSUER, Keys


def make_client(verifier: TokenVerifier) -> TestClient:
    app = create_app("test-svc", token_verifier=verifier, configure_logs=False)

    @app.get("/me")
    async def me(p: Principal = Depends(current_principal)) -> dict[str, str]:
        return {"sub": p.sub, "role": p.role}

    @app.post("/me")
    async def me_post(p: Principal = Depends(current_principal)) -> dict[str, str]:
        return {"sub": p.sub}

    @app.get("/staff")
    async def staff(p: Principal = Depends(require_staff)) -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/admin")
    async def admin(p: Principal = Depends(require_admin)) -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/cart")
    async def cart(p: Principal = Depends(require_requester)) -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(app)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_anonymous_is_401_problem(verifier: TokenVerifier) -> None:
    r = make_client(verifier).get("/me")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 401
    assert body["traceId"] == r.headers["X-Trace-Id"]


def test_valid_bearer(verifier: TokenVerifier, keys: Keys) -> None:
    r = make_client(verifier).get("/me", headers=bearer(keys.token("USR9", "staff")))
    assert r.status_code == 200
    assert r.json() == {"sub": "USR9", "role": "staff"}


@pytest.mark.parametrize(
    ("path", "role", "status"),
    [
        ("/staff", "user", 403),
        ("/staff", "staff", 200),
        ("/staff", "admin", 200),
        ("/admin", "staff", 403),
        ("/admin", "admin", 200),
        ("/cart", "staff", 403),
    ],
)
def test_role_matrix(verifier: TokenVerifier, keys: Keys, path: str, role: str, status: int) -> None:
    client = make_client(verifier)
    method = client.post if path == "/cart" else client.get
    assert method(path, headers=bearer(keys.token(role=role))).status_code == status


def test_cimh_user_cannot_request(verifier: TokenVerifier, keys: Keys) -> None:
    token = keys.token("USR2", "user", email="someone@cimh.edu.bb")
    r = make_client(verifier).post("/cart", headers=bearer(token))
    assert r.status_code == 403
    assert r.json()["code"] == "CIMH_CANNOT_REQUEST"


def test_member_user_can_request(verifier: TokenVerifier, keys: Keys) -> None:
    r = make_client(verifier).post("/cart", headers=bearer(keys.token("USR3", "user")))
    assert r.status_code == 200


def test_expired_token(verifier: TokenVerifier, keys: Keys) -> None:
    old = int(time.time()) - 3600
    token = keys.token(iat=old, exp=old + 60)
    r = make_client(verifier).get("/me", headers=bearer(token))
    assert r.status_code == 401
    assert r.json()["code"] == "TOKEN_EXPIRED"


def test_wrong_signing_key_rejected(verifier: TokenVerifier) -> None:
    other = Keys()  # same kid, different key
    r = make_client(verifier).get("/me", headers=bearer(other.token()))
    assert r.status_code == 401


def test_wrong_audience_rejected(verifier: TokenVerifier, keys: Keys) -> None:
    r = make_client(verifier).get("/me", headers=bearer(keys.token(aud="other")))
    assert r.status_code == 401


def test_hs256_token_rejected(verifier: TokenVerifier) -> None:
    import jwt

    token = jwt.encode({"sub": "x", "role": "admin"}, "secret-secret-secret-secret-32by", algorithm="HS256")
    r = make_client(verifier).get("/me", headers=bearer(token))
    assert r.status_code == 401


def test_revoked_token(verifier: TokenVerifier, keys: Keys, revoked: set[str]) -> None:
    token = keys.token("USR4", jti="J-REVOKED")
    revoked.add("J-REVOKED")
    assert make_client(verifier).get("/me", headers=bearer(token)).status_code == 401


def test_revoked_session(verifier: TokenVerifier, keys: Keys, revoked: set[str]) -> None:
    token = keys.token("USR4", sid="S1")
    revoked.add("S1")
    assert make_client(verifier).get("/me", headers=bearer(token)).status_code == 401


def test_revocation_store_down_fails_closed(keys: Keys) -> None:
    async def fetch() -> dict[str, Any]:
        return keys.jwks()

    async def broken(jti: str, sid: str | None) -> bool:
        raise ConnectionError("redis down")

    v = TokenVerifier(JwksCache(fetch), issuer=ISSUER, audience=AUDIENCE, is_revoked=broken)
    r = make_client(v).get("/me", headers=bearer(keys.token()))
    assert r.status_code == 503


def test_cookie_auth_requires_csrf_on_writes(verifier: TokenVerifier, keys: Keys) -> None:
    client = make_client(verifier)
    client.cookies.set("access_token", keys.token())
    assert client.get("/me").status_code == 200  # reads need no CSRF
    assert client.post("/me").status_code == 403
    client.cookies.set("csrf_token", "abc")
    assert client.post("/me", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post("/me", headers={"X-CSRF-Token": "abc"}).status_code == 200


def test_bearer_writes_need_no_csrf(verifier: TokenVerifier, keys: Keys) -> None:
    assert make_client(verifier).post("/me", headers=bearer(keys.token())).status_code == 200


def test_jwks_refetch_on_rotation(keys: Keys) -> None:
    import asyncio

    calls = 0
    current = {"keys": []}  # type: dict[str, Any]

    async def fetch() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return current

    now = [1000.0]
    cache = JwksCache(fetch, clock=lambda: now[0])
    with pytest.raises(ProblemError):
        asyncio.run(cache.get(keys.kid))
    current = keys.jwks()
    now[0] += 31  # past the 30 s refetch guard
    assert asyncio.run(cache.get(keys.kid)) is not None
    assert calls == 2


# ---- ownership rules (pure functions) ----

USER = Principal(sub="USR1", role="user", org_id="ORG1")
SAME_ORG = Principal(sub="USR2", role="user", org_id="ORG1")
OTHER_ORG = Principal(sub="USR3", role="user", org_id="ORG2")
STAFF = Principal(sub="USR4", role="staff")
ADMIN = Principal(sub="USR5", role="admin")


def test_can_see_rules() -> None:
    kw = {"owner_id": "USR1", "org_id": "ORG1"}
    assert can_see(USER, **kw)
    assert not can_see(SAME_ORG, **kw)
    assert can_see(SAME_ORG, same_org=True, **kw)
    assert not can_see(OTHER_ORG, same_org=True, **kw)
    assert can_see(STAFF, **kw)
    assert can_see(ADMIN, **kw)


def test_no_org_never_matches() -> None:
    a = Principal(sub="A", role="user", org_id=None)
    assert not can_see(a, owner_id="B", org_id=None, same_org=True)


def test_hidden_is_404() -> None:
    with pytest.raises(ProblemError) as e:
        ensure_visible(OTHER_ORG, owner_id="USR1", org_id="ORG1", same_org=True)
    assert e.value.status == 404


def test_act_rules() -> None:
    ensure_can_act(USER, owner_id="USR1", org_id="ORG1")
    ensure_can_act(ADMIN, owner_id="USR1", org_id="ORG1")
    with pytest.raises(ProblemError) as same:
        ensure_can_act(SAME_ORG, owner_id="USR1", org_id="ORG1")
    assert same.value.status == 403
    with pytest.raises(ProblemError) as other:
        ensure_can_act(OTHER_ORG, owner_id="USR1", org_id="ORG1")
    assert other.value.status == 404
    with pytest.raises(ProblemError) as staff:
        ensure_can_act(STAFF, owner_id="USR1", org_id="ORG1")
    assert staff.value.status == 403


def test_admin_without_mfa_is_refused_except_setup(verifier: TokenVerifier, keys: Keys) -> None:
    from cimh_common.authz import authenticated_principal

    app = create_app("t", token_verifier=verifier, configure_logs=False)

    @app.get("/x")
    async def x(p: Principal = Depends(current_principal)) -> dict[str, str]:
        return {"ok": "1"}

    @app.get("/setup")
    async def setup(p: Principal = Depends(authenticated_principal)) -> dict[str, str]:
        return {"ok": "1"}

    c = TestClient(app)
    no_mfa = bearer(keys.token("USR9", "admin", mfa=False))
    r = c.get("/x", headers=no_mfa)
    assert r.status_code == 403
    assert r.json()["code"] == "MFA_REQUIRED"
    assert c.get("/setup", headers=no_mfa).status_code == 200
    assert c.get("/x", headers=bearer(keys.token("USR9", "admin"))).status_code == 200
    assert c.get("/x", headers=bearer(keys.token("USR8", "staff", mfa=False))).status_code == 200


def test_public_endpoints_apply_the_same_token_rules(verifier: TokenVerifier, keys: Keys) -> None:
    """Pen test 2026-11: an admin without MFA must not get the staff view of a public endpoint, and service
    tokens are refused there too. Anonymous callers and normal tokens still work."""
    from cimh_common.authz import optional_principal

    app = create_app("t", token_verifier=verifier, configure_logs=False)

    @app.get("/catalogue")
    async def catalogue(p: Principal | None = Depends(optional_principal)) -> dict[str, str]:
        return {"view": "staff" if p and p.is_staff else "public"}

    c = TestClient(app)
    assert c.get("/catalogue").json() == {"view": "public"}
    assert c.get("/catalogue", headers=bearer(keys.token("USR1", "user"))).json() == {"view": "public"}
    assert c.get("/catalogue", headers=bearer(keys.token("USR2", "staff"))).json() == {"view": "staff"}
    assert c.get("/catalogue", headers=bearer(keys.token("USR3", "admin"))).json() == {"view": "staff"}
    r = c.get("/catalogue", headers=bearer(keys.token("USR4", "admin", mfa=False)))
    assert r.status_code == 403
    assert r.json()["code"] == "MFA_REQUIRED"
    assert c.get("/catalogue", headers=bearer(keys.token("svc:order", "service"))).status_code == 403
