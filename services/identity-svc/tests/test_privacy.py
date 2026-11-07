"""Personal-data rights (TR-PRIV-1, BSD §8, SECURITY §10): export, erasure request, admin erasure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from identity_svc.privacy import DELETED

from .conftest import GOOD_PW, Ctx

SCHEMAS = Path(__file__).resolve().parents[3] / "packages" / "event-schemas" / "schemas"


def event_schema(etype: str) -> Draft202012Validator:
    index = json.loads((SCHEMAS / "index.json").read_text(encoding="utf-8"))
    return Draft202012Validator(json.loads((SCHEMAS / index[etype]).read_text(encoding="utf-8")))


def as_json(evt: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(json.dumps(evt, default=str)))


def audit(ctx: Ctx, **q: Any) -> list[dict[str, Any]]:
    async def get() -> list[dict[str, Any]]:
        return [d async for d in ctx.db["auditlog"].find(q)]

    return list(ctx.run(get()))


@pytest.mark.req("TR-PRIV-1")
def test_user_downloads_own_data_without_staff_names(ctx: Ctx) -> None:
    admin, ah = ctx.admin()
    user = ctx.seed_account("u@met.bb")
    ctx.client.post(
        ctx.url(f"/admin/accounts/{user['id']}/suspend"), headers={**ah, "If-Match": "1"}, json={"reason": "check"}
    )
    ctx.client.post(ctx.url(f"/admin/accounts/{user['id']}/reactivate"), headers={**ah, "If-Match": "2"})
    h = ctx.bearer("u@met.bb")

    r = ctx.client.get(ctx.url("/me/export"), headers=h)
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith('attachment; filename="cimh-my-data-')
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["subjectId"] == user["id"]
    ident = body["sections"]["identity"]
    assert ident["account"]["email"] == "u@met.bb"
    assert "passwordHash" not in json.dumps(body)
    # Staff who acted are shown by role, never by name or id.
    assert admin["email"] not in json.dumps(body)
    assert admin["id"] not in json.dumps(body)
    assert {e["by"] for e in ident["auditTrail"]} >= {"CIMH admin"}
    assert [h["by"]["name"] for h in ident["account"]["statusHistory"]] == ["CIMH admin", "CIMH admin"]
    assert audit(ctx, action="privacy.exported")[0]["entity"]["id"] == user["id"]


@pytest.mark.req("TR-PRIV-1")
def test_admin_export_keeps_names(ctx: Ctx) -> None:
    admin, ah = ctx.admin()
    user = ctx.seed_account("u@met.bb")
    ctx.client.post(
        ctx.url(f"/admin/accounts/{user['id']}/suspend"), headers={**ah, "If-Match": "1"}, json={"reason": "check"}
    )
    r = ctx.client.get(ctx.url(f"/admin/accounts/{user['id']}/export"), headers=ah)
    assert r.status_code == 200
    assert user["id"] in r.headers["content-disposition"]
    trail = r.json()["sections"]["identity"]["auditTrail"]
    assert any(admin["email"] in e["by"] for e in trail)
    assert ctx.client.get(ctx.url("/admin/accounts/USR404/export"), headers=ah).status_code == 404


def test_erasure_request_needs_password_and_is_recorded_once(ctx: Ctx) -> None:
    ctx.seed_account("u@met.bb")
    h = ctx.bearer("u@met.bb")
    r = ctx.client.post(ctx.url("/me/erasure-request"), headers=h, json={"password": "wrong password!"})
    assert r.status_code == 401
    for _ in range(2):
        r = ctx.client.post(ctx.url("/me/erasure-request"), headers=h, json={"password": GOOD_PW})
        assert r.status_code == 202
    acc = ctx.account("u@met.bb")
    assert acc["erasureRequestedAt"]
    events = [e for e in acc["outbox"] if e["type"] == "user.erasure_requested"]
    assert len(events) == 1
    event_schema("user.erasure_requested").validate(as_json(events[0]))
    assert len(audit(ctx, action="privacy.erasure_requested")) == 1


def test_admin_lists_erasure_requests(ctx: Ctx) -> None:
    _, ah = ctx.admin()
    ctx.seed_account("u@met.bb")
    ctx.seed_account("v@met.bb")
    ctx.client.post(ctx.url("/me/erasure-request"), headers=ctx.bearer("u@met.bb"), json={"password": GOOD_PW})
    r = ctx.client.get(ctx.url("/admin/accounts?erasureRequested=true"), headers=ah)
    items = r.json()["items"]
    assert [i["email"] for i in items] == ["u@met.bb"]
    assert items[0]["erasureRequestedAt"]


@pytest.mark.req("TR-PRIV-1")
def test_admin_erases_account(ctx: Ctx) -> None:
    _, ah = ctx.admin()
    user = ctx.seed_account("u@met.bb")
    uh = ctx.bearer("u@met.bb")
    ctx.client.patch(ctx.url("/me"), headers={**uh, "If-Match": "1"}, json={"phone": "+1 246 555 0100"})
    assert ctx.client.get(ctx.url("/me/export"), headers=uh).status_code == 200  # an audit entry by the person
    version = ctx.account("u@met.bb")["version"]

    r = ctx.client.post(
        ctx.url(f"/admin/accounts/{user['id']}/erase"), headers={**ah, "If-Match": "1"}, json={"reason": "asked"}
    )
    assert r.status_code == 409  # stale version
    r = ctx.client.post(
        ctx.url(f"/admin/accounts/{user['id']}/erase"),
        headers={**ah, "If-Match": str(version)},
        json={"reason": "Asked by email on 2026-11-07"},
    )
    assert r.status_code == 204, r.text

    gone = ctx.run(ctx.db["accounts"].find_one({"id": user["id"]}))
    assert gone["firstname"] == DELETED
    assert gone["phone"] is None
    assert gone["email"].endswith("@deleted.invalid")
    assert "passwordHash" not in gone
    assert gone["outbox"][-1]["type"] == "user.deleted"
    event_schema("user.deleted").validate(as_json(gone["outbox"][-1]))
    # Sessions die, the address is free again, the person disappears from lists and lookups.
    assert ctx.client.get(ctx.url("/me"), headers=uh).status_code == 401
    assert ctx.client.get(ctx.url(f"/admin/accounts/{user['id']}"), headers=ah).status_code == 404
    assert "u@met.bb" not in ctx.client.get(ctx.url("/admin/accounts"), headers=ah).text
    # The person's own audit entries keep their action but lose the name.
    mine = audit(ctx, **{"actor.id": user["id"]})
    assert mine
    assert all(e["actor"]["name"] == DELETED and "ip" not in e for e in mine)
    erased = audit(ctx, action="account.erased")[0]
    assert erased["reason"] == "Asked by email on 2026-11-07"
    r = ctx.client.post(
        ctx.url(f"/admin/accounts/{user['id']}/erase"), headers={**ah, "If-Match": "9"}, json={"reason": "again"}
    )
    assert r.status_code == 404


def test_admin_cannot_erase_self_or_last_admin(ctx: Ctx) -> None:
    admin, ah = ctx.admin()
    r = ctx.client.post(
        ctx.url(f"/admin/accounts/{admin['id']}/erase"), headers={**ah, "If-Match": "1"}, json={"reason": "self"}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "ACCOUNT_ILLEGAL_TRANSITION"


def test_staff_cannot_export_or_erase(ctx: Ctx) -> None:
    user = ctx.seed_account("u@met.bb")
    ctx.seed_account("s@cimh.edu.bb", role="staff")
    sh = ctx.bearer("s@cimh.edu.bb")
    assert ctx.client.get(ctx.url(f"/admin/accounts/{user['id']}/export"), headers=sh).status_code == 403
    r = ctx.client.post(
        ctx.url(f"/admin/accounts/{user['id']}/erase"), headers={**sh, "If-Match": "1"}, json={"reason": "nope"}
    )
    assert r.status_code == 403
