from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "authz"))
from authz_cases import all_cases, cases_for, load
from build_matrix import infer
from check_matrix import validate


def test_public_endpoint_cases() -> None:
    cases = cases_for("GET /x", {"roles": ["anonymous", "user", "staff", "admin"], "ownership": "public"})
    assert [(c.actor, c.expect) for c in cases] == [("anonymous", "2xx")]


def test_staff_endpoint_cases() -> None:
    got = {(c.actor, c.expect) for c in cases_for("GET /x", {"roles": ["staff", "admin"], "ownership": "staff"})}
    assert got == {("anonymous", 401), ("user", 403), ("service", 403), ("staff", "2xx"), ("admin", "2xx")}


def test_scoped_endpoint_has_hidden_case_and_cimh() -> None:
    row = {"roles": ["user"], "ownership": "self", "cimh_forbidden": True}
    cases = cases_for("POST /cart", row)
    assert any(c.actor == "user" and c.target == "other" and c.expect == 404 for c in cases)
    cimh = [c for c in cases if c.actor == "cimh_user"]
    assert cimh[0].expect == 403
    assert cimh[0].code == "CIMH_CANNOT_REQUEST"


def test_infer_rules() -> None:
    assert infer("inventory", "/units", {"summary": "x"})["roles"] == ["staff", "admin"]
    assert infer("identity", "/x", {"security": [], "summary": "y"})["ownership"] == "public"
    assert infer("identity", "/internal/t", {"summary": "z"})["roles"] == ["service"]
    assert infer("identity", "/a", {"summary": "Approve (admin)"})["roles"] == ["admin"]
    assert infer("orders", "/r", {"summary": "Accept (requester or admin) - X"})["ownership"] == "requester"
    assert infer("orders", "/r", {"summary": "Mystery"}).get("review") is True


def test_validate_flags_problems() -> None:
    bad = {"endpoints": {"GET /a": {"roles": ["wizard"], "ownership": "nope", "review": True}}}
    errors = validate(bad, allow_review=False)
    assert len(errors) == 3


def test_repo_matrix_is_clean() -> None:
    m = load()
    assert validate(m, allow_review=False) == []
    assert len(all_cases(m)) > len(m["endpoints"])
