"""Schemathesis property tests (TEST_STRATEGY Â§4, CI gate): generated requests against every identity
operation; the service must never 5xx and every response must match the documented status, content type
and schema. Runs on the in-memory app (mongomock + fakeredis), so it is part of the unit job.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fakeredis.aioredis
import pytest

schemathesis = pytest.importorskip("schemathesis")
from hypothesis import HealthCheck, settings  # noqa: E402
from schemathesis import checks  # noqa: E402

from cimh_common.testing import AsyncMongoMock  # noqa: E402
from identity_svc.config import Settings  # noqa: E402
from identity_svc.main import build_app  # noqa: E402


async def _no_breach(_: str) -> bool:
    return False


app = build_app(
    Settings(service_secrets={"notification": "n-secret"}, cookie_secure=False),
    db=AsyncMongoMock(),
    redis=fakeredis.aioredis.FakeRedis(),
    breach_check=_no_breach,
    configure_logs=False,
)
CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "api" / "identity.openapi.yaml"
schema = schemathesis.openapi.from_path(CONTRACT)
schema.app = app

# API README §4 "Implicit responses": allowed on any operation without being listed.
_ERR = "./common.yaml#/components/responses/"


def _apply_implicit_responses(raw: dict[str, Any]) -> None:
    for item in raw["paths"].values():
        for method, op in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            extra = {"400": "BadRequest", "429": "TooManyRequests", "503": "Unavailable"}
            if op.get("security", raw.get("security")):  # [] = public
                extra.update({"401": "Unauthorized", "403": "Forbidden"})
            if op.get("requestBody") or op.get("parameters") or item.get("parameters"):
                extra["422"] = "Unprocessable"
            if any(str(p.get("$ref", "")).endswith("/IfMatch") for p in op.get("parameters", [])):
                extra["428"] = "PreconditionRequired"
            responses = op.setdefault("responses", {})
            for status, name in extra.items():
                responses.setdefault(status, {"$ref": _ERR + name})


_apply_implicit_responses(schema.raw_schema)

# positive_data_acceptance is left out on purpose: schema-valid but random input (e.g. a verification
# code) is rightly rejected by business rules. unsupported_method/allow_header_conformance: FastAPI's 405s.
CHECKS = [
    checks.not_a_server_error,
    checks.status_code_conformance,
    checks.content_type_conformance,
    checks.response_schema_conformance,
    checks.response_headers_conformance,
    checks.negative_data_rejection,
    checks.ignored_auth,
]


@schema.parametrize()
@settings(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
def test_identity_api_conforms(case: schemathesis.Case) -> None:
    case.call_and_validate(checks=CHECKS)
