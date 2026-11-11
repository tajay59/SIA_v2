"""MongoDB `$jsonSchema` validators (BSD §7).

Each service owns the schemas of its collections (`<service>/schemas.py`) and applies them at start-up next to its
indexes. The level comes from `MONGO_VALIDATION`:

- `strict` (default; dev, CI, production after migration sign-off): `validationLevel: strict`, `action: error`.
- `migration` (during a migration run): `moderate` / `warn`, so legacy documents load and violations are logged.

The schemas pin what every document must have (ids, versions, timestamps, enumerations) and leave other fields open:
services add fields over time, and a too-tight validator would reject correct writes in production.
"""

from __future__ import annotations

import os
from typing import Any

from pymongo.errors import OperationFailure

NAMESPACE_EXISTS = 48


def levels(mode: str | None = None) -> tuple[str, str]:
    mode = (mode or os.environ.get("MONGO_VALIDATION") or "strict").lower()
    if mode not in ("strict", "migration"):
        raise ValueError(f"MONGO_VALIDATION must be strict or migration, not {mode!r}")
    return ("strict", "error") if mode == "strict" else ("moderate", "warn")


async def apply_validators(db: Any, schemas: dict[str, dict[str, Any]], mode: str | None = None) -> list[str]:
    """Creates each collection with its validator, or updates the validator of an existing one. Idempotent."""
    level, action = levels(mode)
    done = []
    for name, schema in schemas.items():
        opts = {"validator": {"$jsonSchema": schema}, "validationLevel": level, "validationAction": action}
        try:
            await db.command("create", name, **opts)
        except OperationFailure as exc:
            if exc.code != NAMESPACE_EXISTS:
                raise
            await db.command("collMod", name, **opts)
        done.append(name)
    return done


# Building blocks shared by the service schemas.
STRING = {"bsonType": "string"}
ID = {"bsonType": "string", "minLength": 1}
DATE = {"bsonType": "date"}
BOOL = {"bsonType": "bool"}
INT = {"bsonType": ["int", "long"]}
COUNT = {"bsonType": ["int", "long"], "minimum": 0}
VERSION = {"bsonType": ["int", "long"], "minimum": 1}
ARRAY = {"bsonType": "array"}
OBJECT = {"bsonType": "object"}
MONEY = {"bsonType": ["decimal", "null"]}


def nullable(spec: dict[str, Any]) -> dict[str, Any]:
    kinds = spec["bsonType"] if isinstance(spec["bsonType"], list) else [spec["bsonType"]]
    return {**spec, "bsonType": [*kinds, "null"]}


def enum(*values: str | None) -> dict[str, Any]:
    return {"enum": list(values)}


def document(required: dict[str, dict[str, Any]], optional: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """An object schema: `required` fields must exist with these types; `optional` ones are typed when present."""
    return {
        "bsonType": "object",
        "required": sorted(required),
        "properties": {**(optional or {}), **required},
    }
