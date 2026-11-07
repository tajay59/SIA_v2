"""CI gate: the authz matrix is valid and complete.

Fails if:
  - a row has unknown roles/ownership, or is still marked `review: true`
    (allowed with --allow-review while services are being built);
  - an operation in the OpenAPI specs (docs/api) has no row;
  - a route in any running FastAPI app passed with --app module:attr has no row
    ("no untested endpoint can ship").
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from authz_cases import MATRIX, load
from build_matrix import DEFAULT_SPECS, OWNERSHIP, ROLE_ORDER, key, operations

INFRA_PATHS = {"/health/live", "/health/ready", "/metrics", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def validate(matrix: dict[str, Any], allow_review: bool) -> list[str]:
    errors = []
    for ep, row in matrix["endpoints"].items():
        if not re.match(r"^(GET|POST|PUT|PATCH|DELETE) /", ep):
            errors.append(f"{ep}: bad key")
        bad = set(row.get("roles", [])) - set(ROLE_ORDER)
        if bad or not row.get("roles"):
            errors.append(f"{ep}: bad roles {sorted(bad) or 'none'}")
        if row.get("ownership") not in OWNERSHIP:
            errors.append(f"{ep}: bad ownership {row.get('ownership')!r}")
        if row.get("review") and not allow_review:
            errors.append(f"{ep}: still marked review: true")
    return errors


def app_routes(spec: str) -> list[str]:
    module, attr = spec.split(":")
    app = getattr(importlib.import_module(module), attr)
    # Use the generated OpenAPI document: it lists every public route, including those of
    # included routers (which newer FastAPI versions do not expand in app.routes).
    out = []
    for path, item in app.openapi().get("paths", {}).items():
        if path in INFRA_PATHS:
            continue
        for method in item:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                out.append(f"{method.upper()} {path}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", type=Path, default=MATRIX)
    ap.add_argument("--specs", type=Path, default=DEFAULT_SPECS)
    ap.add_argument("--app", action="append", default=[], help="module:attr of a FastAPI app to check")
    ap.add_argument("--allow-review", action="store_true")
    args = ap.parse_args(argv)

    matrix = load(args.matrix)
    errors = validate(matrix, args.allow_review)
    rows = set(matrix["endpoints"])
    if args.specs.exists():
        for service, method, path, _ in operations(args.specs):
            if key(service, method, path) not in rows:
                errors.append(f"{key(service, method, path)}: in OpenAPI but missing from matrix")
    for spec in args.app:
        for ep in app_routes(spec):
            if ep not in rows:
                errors.append(f"{ep}: served by {spec} but missing from matrix")

    for e in errors:
        print("ERROR", e)
    print(f"{len(rows)} endpoints checked, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
