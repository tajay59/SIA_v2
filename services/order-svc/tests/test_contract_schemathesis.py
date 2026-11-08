"""Schemathesis property tests (TEST_STRATEGY §4, CI gate) for order-svc: generated requests against every
operation (staff for public operations, order-svc for internal ones, and anonymously). The service must never
5xx and every response must match the documented status, content type and schema.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

schemathesis = pytest.importorskip("schemathesis")
import fakeredis.aioredis  # noqa: E402
from hypothesis import HealthCheck, settings  # noqa: E402
from schemathesis import checks  # noqa: E402

from cimh_common.testing import AsyncMongoMock  # noqa: E402
from order_svc.config import Settings  # noqa: E402
from order_svc.main import build_app  # noqa: E402

from .conftest import ADMIN, DOCUMENT, USER, MemoryDeps, verifier  # noqa: E402

app = build_app(
    Settings(),
    db=AsyncMongoMock(),
    redis=fakeredis.aioredis.FakeRedis(),
    token_verifier=verifier(),
    deps=MemoryDeps(),
    configure_logs=False,
)
CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "api" / "orders.openapi.yaml"
schema = schemathesis.openapi.from_path(CONTRACT)
schema.app = app

_ERR = "./common.yaml#/components/responses/"


def _apply_implicit_responses(raw: dict[str, Any]) -> None:
    """API README §4 "Implicit responses": allowed on any operation without being listed."""
    for item in raw["paths"].values():
        for method, op in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            extra = {"400": "BadRequest", "429": "TooManyRequests", "503": "Unavailable"}
            if op.get("security", raw.get("security")):
                extra.update({"401": "Unauthorized", "403": "Forbidden"})
            if op.get("requestBody") or op.get("parameters") or item.get("parameters"):
                extra["422"] = "Unprocessable"
            if any(str(p.get("$ref", "")).endswith("/IfMatch") for p in op.get("parameters", [])):
                extra["428"] = "PreconditionRequired"
            responses = op.setdefault("responses", {})
            for status, name in extra.items():
                responses.setdefault(status, {"$ref": _ERR + name})


_apply_implicit_responses(schema.raw_schema)

CHECKS = [
    checks.not_a_server_error,
    checks.status_code_conformance,
    checks.content_type_conformance,
    checks.response_schema_conformance,
    checks.response_headers_conformance,
    checks.negative_data_rejection,
]


def _headers(case: schemathesis.Case) -> dict[str, str]:
    if case.path.startswith("/internal/"):
        who = DOCUMENT
    elif case.path.startswith("/cart") or (case.path == "/requests" and case.method.upper() == "POST"):
        who = USER  # carts and submission belong to customers
    else:
        who = ADMIN
    # A fresh key per call, unless the case generated one itself.
    return {**who, "Idempotency-Key": uuid.uuid4().hex}


@schema.parametrize()
@settings(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
def test_orders_api_conforms_as_admin_user_or_document_svc(case: schemathesis.Case) -> None:
    case.call_and_validate(headers={**_headers(case), **(case.headers or {})}, checks=CHECKS)


@schema.parametrize()
@settings(max_examples=10, deadline=None, suppress_health_check=list(HealthCheck))
def test_orders_api_conforms_anonymously(case: schemathesis.Case) -> None:
    case.call_and_validate(checks=[*CHECKS, checks.ignored_auth])
