"""Admin approvals, roles, suspension, organisations, audit, internal endpoints (A3-A5, A7, A10-A13)."""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import GOOD_PW, Ctx


def create_org(ctx: Ctx, h: dict[str, str], name: str = "Grenada Met Office", **kw: Any) -> dict[str, Any]:
    r = ctx.client.post(
        ctx.url("/organisations"), headers=h, json={"name": name, "country": "GD", "emailDomains": ["@MET.gd"], **kw}
    )
    assert r.status_code == 201, r.text
    assert r.headers["ETag"] == '"1"'
    return dict(r.json())


def pending(ctx: Ctx, email: str = "ana@met.gd") -> dict[str, Any]:
    return ctx.seed_account(email, status="PENDING_APPROVAL")


@pytest.mark.req("A3")
def test_approve_links_org_and_activates(ctx: Ctx) -> None:
    _, h = ctx.admin()
    org = create_org(ctx, h)
    assert org["emailDomains"] == ["met.gd"]
    acc = pending(ctx)
    q = ctx.client.get(ctx.url("/admin/accounts"), headers=h, params={"status": "PENDING_APPROVAL"}).json()
    assert [a["id"] for a in q["items"]] == [acc["id"]]
    assert q["nextCursor"] is None

    url = ctx.url(f"/admin/accounts/{acc['id']}/approve")
    assert ctx.client.post(url, headers=h, json={"organisationId": org["id"]}).status_code == 428  # no If-Match
    r = ctx.client.post(url, headers={**h, "If-Match": '"1"'}, json={"organisationId": org["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ACTIVE"
    assert body["organisationName"] == "Grenada Met Office"
    assert r.headers["ETag"] == '"2"'
    assert body["statusHistory"][-1]["to"] == "ACTIVE"
    stored = ctx.account("ana@met.gd")
    assert stored["outbox"][-1]["type"] == "user.approved"
    assert stored["outbox"][-1]["payload"]["organisationId"] == org["id"]
    # second approval: illegal transition; stale version: conflict
    r = ctx.client.post(url, headers={**h, "If-Match": '"2"'}, json={"organisationId": org["id"]})
    assert r.json()["code"] == "ACCOUNT_ILLEGAL_TRANSITION"
    r = ctx.client.post(url, headers={**h, "If-Match": '"1"'}, json={"organisationId": org["id"]})
    assert r.json()["code"] == "VERSION_CONFLICT"
    assert ctx.run(ctx.db["auditlog"].count_documents({"action": "account.approved"})) == 1


def test_approve_needs_active_org(ctx: Ctx) -> None:
    _, h = ctx.admin()
    acc = pending(ctx)
    r = ctx.client.post(
        ctx.url(f"/admin/accounts/{acc['id']}/approve"),
        headers={**h, "If-Match": "1"},
        json={"organisationId": "ORGnope"},
    )
    assert r.status_code == 422


@pytest.mark.req("A4")
def test_deny_requires_reason(ctx: Ctx) -> None:
    _, h = ctx.admin()
    acc = pending(ctx)
    url = ctx.url(f"/admin/accounts/{acc['id']}/deny")
    assert ctx.client.post(url, headers={**h, "If-Match": "1"}, json={"reason": ""}).status_code == 422
    r = ctx.client.post(url, headers={**h, "If-Match": "1"}, json={"reason": "Not a member state"})
    assert r.json()["status"] == "REJECTED"
    assert ctx.account("ana@met.gd")["outbox"][-1]["payload"]["reason"] == "Not a member state"


@pytest.mark.req("A3a")
def test_bulk_decision_reports_each_item(ctx: Ctx) -> None:
    _, h = ctx.admin()
    org = create_org(ctx, h)
    a, b, c = pending(ctx, "a@x.org"), pending(ctx, "b@x.org"), pending(ctx, "c@x.org")
    r = ctx.client.post(
        ctx.url("/admin/accounts/bulk-decision"),
        headers=h,
        json={
            "decisions": [
                {"accountId": a["id"], "version": 1, "decision": "approve", "organisationId": org["id"]},
                {"accountId": b["id"], "version": 1, "decision": "deny", "reason": "duplicate"},
                {"accountId": c["id"], "version": 9, "decision": "deny", "reason": "stale"},
                {"accountId": "USRmissing", "version": 1, "decision": "approve", "organisationId": org["id"]},
            ]
        },
    )
    assert r.status_code == 207
    res = r.json()["results"]
    assert [x["ok"] for x in res] == [True, True, False, False]
    assert res[2]["error"]["code"] == "VERSION_CONFLICT"
    assert res[3]["error"]["status"] == 404


@pytest.mark.req("A5")
def test_suspend_revokes_sessions_and_reactivate(ctx: Ctx) -> None:
    _, h = ctx.admin()
    user = ctx.seed_account("u@met.bb")
    uh = ctx.bearer("u@met.bb")
    r = ctx.client.post(
        ctx.url(f"/admin/accounts/{user['id']}/suspend"),
        headers={**h, "If-Match": "1"},
        json={"reason": "abuse report"},
    )
    assert r.json()["status"] == "SUSPENDED"
    assert ctx.client.get(ctx.url("/me"), headers=uh).status_code == 401
    r = ctx.client.post(ctx.url("/auth/login"), json={"email": "u@met.bb", "password": GOOD_PW})
    assert r.json()["code"] == "ACCOUNT_SUSPENDED"
    r = ctx.client.post(ctx.url(f"/admin/accounts/{user['id']}/reactivate"), headers={**h, "If-Match": "2"})
    assert r.json()["status"] == "ACTIVE"
    ctx.login("u@met.bb")


@pytest.mark.req("A7")
def test_role_change_and_last_admin(ctx: Ctx) -> None:
    admin, h = ctx.admin()
    staff = ctx.seed_account("s@cimh.edu.bb", role="staff")
    sh = ctx.bearer("s@cimh.edu.bb")
    r = ctx.client.put(
        ctx.url(f"/admin/accounts/{staff['id']}/role"), headers={**h, "If-Match": "1"}, json={"role": "user"}
    )
    assert r.json()["role"] == "user"
    assert ctx.account("s@cimh.edu.bb")["outbox"][-1]["payload"]["previousRole"] == "staff"
    assert ctx.client.get(ctx.url("/me"), headers=sh).status_code == 401  # old role token revoked
    r = ctx.client.put(
        ctx.url(f"/admin/accounts/{admin['id']}/role"), headers={**h, "If-Match": "1"}, json={"role": "staff"}
    )
    assert r.json()["code"] == "LAST_ADMIN"
    r = ctx.client.post(
        ctx.url(f"/admin/accounts/{admin['id']}/suspend"), headers={**h, "If-Match": "1"}, json={"reason": "self"}
    )
    assert r.status_code == 409


def test_staff_reads_but_cannot_decide(ctx: Ctx) -> None:
    ctx.seed_account("s@cimh.edu.bb", role="staff")
    h = ctx.bearer("s@cimh.edu.bb")
    acc = pending(ctx)
    assert ctx.client.get(ctx.url(f"/admin/accounts/{acc['id']}"), headers=h).status_code == 200
    r = ctx.client.post(
        ctx.url(f"/admin/accounts/{acc['id']}/approve"), headers={**h, "If-Match": "1"}, json={"organisationId": "x"}
    )
    assert r.status_code == 403
    ctx.seed_account("u@met.bb")
    assert ctx.client.get(ctx.url("/admin/accounts"), headers=ctx.bearer("u@met.bb")).status_code == 403


def test_account_paging_and_search(ctx: Ctx) -> None:
    _, h = ctx.admin()
    for i in range(5):
        ctx.seed_account(f"p{i}@x.org", status="PENDING_APPROVAL")
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"status": "PENDING_APPROVAL", "limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = ctx.client.get(ctx.url("/admin/accounts"), headers=h, params=params).json()
        seen += [a["email"] for a in page["items"]]
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert sorted(seen) == [f"p{i}@x.org" for i in range(5)]
    assert len(set(seen)) == 5
    r = ctx.client.get(ctx.url("/admin/accounts"), headers=h, params={"q": "p3"}).json()
    assert [a["email"] for a in r["items"]] == ["p3@x.org"]
    assert ctx.client.get(ctx.url("/admin/accounts"), headers=h, params={"limit": 101}).status_code == 422
    assert ctx.client.get(ctx.url("/admin/accounts"), headers=h, params={"cursor": "garbage"}).status_code == 422


@pytest.mark.req("A11")
def test_organisations_crud_merge(ctx: Ctx) -> None:
    _, h = ctx.admin()
    a = create_org(ctx, h, "Barbados Met Service")
    b = create_org(ctx, h, "BMS (duplicate)", aliases=["BMS"])
    assert (
        ctx.client.post(
            ctx.url("/organisations"), headers=h, json={"name": "barbados met service", "country": "BB"}
        ).status_code
        == 409
    )
    u = ctx.seed_account("u@met.bb", org=b["id"])
    r = ctx.client.patch(
        ctx.url(f"/organisations/{a['id']}"),
        headers={**h, "If-Match": "1"},
        json={"name": "Barbados Meteorological Services", "country": "BB"},
    )
    assert r.json()["name"] == "Barbados Meteorological Services"
    r = ctx.client.patch(
        ctx.url(f"/organisations/{a['id']}"), headers={**h, "If-Match": "1"}, json={"name": "x", "country": "BB"}
    )
    assert r.json()["code"] == "VERSION_CONFLICT"
    r = ctx.client.post(ctx.url(f"/organisations/{b['id']}/merge"), headers=h, json={"targetId": a["id"]})
    assert r.status_code == 200
    assert "BMS (duplicate)" in r.json()["aliases"]
    assert r.json()["memberCount"] == 1
    assert ctx.account("u@met.bb")["organisationId"] == a["id"]
    src = ctx.client.get(ctx.url(f"/organisations/{b['id']}"), headers=h).json()
    assert src["mergedInto"] == a["id"]
    assert src["active"] is False
    assert (
        ctx.client.post(ctx.url(f"/organisations/{a['id']}/merge"), headers=h, json={"targetId": a["id"]}).status_code
        == 409
    )
    found = ctx.client.get(ctx.url("/organisations"), headers=h, params={"q": "bms"}).json()["items"]
    assert {o["id"] for o in found} >= {a["id"]}
    by_domain = ctx.client.get(ctx.url("/organisations"), headers=h, params={"emailDomain": "met.gd"}).json()
    assert len(by_domain["items"]) == 2
    _ = u


def test_user_sees_only_own_org(ctx: Ctx) -> None:
    _, h = ctx.admin()
    mine = create_org(ctx, h, "Mine")
    other = create_org(ctx, h, "Other")
    ctx.seed_account("u@met.bb", org=mine["id"])
    uh = ctx.bearer("u@met.bb")
    r = ctx.client.get(ctx.url(f"/organisations/{mine['id']}"), headers=uh)
    assert r.status_code == 200
    assert "memberCount" not in r.json()
    assert ctx.client.get(ctx.url(f"/organisations/{other['id']}"), headers=uh).status_code == 404
    assert ctx.client.get(ctx.url("/organisations"), headers=uh).status_code == 403


@pytest.mark.req("A13")
def test_audit_log_newest_first_and_filters(ctx: Ctx) -> None:
    admin, h = ctx.admin()
    org = create_org(ctx, h)
    acc = pending(ctx)
    ctx.client.post(
        ctx.url(f"/admin/accounts/{acc['id']}/approve"),
        headers={**h, "If-Match": "1"},
        json={"organisationId": org["id"]},
    )
    items = ctx.client.get(ctx.url("/audit"), headers=h).json()["items"]
    actions = [i["action"] for i in items]
    assert actions.index("account.approved") < actions.index("organisation.created")
    only = ctx.client.get(ctx.url("/audit"), headers=h, params={"entityId": acc["id"]}).json()["items"]
    assert [i["action"] for i in only] == ["account.approved"]
    assert "ip" not in only[0]
    ctx.seed_account("s@cimh.edu.bb", role="staff")
    assert ctx.client.get(ctx.url("/audit"), headers=ctx.bearer("s@cimh.edu.bb")).status_code == 403
    _ = admin


@pytest.mark.req("A12")
def test_profile_update_with_if_match(ctx: Ctx) -> None:
    ctx.seed_account("u@met.bb")
    h = ctx.bearer("u@met.bb")
    me = ctx.client.get(ctx.url("/me"), headers=h)
    assert me.headers["ETag"] == '"1"'
    assert "statusHistory" not in me.json()
    addr = {
        "line1": "1 Bay St",
        "city": "Bridgetown",
        "country": "BB",
        "firstname": "U",
        "lastname": "M",
        "email": "u@met.bb",
    }
    r = ctx.client.patch(
        ctx.url("/me"), headers={**h, "If-Match": '"1"'}, json={"phone": "+1 246 555 0100", "addresses": [addr]}
    )
    assert r.status_code == 200
    assert r.json()["addresses"][0]["city"] == "Bridgetown"
    assert (
        ctx.client.patch(ctx.url("/me"), headers={**h, "If-Match": '"1"'}, json={"phone": "x"}).json()["code"]
        == "VERSION_CONFLICT"
    )
    assert ctx.client.patch(ctx.url("/me"), headers={**h, "If-Match": '"2"'}, json={"role": "admin"}).status_code == 422
    assert (
        ctx.client.patch(ctx.url("/me"), headers={**h, "If-Match": '"2"'}, json={"addresses": [addr] * 11}).status_code
        == 422
    )


def test_internal_service_token_and_code_claim(ctx: Ctx) -> None:
    r = ctx.client.post(ctx.url("/internal/service-token"), json={"service": "notification", "secret": "wrong"})
    assert r.status_code == 401
    tok = ctx.client.post(
        ctx.url("/internal/service-token"), json={"service": "notification", "secret": "n-secret"}
    ).json()
    assert tok["expiresIn"] == 300
    sh = {"Authorization": "Bearer " + tok["token"]}
    ctx.client.post(
        ctx.url("/auth/register"),
        json={
            "firstname": "A",
            "lastname": "B",
            "email": "z@x.org",
            "password": GOOD_PW,
            "organisationText": "Org",
            "country": "BB",
        },
    )
    acc = ctx.account("z@x.org")
    ref = acc["outbox"][0]["payload"]["codeRef"]
    r = ctx.client.get(ctx.url(f"/internal/codes/{ref}"), headers=sh)
    assert r.status_code == 200
    code = r.json()["code"]
    assert len(code) == 6
    assert ctx.client.get(ctx.url(f"/internal/codes/{ref}"), headers=sh).status_code == 404  # one-time
    assert ctx.client.post(ctx.url("/auth/verify"), json={"email": "z@x.org", "code": code}).status_code == 200
    # other services can't read codes; users can't call internal endpoints
    oh = {
        "Authorization": "Bearer "
        + ctx.client.post(ctx.url("/internal/service-token"), json={"service": "order", "secret": "o-secret"}).json()[
            "token"
        ]
    }
    assert ctx.client.get(ctx.url(f"/internal/codes/{ref}"), headers=oh).status_code == 403
    assert ctx.client.get(ctx.url(f"/internal/accounts/{acc['id']}"), headers=oh).json()["email"] == "z@x.org"
    ctx.seed_account("u@met.bb")
    assert ctx.client.get(ctx.url(f"/internal/accounts/{acc['id']}"), headers=ctx.bearer("u@met.bb")).status_code == 403
