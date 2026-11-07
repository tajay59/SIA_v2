"""Transition-table test generator (TEST_STRATEGY §4).

Loads tests/transitions/*.yaml and yields:
  legal(table)    every (from, to, action) in the table          -> must succeed
  illegal(table)  every other (from, to) over all known statuses  -> must be rejected with `illegal_code`

`check(table)` validates the table itself: every status reachable from `initial`, terminal
states have no outgoing transitions, and every non-terminal state can leave.

Domain code uses `allowed(table, from)` in tests to compare against its own state machine,
so the YAML and the implementation can't drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

TABLES_DIR = Path(__file__).resolve().parents[2] / "tests" / "transitions"


@dataclass(frozen=True)
class Transition:
    src: str
    dst: str
    action: str | None = None

    @property
    def id(self) -> str:
        return f"{self.src}->{self.dst}" + (f" ({self.action})" if self.action else "")


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((TABLES_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    return data


def tables() -> dict[str, dict[str, Any]]:
    return {p.stem: load(p.stem) for p in sorted(TABLES_DIR.glob("*.yaml"))}


def statuses(table: dict[str, Any]) -> list[str]:
    seen: dict[str, None] = {table["initial"]: None}
    for t in table["transitions"]:
        seen.setdefault(t["from"], None)
        seen.setdefault(t["to"], None)
    for s in table.get("terminal", []):
        seen.setdefault(s, None)
    return list(seen)


def legal(table: dict[str, Any]) -> list[Transition]:
    return [Transition(t["from"], t["to"], t.get("action")) for t in table["transitions"]]


def allowed(table: dict[str, Any], src: str) -> set[str]:
    return {t["to"] for t in table["transitions"] if t["from"] == src}


def illegal(table: dict[str, Any]) -> list[Transition]:
    ok = {(t.src, t.dst) for t in legal(table)}
    all_s = statuses(table)
    return [Transition(a, b) for a in all_s for b in all_s if (a, b) not in ok and a != b]


def check(table: dict[str, Any]) -> list[str]:
    errors = []
    all_s = statuses(table)
    terminal = set(table.get("terminal", []))
    reach = {table["initial"]}
    frontier = [table["initial"]]
    while frontier:
        s = frontier.pop()
        for d in allowed(table, s):
            if d not in reach:
                reach.add(d)
                frontier.append(d)
    errors += [f"{s} unreachable from {table['initial']}" for s in all_s if s not in reach]
    errors += [f"terminal {s} has outgoing transitions" for s in terminal if allowed(table, s)]
    errors += [f"{s} is a dead end but not terminal" for s in all_s if s not in terminal and not allowed(table, s)]
    return errors
