"""FastAPI dependencies for authentication, roles and ownership (API README §3).

Usage:
    @router.get("/requests/{id}")
    async def get_request(id: str, me: Principal = Depends(require_roles("user", "staff", "admin"))):
        req = await repo.get(id)
        ensure_visible(me, owner_id=req.requester_id, org_id=req.org_id, same_org=True)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request

from .auth import Principal, Role, TokenVerifier, check_csrf, extract_token
from .errors import ProblemError, forbidden, not_found, unauthorized


def _verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        raise ProblemError(503, "DEPENDENCY_UNAVAILABLE", "Token verifier not configured")
    return verifier


async def _token_principal(request: Request) -> Principal | None:
    """The verified token's principal, or None without a token. No role or MFA rules: building block only."""
    token, from_cookie = extract_token(request)
    if token is None:
        return None
    principal = await _verifier(request).verify(token)
    if from_cookie:
        check_csrf(request)
    request.state.principal = principal
    return principal


async def optional_principal(request: Request) -> Principal | None:
    """Public endpoints that show more to signed-in callers (e.g. the catalogue's staff view).

    Same rules as every other user endpoint (pen test 2026-11): service tokens are refused, and an admin
    without MFA gets 403 MFA_REQUIRED instead of the staff view. No token: anonymous (None).
    """
    principal = await _token_principal(request)
    if principal is None:
        return None
    if principal.role == "service":
        raise forbidden("Service tokens cannot call user endpoints")
    if principal.is_admin and not principal.mfa:
        raise forbidden("Set up multi-factor sign-in first", code="MFA_REQUIRED")
    return principal


async def authenticated_principal(request: Request) -> Principal:
    """Any valid token, including an admin who has not set up MFA yet.

    Use ONLY on the endpoints needed to finish MFA setup (/auth/mfa/*, GET /me, /auth/logout).
    """
    principal = await _token_principal(request)
    if principal is None:
        raise unauthorized()
    if principal.role == "service":
        # Service tokens are for /internal/* (require_service) only, never user endpoints.
        raise forbidden("Service tokens cannot call user endpoints")
    return principal


async def require_admin_mfa_setup(request: Request) -> Principal:
    """Admin, MFA not required yet: only for /auth/mfa/setup and /auth/mfa/confirm."""
    principal = await authenticated_principal(request)
    if principal.role != "admin":
        raise forbidden("Only admins use multi-factor sign-in")
    return principal


async def current_principal(request: Request) -> Principal:
    """Any valid token. Admin tokens without MFA (TR-AUTH-9) are refused with MFA_REQUIRED."""
    principal = await authenticated_principal(request)
    if principal.is_admin and not principal.mfa:
        raise forbidden("Set up multi-factor sign-in first", code="MFA_REQUIRED")
    return principal


def require_roles(*roles: Role) -> Callable[[Request], Awaitable[Principal]]:
    allowed = frozenset(roles)
    if not allowed:
        raise ValueError("require_roles needs at least one role")

    async def dependency(request: Request) -> Principal:
        principal = await _token_principal(request)
        if principal is None:
            raise unauthorized()
        if principal.role not in allowed:
            raise forbidden(f"Requires role: {', '.join(sorted(allowed))}")
        if principal.is_admin and not principal.mfa:
            raise forbidden("Set up multi-factor sign-in first", code="MFA_REQUIRED")
        return principal

    return dependency


require_staff = require_roles("staff", "admin")
require_admin = require_roles("admin")
require_service = require_roles("service")


def require_services(*names: str) -> Callable[[Request], Awaitable[Principal]]:
    """Internal endpoints: a service token from one of the named callers only (least privilege, pen test 2026-11).

    `require_service` alone admits every service; use this so a compromised service reaches only what it needs.
    """
    allowed = {f"svc:{n}" for n in names}
    base = require_roles("service")

    async def dependency(request: Request) -> Principal:
        principal = await base(request)
        if principal.sub not in allowed:
            raise forbidden("This service may not call this endpoint")
        return principal

    return dependency


async def require_requester(request: Request) -> Principal:
    """Cart and request-submission endpoints: role `user`, not a @cimh.edu.bb account."""
    principal = await require_roles("user")(request)
    if principal.is_cimh:
        raise forbidden("CIMH accounts cannot request items", code="CIMH_CANNOT_REQUEST")
    return principal


def can_see(principal: Principal, *, owner_id: str | None, org_id: str | None = None, same_org: bool = False) -> bool:
    """Staff/admin see everything; users see their own, plus same-org if `same_org`."""
    if principal.is_staff:
        return True
    if owner_id is not None and owner_id == principal.sub:
        return True
    return bool(same_org and org_id and principal.org_id and org_id == principal.org_id)


def ensure_visible(
    principal: Principal, *, owner_id: str | None, org_id: str | None = None, same_org: bool = False
) -> None:
    """Raise 404 (not 403) so callers can't learn that hidden data exists."""
    if not can_see(principal, owner_id=owner_id, org_id=org_id, same_org=same_org):
        raise not_found()


def ensure_can_act(principal: Principal, *, owner_id: str | None, org_id: str | None = None) -> None:
    """Only the requester or an admin may act; same-org users can see but get 403 here."""
    if principal.is_admin or (owner_id is not None and owner_id == principal.sub):
        return
    if can_see(principal, owner_id=owner_id, org_id=org_id, same_org=True):
        raise forbidden("Only the requester or an admin can do this")
    raise not_found()
