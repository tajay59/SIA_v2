"""Turn the authz matrix into concrete test cases (TEST_STRATEGY §5).

For each endpoint:
  1. anonymous -> 401 (or 2xx if public)
  2. each authenticated role not allowed -> 403
  3. allowed role on another user's / organisation's resource -> 404 (hidden)
  4. allowed role on own resource -> 2xx
  5. @cimh.edu.bb user on cart/request endpoints -> 403 CIMH_CANNOT_REQUEST

Services use `cases_for(...)` with pytest.mark.parametrize and supply fixtures that create
"own" and "other" resources; this module only decides who should get which status.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

MATRIX = Path(__file__).resolve().parents[2] / "tests" / "authz" / "matrix.yaml"
AUTH_ROLES = ("user", "staff", "admin", "service")
SCOPED = {"self", "same_org", "requester"}


@dataclass(frozen=True)
class Case:
    endpoint: str
    actor: str  # anonymous | user | staff | admin | service | cimh_user
    target: str  # own | other | none
    expect: int | str  # status, or "2xx"
    code: str | None = None

    @property
    def id(self) -> str:
        return f"{self.endpoint} [{self.actor}/{self.target}]"


def load(path: Path = MATRIX) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def cases_for(endpoint: str, row: dict[str, Any]) -> list[Case]:
    roles = set(row["roles"])
    ownership = row["ownership"]
    out: list[Case] = []
    public = ownership == "public"

    out.append(Case(endpoint, "anonymous", "none", "2xx" if public else 401))
    for role in AUTH_ROLES:
        if public:
            continue
        if role not in roles:
            out.append(Case(endpoint, role, "none", 403))
            continue
        if ownership in SCOPED and role == "user":
            out.append(Case(endpoint, role, "own", "2xx"))
            out.append(Case(endpoint, role, "other", 404))
        else:
            out.append(Case(endpoint, role, "own" if ownership in SCOPED else "none", "2xx"))
    if row.get("cimh_forbidden"):
        out.append(Case(endpoint, "cimh_user", "none", 403, "CIMH_CANNOT_REQUEST"))
    return out


def all_cases(matrix: dict[str, Any] | None = None) -> list[Case]:
    m = matrix or load()
    return [c for ep, row in m["endpoints"].items() for c in cases_for(ep, row)]


def endpoints_for(service_base: str, matrix: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    m = matrix or load()
    return {ep: row for ep, row in m["endpoints"].items() if ep.split(" ", 1)[1].startswith(service_base)}
