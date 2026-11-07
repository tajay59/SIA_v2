from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "transitions"))
from transition_cases import allowed, check, illegal, legal, statuses, tables

TABLES = tables()


@pytest.mark.parametrize("name", sorted(TABLES))
def test_table_is_well_formed(name: str) -> None:
    assert check(TABLES[name]) == []


def test_paid_flow_matches_business_rules() -> None:
    t = TABLES["request_paid"]
    assert allowed(t, "QUOTED") == {"QUOTED", "AWAITING_AGREEMENT", "DECLINED", "CANCELLED"}
    assert allowed(t, "ACCEPTED") == {"PURCHASING", "AWAITING_AGREEMENT", "CANCELLED"}
    assert allowed(t, "DELIVERED") == set()
    pairs = {(x.src, x.dst) for x in illegal(t)}
    assert ("SUBMITTED", "ACCEPTED") in pairs  # can't skip the quote
    assert ("DELIVERED", "CANCELLED") in pairs
    assert ("SHIPPED", "PURCHASING") in pairs


def test_probono_has_no_quote_states() -> None:
    t = TABLES["request_probono"]
    assert "QUOTED" not in statuses(t)
    assert allowed(t, "SUBMITTED") == {"APPROVED", "REJECTED", "CANCELLED"}


def test_legal_and_illegal_partition_all_pairs() -> None:
    for t in TABLES.values():
        n = len(statuses(t))
        legal_pairs = {(x.src, x.dst) for x in legal(t) if x.src != x.dst}
        assert len(legal_pairs) + len(illegal(t)) == n * (n - 1)


def test_check_finds_problems() -> None:
    bad = {
        "initial": "A",
        "terminal": ["C"],
        "transitions": [{"from": "A", "to": "B"}, {"from": "C", "to": "A"}, {"from": "D", "to": "C"}],
    }
    errors = check(bad)
    assert any("unreachable" in e for e in errors)
    assert any("terminal C" in e for e in errors)
    assert any("B is a dead end" in e for e in errors)
