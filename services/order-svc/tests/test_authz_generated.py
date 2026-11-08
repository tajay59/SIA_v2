"""Generated authz tests from tests/authz/matrix.yaml (TEST_STRATEGY §5), negative cases.

Auth runs before body validation, so 401/403 can be checked with dummy path ids and no body. Allowed-role
cases are covered by the functional tests with real data.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from order_svc.main import BASE

from .conftest import ADMIN, CIMH_USER, STAFF, USER, Ctx, token

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "authz"))
from authz_cases import Case, cases_for, endpoints_for

CASES = [c for ep, row in endpoints_for(BASE).items() for c in cases_for(ep, row) if c.expect in (401, 403)]
HEADERS = {
    "anonymous": {},
    "user": USER,
    "staff": STAFF,
    "admin": ADMIN,
    "service": token("service", "svc:document", ""),
    "cimh_user": CIMH_USER,
}


def test_generated_cases_exist() -> None:
    assert len(CASES) > 50


@pytest.mark.req("TR-AUTH-5")
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_negative_authz(ctx: Ctx, case: Case) -> None:
    method, path = case.endpoint.split(" ", 1)
    path = re.sub(r"\{[^}]+\}", "X", path)
    r = ctx.client.request(method, path, headers={**HEADERS[case.actor], "If-Match": "1"})
    assert r.status_code == case.expect, f"{case.id}: got {r.status_code} {r.text[:200]}"


def test_admin_without_mfa_is_refused(ctx: Ctx) -> None:
    r = ctx.client.get(ctx.url("/requests"), headers=token("admin", "USRA", "a@cimh.edu.bb", mfa=False))
    assert r.status_code == 403
    assert r.json()["code"] == "MFA_REQUIRED"


@pytest.mark.parametrize("case", [c for c in CASES if c.actor == "cimh_user"], ids=lambda c: c.id)
def test_cimh_code(ctx: Ctx, case: Case) -> None:
    method, path = case.endpoint.split(" ", 1)
    r = ctx.client.request(method, re.sub(r"\{[^}]+\}", "X", path), headers=CIMH_USER)
    assert r.json()["code"] == "CIMH_CANNOT_REQUEST"
