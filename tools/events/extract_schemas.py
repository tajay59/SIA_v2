"""Extract one JSON Schema per event type from docs/api/events.asyncapi.yaml into packages/event-schemas.

    python tools/events/extract_schemas.py [--spec ../docs/api/events.asyncapi.yaml]

Output: packages/event-schemas/schemas/<event.type>.v<version>.json (payload schema with all
$refs inlined) + index.json mapping event type -> file. Producers/consumers validate payloads
against these in tests; Apicurio registration (backward-compatible rule) uses the same files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

V2 = Path(__file__).resolve().parents[2]
DEFAULT_SPEC = V2.parent / "docs" / "api" / "events.asyncapi.yaml"
OUT = V2 / "packages" / "event-schemas" / "schemas"


def resolve(node: Any, root: dict[str, Any], base: Path, seen: tuple[str, ...] = ()) -> Any:
    if isinstance(node, dict):
        if "$ref" in node and len(node) == 1:
            ref = node["$ref"]
            if ref in seen:
                return {"description": f"recursive {ref}"}
            file_part, _, pointer = ref.partition("#")
            doc = root
            if file_part:
                doc = yaml.safe_load((base / file_part).read_text(encoding="utf-8"))
            target: Any = doc
            for part in [p for p in pointer.split("/") if p]:
                target = target[part.replace("~1", "/").replace("~0", "~")]
            return resolve(target, doc, base, (*seen, ref))
        return {k: resolve(v, root, base, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve(v, root, base, seen) for v in node]
    return node


EVENT_RE = re.compile(r"^[a-z]+\.[a-z_]+$")


def event_types(name: str, message: dict[str, Any]) -> list[str]:
    """A message may cover several types sharing one payload: "unit.stowed / unit.picked"."""
    raw = str(message.get("name", ""))
    types = [t.strip() for t in raw.split("/") if t.strip()]
    if types and all(EVENT_RE.match(t) for t in types):
        return types
    raise ValueError(f"message {name}: cannot read event type(s) from name {raw!r}")


def extract(spec_path: Path) -> dict[str, dict[str, Any]]:
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    messages = (spec.get("components") or {}).get("messages") or {}
    out: dict[str, dict[str, Any]] = {}
    for name, message in messages.items():
        message = resolve(message, spec, spec_path.parent)
        payload = message.get("payload") or {}
        for etype in event_types(name, message):
            out[etype] = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": etype, **payload}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    schemas = extract(args.spec)
    args.out.mkdir(parents=True, exist_ok=True)
    index = {}
    for etype, schema in sorted(schemas.items()):
        fname = f"{etype}.v1.json"
        (args.out / fname).write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        index[etype] = fname
    (args.out / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"{len(schemas)} event schemas -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
