"""Schemathesis property tests (TEST_STRATEGY §4, CI gate) for document-svc: generated requests against every
operation (staff for public operations, inventory-svc for internal ones, and anonymously). The service must never
5xx and every response must match the documented status, content type and schema.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

schemathesis = pytest.importorskip("schemathesis")
import tempfile  # noqa: E402

from hypothesis import HealthCheck, settings  # noqa: E402
from schemathesis import checks  # noqa: E402

from document_svc.config import Settings  # noqa: E402
from document_svc.main import build_app  # noqa: E402

from .conftest import ADMIN, INVENTORY, FakeClamd, MemoryOrders, MemoryPublisher, request_doc, verifier  # noqa: E402

app = build_app(
    Settings(data_dir=tempfile.mkdtemp(prefix="docsvc-")),
    token_verifier=verifier(),
    orders=MemoryOrders(requests={"ORD1": request_doc("ORD1")}),
    publisher=MemoryPublisher(),
    scanner=FakeClamd(),
    configure_logs=False,
)
CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "api" / "documents.openapi.yaml"
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
    return INVENTORY if case.path.startswith("/internal/") else ADMIN


@schema.parametrize()
@settings(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
def test_documents_api_conforms_as_admin_or_inventory_svc(case: schemathesis.Case) -> None:
    case.call_and_validate(headers={**_headers(case), **(case.headers or {})}, checks=CHECKS)


@schema.parametrize()
@settings(max_examples=10, deadline=None, suppress_health_check=list(HealthCheck))
def test_documents_api_conforms_anonymously(case: schemathesis.Case) -> None:
    case.call_and_validate(checks=[*CHECKS, checks.ignored_auth])
