from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from cimh_common.outbox import EventEnvelope

SCHEMAS = Path(__file__).resolve().parents[2] / "packages" / "event-schemas" / "schemas"
INDEX = json.loads((SCHEMAS / "index.json").read_text(encoding="utf-8"))


def test_index_lists_every_file() -> None:
    files = {p.name for p in SCHEMAS.glob("*.json")} - {"index.json"}
    assert set(INDEX.values()) == files
    assert len(INDEX) >= 40


@pytest.mark.parametrize("etype", sorted(INDEX))
def test_schema_is_valid_and_matches_envelope(etype: str) -> None:
    schema = json.loads((SCHEMAS / INDEX[etype]).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    # The envelope fields the AsyncAPI requires must exist on py-common's EventEnvelope.
    required: set[str] = set()
    for part in schema.get("allOf", [schema]):
        required |= set(part.get("required", []))
    assert required <= set(EventEnvelope.model_fields), required - set(EventEnvelope.model_fields)
