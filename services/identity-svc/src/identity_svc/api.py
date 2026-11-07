"""HTTP layer for identity-svc: docs/api/identity.openapi.yaml is the contract."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from cimh_common.auth import CSRF_COOKIE, Principal, check_csrf
from cimh_common.authz import (
    authenticated_principal,
    current_principal,
    require_admin,
    require_admin_mfa_setup,
    require_service,
    require_staff,
)
from cimh_common.errors import ProblemError, unauthorized

from .service import IdentityService, account_view
from .tokens import IssuedTokens

Role = Literal["user", "staff", "admin"]
Status = Literal["PENDING_VERIFICATION", "PENDING_APPROVAL", "ACTIVE", "REJECTED", "EXPIRED", "SUSPENDED"]
Code = Annotated[str, Field(pattern=r"^\d{6}$")]
Country = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
Password = Annotated[str, Field(min_length=12, max_length=256)]

ACCESS_COOKIE_PATH = "/api"
REFRESH_COOKIE_PATH = "/api/identity/v1/auth"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterIn(Strict):
    firstname: str = Field(max_length=100, min_length=1)
    lastname: str = Field(max_length=100, min_length=1)
    email: EmailStr
    password: Password
    organisationText: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=100)
    country: Country
    phone: str | None = Field(default=None, max_length=40)


class VerifyIn(Strict):
    email: EmailStr
    code: Code


class EmailIn(Strict):
    email: EmailStr


class LoginIn(Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    totp: Code | None = None
    client: Literal["web", "mobile"] = "web"


class RefreshIn(Strict):
    refreshToken: str | None = None


class ResetIn(Strict):
    email: EmailStr
    code: Code
    newPassword: Password


class TotpIn(Strict):
    totp: Code


class Address(Strict):
    line1: str = Field(max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(max_length=100)
    parish: str | None = Field(default=None, max_length=100)
    country: Country
    zip: str | None = Field(default=None, max_length=20)
    organisation: str | None = Field(default=None, max_length=200)
    attention: str | None = Field(default=None, max_length=200)
    firstname: str = Field(max_length=100)
    lastname: str = Field(max_length=100)
    email: EmailStr
    tel: str | None = Field(default=None, max_length=40)


class MePatch(Strict):
    firstname: str | None = Field(default=None, max_length=100, min_length=1)
    lastname: str | None = Field(default=None, max_length=100, min_length=1)
    phone: str | None = Field(default=None, max_length=40)
    department: str | None = None
    country: Country | None = None
    addresses: list[Address] | None = Field(default=None, max_length=10)
    image: str | None = None


class EmailChangeIn(Strict):
    newEmail: EmailStr
    password: str


class PasswordChangeIn(Strict):
    currentPassword: str
    newPassword: Password


class ApproveIn(Strict):
    organisationId: str
    role: Role | None = None


class ReasonIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


class Decision(Strict):
    accountId: str
    version: int
    decision: Literal["approve", "deny"]
    organisationId: str | None = None
    role: Role | None = None
    reason: str | None = Field(default=None, max_length=500)


class BulkIn(Strict):
    decisions: list[Decision] = Field(max_length=100)


class RoleIn(Strict):
    role: Role


class OrgIn(Strict):
    name: str = Field(min_length=1, max_length=200)
    country: Country
    type: Literal["met_service", "hydro_service", "government", "academic", "other"] | None = None
    emailDomains: list[str] | None = None
    aliases: list[str] | None = None
    active: bool | None = None


class MergeIn(Strict):
    targetId: str


class ServiceTokenIn(Strict):
    service: Literal["catalog", "inventory", "order", "document", "notification", "media"]
    secret: str


# ---------------------------------------------------------------- helpers


def svc(request: Request) -> IdentityService:
    s: IdentityService = request.app.state.identity
    return s


def cid(request: Request) -> str:
    return str(getattr(request.state, "trace_id", "") or "none")


def client_ip(request: Request) -> str | None:
    # nginx sets X-Real-IP; it is the only hop in front of services.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


def if_match(value: str | None) -> int:
    if not value:
        raise ProblemError(428, "PRECONDITION_REQUIRED", "If-Match header with the current version is required")
    try:
        return int(value.strip().removeprefix("W/").strip('"'))
    except ValueError as exc:
        raise ProblemError(400, None, "If-Match must be a version number") from exc


def with_etag(body: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers={"ETag": f'"{body.get("version", 1)}"'})


def _set_session_cookies(resp: Response, request: Request, tokens: IssuedTokens) -> None:
    s = request.app.state.settings
    common: dict[str, Any] = {"secure": s.cookie_secure, "samesite": "lax", "domain": s.cookie_domain}
    resp.set_cookie(
        "access_token", tokens.access_token, max_age=tokens.expires_in, httponly=True, path=ACCESS_COOKIE_PATH, **common
    )
    resp.set_cookie(
        "refresh_token", tokens.refresh_token, max_age=s.refresh_ttl, httponly=True, path=REFRESH_COOKIE_PATH, **common
    )
    # Double-submit CSRF token: readable by JS, echoed in X-CSRF-Token.
    resp.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(24), max_age=s.refresh_ttl, httponly=False, path="/", **common)


def _clear_cookies(resp: Response, request: Request) -> None:
    s = request.app.state.settings
    for name, path in (
        ("access_token", ACCESS_COOKIE_PATH),
        ("refresh_token", REFRESH_COOKIE_PATH),
        (CSRF_COOKIE, "/"),
    ):
        resp.delete_cookie(name, path=path, domain=s.cookie_domain, secure=s.cookie_secure, samesite="lax")


async def _login_response(request: Request, acc: dict[str, Any], tokens: IssuedTokens, mobile: bool) -> JSONResponse:
    s = svc(request)
    view = account_view(acc, staff_view=False, org_name=await s._org_name(acc.get("organisationId")))
    body: dict[str, Any] = {"account": view, "expiresIn": tokens.expires_in}
    if mobile:
        body.update(accessToken=tokens.access_token, refreshToken=tokens.refresh_token)
    resp = JSONResponse(body)
    if not mobile:
        _set_session_cookies(resp, request, tokens)
    return resp


IfMatch = Annotated[str | None, Header(alias="If-Match")]
Limit = Annotated[int | None, Query(ge=1, le=100)]

router = APIRouter()

# ---------------------------------------------------------------- auth


@router.post("/auth/register", status_code=202, tags=["auth"])
async def register(body: RegisterIn, request: Request) -> Response:
    await svc(request).register(body.model_dump(), cid(request))
    return Response(status_code=202)


@router.post("/auth/verify", tags=["auth"])
async def verify(body: VerifyIn, request: Request) -> dict[str, str]:
    return {"status": await svc(request).verify(body.email, body.code, cid(request))}


@router.post("/auth/verify/resend", status_code=202, tags=["auth"])
async def resend(body: EmailIn, request: Request) -> Response:
    try:
        await svc(request).resend_verification(body.email, cid(request))
    except ProblemError as e:
        if e.status != 429:
            raise
        raise
    return Response(status_code=202)


@router.post("/auth/login", tags=["auth"])
async def login(body: LoginIn, request: Request) -> JSONResponse:
    acc, tokens = await svc(request).login(body.email, body.password, body.totp, client_ip(request), cid(request))
    return await _login_response(request, acc, tokens, body.client == "mobile")


@router.post("/auth/refresh", tags=["auth"])
async def refresh(request: Request, body: RefreshIn | None = None) -> JSONResponse:
    mobile = bool(body and body.refreshToken)
    token = body.refreshToken if body and body.refreshToken else request.cookies.get("refresh_token")
    if not token:
        raise unauthorized("No refresh token")
    if not mobile:
        check_csrf(request)
    acc, tokens = await svc(request).refresh(token)
    return await _login_response(request, acc, tokens, mobile)


@router.post("/auth/logout", status_code=204, tags=["auth"])
async def logout(request: Request, me: Principal = Depends(authenticated_principal)) -> Response:
    await svc(request).logout(me)
    resp = Response(status_code=204)
    _clear_cookies(resp, request)
    return resp


@router.post("/auth/password/forgot", status_code=202, tags=["auth"])
async def forgot(body: EmailIn, request: Request) -> Response:
    await svc(request).forgot_password(body.email, cid(request))
    return Response(status_code=202)


@router.post("/auth/password/reset", status_code=204, tags=["auth"])
async def reset(body: ResetIn, request: Request) -> Response:
    await svc(request).reset_password(body.email, body.code, body.newPassword, cid(request))
    return Response(status_code=204)


@router.post("/auth/mfa/setup", tags=["auth"])
async def mfa_setup(request: Request, me: Principal = Depends(require_admin_mfa_setup)) -> dict[str, str]:
    return {"otpauthUri": await svc(request).mfa_setup(me)}


@router.post("/auth/mfa/confirm", status_code=204, tags=["auth"])
async def mfa_confirm(body: TotpIn, request: Request, me: Principal = Depends(require_admin_mfa_setup)) -> Response:
    await svc(request).mfa_confirm(me, body.totp, cid(request))
    return Response(status_code=204)


@router.get("/.well-known/jwks.json", tags=["auth"])
async def jwks(request: Request) -> JSONResponse:
    return JSONResponse(request.app.state.keys.jwks(), headers={"Cache-Control": "public, max-age=600"})


# ---------------------------------------------------------------- me


@router.get("/me", tags=["me"])
async def get_me(request: Request, me: Principal = Depends(authenticated_principal)) -> JSONResponse:
    return with_etag(await svc(request).me(me))


@router.patch("/me", tags=["me"])
async def patch_me(
    body: MePatch, request: Request, version: IfMatch = None, me: Principal = Depends(current_principal)
) -> JSONResponse:
    fields = body.model_dump(exclude_unset=True, mode="json")
    if not fields:
        raise ProblemError(422, "VALIDATION_FAILED", "Nothing to update")
    for required in ("firstname", "lastname"):
        if required in fields and fields[required] is None:
            raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": required, "message": "cannot be empty"}])
    return with_etag(await svc(request).update_me(me, if_match(version), fields, cid(request)))


@router.post("/me/email", status_code=202, tags=["me"])
async def change_email(body: EmailChangeIn, request: Request, me: Principal = Depends(current_principal)) -> Response:
    await svc(request).request_email_change(me, body.newEmail, body.password, cid(request))
    return Response(status_code=202)


@router.post("/me/password", status_code=204, tags=["me"])
async def change_password(
    body: PasswordChangeIn, request: Request, me: Principal = Depends(current_principal)
) -> Response:
    await svc(request).change_password(me, body.currentPassword, body.newPassword, cid(request))
    return Response(status_code=204)


# ---------------------------------------------------------------- admin accounts


@router.get("/admin/accounts", tags=["admin-accounts"])
async def list_accounts(
    request: Request,
    status: Status | None = None,
    role: Role | None = None,
    organisationId: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cursor: str | None = None,
    limit: Limit = None,
    me: Principal = Depends(require_staff),
) -> dict[str, Any]:
    items, nxt = await svc(request).list_accounts(
        {"status": status, "role": role, "organisationId": organisationId, "q": q}, cursor, limit
    )
    return {"items": items, "nextCursor": nxt}


@router.get("/admin/accounts/{accountId}", tags=["admin-accounts"])
async def get_account(accountId: str, request: Request, me: Principal = Depends(require_staff)) -> JSONResponse:
    return with_etag(await svc(request).get_account(accountId))


@router.post("/admin/accounts/bulk-decision", status_code=207, tags=["admin-accounts"])
async def bulk(body: BulkIn, request: Request, me: Principal = Depends(require_admin)) -> JSONResponse:
    results = await svc(request).bulk_decision(me, [d.model_dump() for d in body.decisions], cid(request))
    return JSONResponse({"results": results}, status_code=207)


@router.post("/admin/accounts/{accountId}/approve", tags=["admin-accounts"])
async def approve(
    accountId: str, body: ApproveIn, request: Request, version: IfMatch = None, me: Principal = Depends(require_admin)
) -> JSONResponse:
    return with_etag(
        await svc(request).approve(me, accountId, if_match(version), body.organisationId, body.role, cid(request))
    )


@router.post("/admin/accounts/{accountId}/deny", tags=["admin-accounts"])
async def deny(
    accountId: str, body: ReasonIn, request: Request, version: IfMatch = None, me: Principal = Depends(require_admin)
) -> JSONResponse:
    return with_etag(await svc(request).deny(me, accountId, if_match(version), body.reason, cid(request)))


@router.post("/admin/accounts/{accountId}/suspend", tags=["admin-accounts"])
async def suspend(
    accountId: str, body: ReasonIn, request: Request, version: IfMatch = None, me: Principal = Depends(require_admin)
) -> JSONResponse:
    return with_etag(await svc(request).suspend(me, accountId, if_match(version), body.reason, cid(request)))


@router.post("/admin/accounts/{accountId}/reactivate", tags=["admin-accounts"])
async def reactivate(
    accountId: str, request: Request, version: IfMatch = None, me: Principal = Depends(require_admin)
) -> JSONResponse:
    return with_etag(await svc(request).reactivate(me, accountId, if_match(version), cid(request)))


@router.put("/admin/accounts/{accountId}/role", tags=["admin-accounts"])
async def change_role(
    accountId: str, body: RoleIn, request: Request, version: IfMatch = None, me: Principal = Depends(require_admin)
) -> JSONResponse:
    return with_etag(await svc(request).change_role(me, accountId, if_match(version), body.role, cid(request)))


# ---------------------------------------------------------------- organisations


@router.get("/organisations", tags=["organisations"])
async def list_orgs(
    request: Request,
    q: Annotated[str | None, Query(max_length=100)] = None,
    emailDomain: str | None = None,
    cursor: str | None = None,
    limit: Limit = None,
    me: Principal = Depends(require_staff),
) -> dict[str, Any]:
    items, nxt = await svc(request).list_orgs(q, emailDomain, cursor, limit)
    return {"items": items, "nextCursor": nxt}


@router.post("/organisations", status_code=201, tags=["organisations"])
async def create_org(body: OrgIn, request: Request, me: Principal = Depends(require_admin)) -> JSONResponse:
    return with_etag(await svc(request).create_org(me, body.model_dump(exclude_none=True), cid(request)), 201)


@router.get("/organisations/{organisationId}", tags=["organisations"])
async def get_org(organisationId: str, request: Request, me: Principal = Depends(current_principal)) -> JSONResponse:
    return with_etag(await svc(request).get_org(me, organisationId))


@router.patch("/organisations/{organisationId}", tags=["organisations"])
async def patch_org(
    organisationId: str, body: OrgIn, request: Request, version: IfMatch = None, me: Principal = Depends(require_admin)
) -> JSONResponse:
    fields = body.model_dump(exclude_unset=True)
    return with_etag(await svc(request).update_org(me, organisationId, if_match(version), fields, cid(request)))


@router.post("/organisations/{organisationId}/merge", tags=["organisations"])
async def merge_org(
    organisationId: str, body: MergeIn, request: Request, me: Principal = Depends(require_admin)
) -> JSONResponse:
    return with_etag(await svc(request).merge_org(me, organisationId, body.targetId, cid(request)))


# ---------------------------------------------------------------- audit


@router.get("/audit", tags=["audit"])
async def audit(
    request: Request,
    entityType: str | None = None,
    entityId: str | None = None,
    actorId: str | None = None,
    action: str | None = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    cursor: str | None = None,
    limit: Limit = None,
    me: Principal = Depends(require_admin),
) -> dict[str, Any]:
    items, nxt = await svc(request).list_audit(
        {"entityType": entityType, "entityId": entityId, "actorId": actorId, "action": action, "from": from_, "to": to},
        cursor,
        limit,
    )
    return {"items": items, "nextCursor": nxt}


# ---------------------------------------------------------------- internal (not routed by nginx)


@router.post("/internal/service-token", tags=["internal"])
async def service_token(body: ServiceTokenIn, request: Request) -> dict[str, Any]:
    token, ttl = await svc(request).service_token(body.service, body.secret)
    return {"token": token, "expiresIn": ttl}


@router.get("/internal/accounts/{accountId}", tags=["internal"])
async def internal_account(
    accountId: str, request: Request, me: Principal = Depends(require_service)
) -> dict[str, Any]:
    return await svc(request).internal_account(accountId)


@router.get("/internal/codes/{codeRef}", tags=["internal"])
async def internal_code(codeRef: str, request: Request, me: Principal = Depends(require_service)) -> dict[str, Any]:
    return await svc(request).claim_code(me, codeRef)
