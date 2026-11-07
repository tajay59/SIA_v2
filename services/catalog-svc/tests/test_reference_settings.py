"""Reference data and settings (PRD C8, BSD §5.7); admin changes are audited through audit.events."""

from __future__ import annotations

from pathlib import Path

import pytest

from catalog_svc.config import Settings
from catalog_svc.main import build_app
from cimh_common.testing import AsyncMongoMock

from .conftest import ADMIN, STAFF, USER, Ctx, check_event, verifier


def test_reference_defaults_and_departments(ctx: Ctx) -> None:
    ref = ctx.client.get(ctx.url("/reference")).json()
    assert ref["departments"] == []
    assert [t["key"] for t in ref["types"]] == ["MET", "RAD", "EQUIP", "SUPP", "MISC", "PRO"]
    assert ref["projects"] == []
    r = ctx.client.put(
        ctx.url("/reference/departments"), headers=ADMIN, json={"values": [" Hydrology", "Hydrology", "IT"]}
    )
    assert r.status_code == 204
    assert ctx.client.get(ctx.url("/reference")).json()["departments"] == ["Hydrology", "IT"]
    assert ctx.client.put(ctx.url("/reference/departments"), headers=ADMIN, json={"values": [" "]}).status_code == 422
    assert ctx.client.put(ctx.url("/reference/departments"), headers=STAFF, json={"values": []}).status_code == 403
    audit = ctx.misc("departments")["outbox"][0]
    check_event(audit)
    assert audit["payload"]["action"] == "settings.departments_changed"


def test_type_labels_come_from_misc(ctx: Ctx) -> None:
    ctx.run(
        ctx.db["misc"].insert_one(
            {"id": "types", "kind": "types", "values": [{"key": "MET", "label": "Meteorological"}]}
        )
    )
    types = ctx.client.get(ctx.url("/reference")).json()["types"]
    assert types[0] == {"key": "MET", "label": "Meteorological"}
    assert types[1] == {"key": "RAD", "label": "RAD"}


def test_projects(ctx: Ctx) -> None:
    r = ctx.client.post(
        ctx.url("/reference/projects"), headers=ADMIN, json={"code": "CREWS", "name": "CREWS Caribbean"}
    )
    assert r.status_code == 201
    assert r.json() == {"code": "crews", "name": "CREWS Caribbean", "active": True}
    assert (
        ctx.client.post(ctx.url("/reference/projects"), headers=ADMIN, json={"code": "crews", "name": "x"}).status_code
        == 409
    )
    assert (
        ctx.client.post(ctx.url("/reference/projects"), headers=ADMIN, json={"code": "a b", "name": "x"}).status_code
        == 422
    )
    ctx.client.post(ctx.url("/reference/projects"), headers=ADMIN, json={"code": "old", "name": "Old", "active": False})
    assert [p["code"] for p in ctx.client.get(ctx.url("/reference")).json()["projects"]] == ["crews"]
    r = ctx.client.patch(ctx.url("/reference/projects/CREWS"), headers=ADMIN, json={"active": False})
    assert r.json()["active"] is False
    assert ctx.client.patch(ctx.url("/reference/projects/nope"), headers=ADMIN, json={"name": "x"}).status_code == 404


@pytest.mark.req("C8")
def test_fees(ctx: Ctx) -> None:
    assert ctx.client.get(ctx.url("/settings/fees"), headers=STAFF).json() == {"types": []}
    body = {"types": [{"name": "admin", "fee": "25.00"}, {"name": "handling", "fee": "10.50"}]}
    assert ctx.client.put(ctx.url("/settings/fees"), headers=ADMIN, json=body).json() == body
    assert ctx.client.get(ctx.url("/settings/fees"), headers=STAFF).json() == body
    dup = {"types": [{"name": "admin", "fee": "1.00"}, {"name": "admin", "fee": "2.00"}]}
    assert ctx.client.put(ctx.url("/settings/fees"), headers=ADMIN, json=dup).status_code == 422
    bad = {"types": [{"name": "admin", "fee": "1.5"}]}
    assert ctx.client.put(ctx.url("/settings/fees"), headers=ADMIN, json=bad).status_code == 422
    assert ctx.client.put(ctx.url("/settings/fees"), headers=STAFF, json=body).status_code == 403
    assert ctx.client.get(ctx.url("/settings/fees"), headers=USER).status_code == 403


def test_general_settings(ctx: Ctx) -> None:
    defaults = ctx.client.get(ctx.url("/settings/general"), headers=STAFF).json()
    assert defaults["quoteValidityDays"] == 30
    assert defaults["cartInactivityDays"] == 180
    body = {**defaults, "quoteValidityDays": 45}
    assert ctx.client.put(ctx.url("/settings/general"), headers=ADMIN, json=body).json()["quoteValidityDays"] == 45
    assert (
        ctx.client.put(ctx.url("/settings/general"), headers=ADMIN, json={**body, "quoteValidityDays": 0}).status_code
        == 422
    )


@pytest.mark.req("C8")
def test_email_lists_accept_only_active_staff(ctx: Ctx) -> None:
    empty = ctx.client.get(ctx.url("/settings/email-lists"), headers=ADMIN).json()
    assert empty == {"registration": [], "order": [], "invoice": [], "cancellation": [], "lowStock": []}
    body = {
        **empty,
        "order": [{"accountId": "USRSTAFF"}, {"accountId": "USRSTAFF"}],
        "lowStock": [{"accountId": "USRADMIN"}],
    }
    r = ctx.client.put(ctx.url("/settings/email-lists"), headers=ADMIN, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["order"] == [
        {"accountId": "USRSTAFF", "email": "s@cimh.edu.bb", "firstname": "Sam", "lastname": "Staff"}
    ]
    for bad in ("USRUSER", "USROFF", "USR404"):
        r = ctx.client.put(
            ctx.url("/settings/email-lists"), headers=ADMIN, json={**empty, "invoice": [{"accountId": bad}]}
        )
        assert r.status_code == 422, bad
        assert r.json()["errors"][0]["field"] == "invoice[0]"
    assert ctx.client.get(ctx.url("/settings/email-lists"), headers=STAFF).status_code == 403


def test_email_lists_need_identity(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    app = build_app(
        Settings(media_root=str(tmp_path)), db=AsyncMongoMock(), token_verifier=verifier(), configure_logs=False,
        create_view=False,
    )  # fmt: skip
    with TestClient(app) as client:
        empty = {"registration": [], "order": [], "invoice": [], "cancellation": [], "lowStock": []}
        r = client.put("/api/catalog/v1/settings/email-lists", headers=ADMIN, json=empty)
        assert r.status_code == 503


def test_email_lists_report_identity_outage_as_503(ctx: Ctx) -> None:
    async def down(_: str) -> None:
        raise ConnectionError("identity unreachable")

    ctx.app.state.catalog.lookup_account = down
    empty = {
        "registration": [],
        "order": [{"accountId": "USRSTAFF"}],
        "invoice": [],
        "cancellation": [],
        "lowStock": [],
    }
    r = ctx.client.put(ctx.url("/settings/email-lists"), headers=ADMIN, json=empty)
    assert r.status_code == 503
    assert r.json()["code"] == "DEPENDENCY_UNAVAILABLE"
