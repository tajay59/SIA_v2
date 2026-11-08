"""Generated state-machine tests (TEST_STRATEGY §4; P5 exit: every illegal transition returns 409).

Oracle: tests/transitions/request_paid.yaml and request_probono.yaml.
  1. order_svc.domain.TRANSITIONS equals the YAML tables exactly (no drift either way).
  2. For every API action and every status the action is NOT allowed from, the endpoint answers
     409 ORDER_ILLEGAL_TRANSITION (called as an admin, who may perform customer and staff actions alike,
     with a valid body, so nothing but the state machine can refuse it).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

from order_svc import domain as d

from .conftest import ADMIN, Ctx

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "transitions"))
from transition_cases import check, load, statuses

TABLES = {d.PAID: load("request_paid"), d.PROBONO: load("request_probono")}
REASON = {"reason": "Generated test"}
# action -> (method, path, body). `agreement`/`accept` bodies are schema-valid; legality is checked first.
ACTIONS: dict[str, tuple[str, str, Any]] = {
    "start-quoting": ("POST", "start-quoting", None),
    "quote-draft": ("PUT", "quote-draft", {"supplierQuotes": []}),
    "send-quote": ("POST", "send-quote", None),
    "agreement": ("POST", "agreement", {"quoteVersion": 1, "choices": []}),
    "accept": ("POST", "accept", {"quoteVersion": 1, "signedAgreementFileId": "FILx"}),
    "decline": ("POST", "decline", REASON),
    "cancel": ("POST", "cancel", REASON),
    "reject-agreement": ("POST", "reject-agreement", REASON),
    "purchase": ("POST", "purchase-orders", {"agreementVerified": True, "purchaseOrders": []}),
    "approve": ("POST", "approve", None),
    "reject": ("POST", "reject", REASON),
    "pick": ("POST", "picks", {"lineId": "L1", "unit": "MET1_00"}),
    "ship": ("POST", "ship", {"carrier": "HAND", "date": "2026-11-09"}),
    "deliver": ("POST", "deliver", None),
}
# Where each action is legal (beyond the table): quote drafts while quoting or revising; new choices
# while awaiting the agreement; picks while purchasing (PAID) or approved/picking (Pro Bono).
EXTRA = {
    (d.PAID, "quote-draft"): {"QUOTING", "QUOTED"},
    (d.PAID, "agreement"): {"AWAITING_AGREEMENT"},
    (d.PAID, "pick"): {"PURCHASING"},
    (d.PROBONO, "pick"): {"APPROVED", "PICKING"},
}
PAID_ONLY = {
    "start-quoting",
    "quote-draft",
    "send-quote",
    "agreement",
    "accept",
    "decline",
    "reject-agreement",
    "purchase",
}
PROBONO_ONLY = {"approve", "reject"}


def legal_from(kind: str, action: str) -> set[str]:
    table = {t["from"] for t in TABLES[kind]["transitions"] if t.get("action") == action}
    return table | EXTRA.get((kind, action), set())


def illegal_cases() -> list[tuple[str, str, str]]:
    out = []
    for kind, table in TABLES.items():
        for action in ACTIONS:
            if (kind == d.PAID and action in PROBONO_ONLY) or (kind == d.PROBONO and action in PAID_ONLY):
                continue  # the other type's actions are covered by test_wrong_type_actions
            for src in statuses(table):
                if src not in legal_from(kind, action):
                    out.append((kind, action, src))
    return out


CASES = illegal_cases()


@pytest.mark.parametrize("kind", [d.PAID, d.PROBONO])
def test_tables_are_valid(kind: str) -> None:
    assert check(TABLES[kind]) == []


@pytest.mark.parametrize("kind", [d.PAID, d.PROBONO])
def test_domain_matches_the_yaml(kind: str) -> None:
    yaml_pairs = {(t["from"], t["to"]): t["action"] for t in TABLES[kind]["transitions"]}
    code_pairs = {(s, t): a for (k, s, t), (a, _) in d.TRANSITIONS.items() if k == kind}
    assert code_pairs == yaml_pairs


def test_generated_cases_exist() -> None:
    assert len(CASES) > 100


def _request(ctx: Ctx, kind: str, status: str) -> str:
    pid = "PRO1" if kind == d.PROBONO else "MET1"
    assert ctx.cart_add(pid, 1).status_code == 200
    (req,) = ctx.submit(None if kind == d.PROBONO else "BBD")
    ctx.force(req["id"], status=status, quoteVersion=1)
    return str(req["id"])


def _call(ctx: Ctx, rid: str, action: str) -> Any:
    method, path, body = ACTIONS[action]
    headers = {**ADMIN, "If-Match": str(ctx.get(rid, ADMIN)["version"]), "Idempotency-Key": uuid.uuid4().hex}
    return ctx.client.request(method, ctx.url(f"/requests/{rid}/{path}"), headers=headers, json=body)


@pytest.mark.req("TR-ORD-1")
@pytest.mark.parametrize(("kind", "action", "src"), CASES, ids=lambda x: str(x))
def test_illegal_transition_is_409(ctx: Ctx, kind: str, action: str, src: str) -> None:
    rid = _request(ctx, kind, src)
    before = ctx.doc(rid)
    r = _call(ctx, rid, action)
    assert r.status_code == 409, f"{kind} {action} from {src}: {r.status_code} {r.text[:200]}"
    assert r.json()["code"] == "ORDER_ILLEGAL_TRANSITION"
    after = ctx.doc(rid)
    assert (after["status"], after["version"]) == (before["status"], before["version"])


@pytest.mark.parametrize(
    ("kind", "action"), [(d.PAID, a) for a in sorted(PROBONO_ONLY)] + [(d.PROBONO, a) for a in sorted(PAID_ONLY)]
)
def test_wrong_type_actions(ctx: Ctx, kind: str, action: str) -> None:
    rid = _request(ctx, kind, "SUBMITTED")
    r = _call(ctx, rid, action)
    assert r.status_code == 409
    assert r.json()["code"] == "ORDER_ILLEGAL_TRANSITION"
