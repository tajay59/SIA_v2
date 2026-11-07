"""RFC 9457 problem details, as defined in docs/api/README.md §4 and common.yaml#Problem."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"
ERROR_BASE = "https://errors.cimh.edu.bb"

_TITLES = {
    400: "Bad request",
    401: "Not authenticated",
    403: "Forbidden",
    404: "Not found",
    405: "Method not allowed",
    409: "Conflict",
    413: "Payload too large",
    415: "Unsupported media type",
    422: "Validation failed",
    429: "Too many requests",
    500: "Internal error",
    503: "Dependency unavailable",
}


class ProblemError(Exception):
    """Raise anywhere in a request to return a Problem response.

    `code` must be one of the stable codes in the API README (e.g. ORDER_ILLEGAL_TRANSITION).
    """

    def __init__(
        self,
        status: int,
        code: str | None = None,
        detail: str | None = None,
        *,
        title: str | None = None,
        type_path: str | None = None,
        errors: list[dict[str, str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or code or str(status))
        self.status = status
        self.code = code
        self.detail = detail
        self.title = title or _TITLES.get(status, "Error")
        self.type_path = type_path or (code.lower().replace("_", "-") if code else "about-blank")
        self.errors = errors or []
        self.headers = headers or {}


# Convenience constructors for the common cases.
def unauthorized(detail: str = "Authentication required", code: str | None = None) -> ProblemError:
    return ProblemError(401, code, detail)


def forbidden(detail: str = "Not allowed", code: str | None = None) -> ProblemError:
    return ProblemError(403, code, detail)


def not_found(detail: str = "Not found") -> ProblemError:
    """Also used for resources the caller may not see (README §3: 404, not 403)."""
    return ProblemError(404, None, detail)


def conflict(code: str, detail: str) -> ProblemError:
    return ProblemError(409, code, detail)


def problem_body(
    status: int,
    trace_id: str,
    *,
    code: str | None = None,
    detail: str | None = None,
    title: str | None = None,
    type_path: str = "about-blank",
    errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"{ERROR_BASE}/{type_path}",
        "title": title or _TITLES.get(status, "Error"),
        "status": status,
        "traceId": trace_id,
    }
    if code:
        body["code"] = code
    if detail:
        body["detail"] = detail
    if errors:
        body["errors"] = errors
    return body


def _trace_id(request: Request) -> str:
    return str(getattr(request.state, "trace_id", "") or "unknown")


def _response(status: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    """Make every error a Problem; never leak stack traces."""

    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: ProblemError) -> JSONResponse:
        body = problem_body(
            exc.status,
            _trace_id(request),
            code=exc.code,
            detail=exc.detail,
            title=exc.title,
            type_path=exc.type_path,
            errors=exc.errors,
        )
        return _response(exc.status, body, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(p) for p in err.get("loc", ())[1:]) or "body",
                "message": str(err.get("msg", "invalid")),
            }
            for err in exc.errors()
        ]
        body = problem_body(
            422, _trace_id(request), code="VALIDATION_FAILED", type_path="validation-failed", errors=errors
        )
        return _response(422, body)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        body = problem_body(exc.status_code, _trace_id(request), detail=str(exc.detail) if exc.detail else None)
        return _response(exc.status_code, body, getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Logged by the logging middleware; the client only gets the trace id.
        body = problem_body(500, _trace_id(request))
        return _response(500, body)
