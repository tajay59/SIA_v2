"""BSD §7 validators: the helper's modes, create-or-update, and that every owned collection has a schema."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pymongo.errors import OperationFailure

from cimh_common.validation import apply_validators, document, enum, levels, nullable

# CLAUDE.md "Target architecture": a service touches only the collections it owns.
OWNED = {
    "identity_svc": {"accounts", "temp", "organisations", "auditlog"},
    "catalog_svc": {"product", "misc"},
    "inventory_svc": {"storage", "history", "stock"},
    "order_svc": {"orders"},
}


class FakeDb:
    def __init__(self, existing: set[str]) -> None:
        self.existing = existing
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def command(self, name: str, coll: str, **opts: Any) -> dict[str, Any]:
        self.calls.append((name, coll, opts))
        if name == "create" and coll in self.existing:
            raise OperationFailure("exists", code=48)
        return {"ok": 1}


def test_levels() -> None:
    assert levels("strict") == ("strict", "error")
    assert levels("migration") == ("moderate", "warn")
    with pytest.raises(ValueError, match="MONGO_VALIDATION"):
        levels("off")


def test_strict_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONGO_VALIDATION", raising=False)
    assert levels() == ("strict", "error")
    monkeypatch.setenv("MONGO_VALIDATION", "migration")
    assert levels() == ("moderate", "warn")


def test_creates_new_collections_and_updates_existing_ones() -> None:
    db = FakeDb(existing={"orders"})
    schema = document({"id": {"bsonType": "string"}})
    asyncio.run(apply_validators(db, {"orders": schema, "temp": schema}, mode="migration"))
    assert [(n, c) for n, c, _ in db.calls] == [("create", "orders"), ("collMod", "orders"), ("create", "temp")]
    assert db.calls[1][2]["validationLevel"] == "moderate"
    assert db.calls[1][2]["validator"] == {"$jsonSchema": schema}


def test_other_errors_are_not_swallowed() -> None:
    class Broken(FakeDb):
        async def command(self, name: str, coll: str, **opts: Any) -> dict[str, Any]:
            raise OperationFailure("not authorized", code=13)

    with pytest.raises(OperationFailure):
        asyncio.run(apply_validators(Broken(set()), {"x": document({})}))


def test_building_blocks() -> None:
    assert nullable({"bsonType": "string"}) == {"bsonType": ["string", "null"]}
    assert enum("A", None) == {"enum": ["A", None]}
    d = document({"b": {}, "a": {}}, {"c": {}})
    assert d["required"] == ["a", "b"]
    assert set(d["properties"]) == {"a", "b", "c"}


@pytest.mark.parametrize("module", sorted(OWNED))
def test_every_owned_collection_has_a_schema(module: str) -> None:
    schemas = pytest.importorskip(f"{module}.schemas").SCHEMAS
    assert set(schemas) == OWNED[module]
    for name, schema in schemas.items():
        assert schema["bsonType"] == "object", name
        assert set(schema["required"]) <= set(schema["properties"]), name
