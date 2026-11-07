from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "seed"))
from seed_dev import build, main


def test_seed_is_deterministic_and_covers_cases() -> None:
    a, b = build(1, 50), build(1, 50)
    assert [p["name"] for p in a["product"]] == [p["name"] for p in b["product"]]
    users = a["accounts"]
    assert {u["role"] for u in users} == {"admin", "staff", "user"}
    assert {u["status"] for u in users} >= {"ACTIVE", "PENDING_APPROVAL", "PENDING_VERIFICATION", "SUSPENDED"}
    assert any(u["isCimh"] and u["role"] == "user" for u in users)
    assert all(u["email"].endswith(("@example.org", "@cimh.edu.bb")) for u in users)
    # carts only for active member (non-CIMH) users
    owners = {c["requesterId"] for c in a["orders"]}
    by_id = {u["id"]: u for u in users}
    assert all(by_id[o]["status"] == "ACTIVE" and not by_id[o]["isCimh"] for o in owners)
    # money is a 2-decimal string, never a float
    assert all(isinstance(p["cost"], str) and p["cost"].split(".")[1].__len__() == 2 for p in a["product"])
    assert all(not p["probono"] or p["sellable"] for p in a["product"])


def test_refuses_remote_hosts() -> None:
    assert main(["--mongo", "mongodb://172.16.0.203:27017", "--products", "1"]) == 2


def test_dry_run() -> None:
    assert main(["--dry-run", "--products", "3"]) == 0
