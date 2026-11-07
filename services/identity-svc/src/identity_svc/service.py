"""identity-svc business rules (PRD A1-A13, TR-AUTH-1..9, BSD §5.1-5.4).

Every state change is ONE conditional update on the account (expected status + version) that also
pushes the outbox event, so state and event can't diverge (TAD §5).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument

from cimh_common.auth import CIMH_DOMAIN, Principal
from cimh_common.errors import ProblemError, conflict, forbidden, not_found, unauthorized
from cimh_common.ids import new_id, ulid
from cimh_common.outbox import new_event
from cimh_common.paging import page

from . import security as sec
from .config import Settings
from .store import Store, now
from .tokens import IssuedTokens, TokenError, TokenService

log = logging.getLogger(__name__)

STATUS_403 = {
    "PENDING_VERIFICATION": "ACCOUNT_PENDING_VERIFICATION",
    "PENDING_APPROVAL": "ACCOUNT_PENDING_APPROVAL",
    "REJECTED": "ACCOUNT_REJECTED",
    "EXPIRED": "ACCOUNT_REJECTED",
    "SUSPENDED": "ACCOUNT_SUSPENDED",
}
SYSTEM_ACTOR = {"id": "svc:identity", "name": "identity-svc", "role": "service"}


def iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return str(value.astimezone(UTC).isoformat().replace("+00:00", "Z"))
    return str(value)


def user_ref(acc: dict[str, Any]) -> dict[str, Any]:
    return {
        "userId": acc["id"],
        "email": acc["email"],
        "firstname": acc["firstname"],
        "lastname": acc["lastname"],
        "role": acc["role"],
        "status": acc["status"],
        "isCimh": acc.get("isCimh", False),
        "organisationId": acc.get("organisationId"),
    }


def summary(acc: dict[str, Any], org_name: str | None = None) -> dict[str, Any]:
    return {
        "id": acc["id"],
        "firstname": acc["firstname"],
        "lastname": acc["lastname"],
        "email": acc["email"],
        "role": acc["role"],
        "status": acc["status"],
        "isCimh": acc.get("isCimh", False),
        "organisationId": acc.get("organisationId"),
        "organisationName": org_name,
        "organisationText": acc.get("organisationText"),
        "createdAt": iso(acc.get("createdAt")),
    }


def account_view(acc: dict[str, Any], *, staff_view: bool, org_name: str | None = None) -> dict[str, Any]:
    out = summary(acc, org_name)
    out.update(
        version=acc.get("version", 1),
        phone=acc.get("phone"),
        department=acc.get("department"),
        country=acc.get("country"),
        addresses=acc.get("addresses", []),
        image=acc.get("image"),
        defaults=acc.get("defaults"),
        mfaEnabled=bool((acc.get("mfa") or {}).get("enabled")),
        verifiedAt=iso(acc.get("verifiedAt")),
        approvedAt=iso(acc.get("approvedAt")),
    )
    if staff_view:
        out["statusHistory"] = [{**h, "at": iso(h.get("at"))} for h in acc.get("statusHistory", [])]
    return out


def actor_of(p: Principal, name: str = "") -> dict[str, Any]:
    return {"id": p.sub, "name": name or p.email or p.sub, "role": p.role}


def _merge_update(*parts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for part in parts:
        for op, fields in part.items():
            if op == "$push" and "$push" in out:
                out["$push"].update(fields)
            else:
                out.setdefault(op, {}).update(fields)
    return out


class IdentityService:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        tokens: TokenService,
        envelope: sec.Envelope,
        breach_check: sec.BreachCheck,
    ) -> None:
        self.s = settings
        self.store = store
        self.tokens = tokens
        self.env = envelope
        self.breached = breach_check

    # ------------------------------------------------------------------ helpers

    async def _check_new_password(self, password: str) -> None:
        if len(password) < self.s.password_min_length:
            raise ProblemError(
                422,
                "VALIDATION_FAILED",
                errors=[{"field": "password", "message": f"at least {self.s.password_min_length} characters"}],
            )
        if await self.breached(password):
            raise ProblemError(422, "PASSWORD_BREACHED", "This password appears in known data breaches")

    async def _org_name(self, org_id: str | None) -> str | None:
        if not org_id:
            return None
        org = await self.store.organisations.find_one({"id": org_id}, {"name": 1})
        return org["name"] if org else None

    async def _transition(
        self,
        account_id: str,
        *,
        from_status: tuple[str, ...],
        version: int | None,
        set_fields: dict[str, Any],
        event_type: str | None,
        actor: dict[str, Any],
        correlation_id: str,
        reason: str | None = None,
        extra_payload: dict[str, Any] | None = None,
        new_status: str | None = None,
    ) -> dict[str, Any]:
        filt: dict[str, Any] = {"id": account_id, "status": {"$in": list(from_status)}}
        if version is not None:
            filt["version"] = version
        current = await self.store.accounts.find_one({"id": account_id})
        if current is None:
            raise not_found("Account not found")
        update: dict[str, Any] = {"$set": {**set_fields, "updatedAt": now()}, "$inc": {"version": 1}}
        if new_status:
            update["$set"]["status"] = new_status
            update["$push"] = {
                "statusHistory": {
                    "$each": [
                        {"from": current["status"], "to": new_status, "by": actor, "at": now(), "reason": reason}
                    ],
                    "$slice": -50,
                }
            }
        if event_type:
            preview = {**current, **set_fields, **({"status": new_status} if new_status else {})}
            evt = new_event(
                event_type,
                {**user_ref(preview), **(extra_payload or {})},
                correlation_id=correlation_id,
                actor_id=actor["id"],
            )
            update = _merge_update(update, {"$push": {"outbox": evt.model_dump(mode="python")}})
        doc = await self.store.accounts.find_one_and_update(filt, update, return_document=ReturnDocument.AFTER)
        if doc is None:
            if version is not None and current.get("version") != version:
                raise conflict("VERSION_CONFLICT", "The account was changed by someone else; reload and retry")
            raise conflict("ACCOUNT_ILLEGAL_TRANSITION", f"Account is {current['status']}")
        return dict(doc)

    async def _issue_code(self, account: dict[str, Any], kind: str, extra: dict[str, Any] | None = None) -> str:
        """Create/replace the code for (account, kind). Returns the temp id (codeRef)."""
        code = sec.new_code()
        t = now()
        existing = await self.store.temp.find_one({"accountId": account["id"], "kind": kind})
        sent = 0
        window = t
        if existing:
            window = existing.get("windowStart", t)
            if window.tzinfo is None:
                window = window.replace(tzinfo=UTC)
            sent = existing.get("sentCount", 0) if t - window < timedelta(hours=1) else 0
            if t - window >= timedelta(hours=1):
                window = t
            if sent >= self.s.code_max_sends_per_hour:
                raise ProblemError(
                    429, "RATE_LIMITED", "Too many codes requested; try again later", headers={"Retry-After": "3600"}
                )
            await self.store.temp.delete_many({"accountId": account["id"], "kind": kind})
        ref = "TMP" + ulid()
        await self.store.temp.insert_one(
            {
                "id": ref,
                "kind": kind,
                "accountId": account["id"],
                "codeHash": sec.hash_code(code, self.s.code_pepper),
                # Sealed copy for notification-svc to fetch ONCE (GET /internal/codes/{ref}).
                "codeEnc": self.env.seal(code, ref),
                "attempts": 0,
                "sentCount": sent + 1,
                "windowStart": window,
                "createdAt": t,
                "expireAt": t + timedelta(seconds=self.s.code_ttl),
                **(extra or {}),
            }
        )
        return ref

    async def _check_code(self, account_id: str, kind: str, code: str) -> dict[str, Any]:
        doc = await self.store.temp.find_one({"accountId": account_id, "kind": kind})
        if doc is None:
            raise ProblemError(422, "CODE_INVALID", "The code is not valid")
        expire = doc["expireAt"] if doc["expireAt"].tzinfo else doc["expireAt"].replace(tzinfo=UTC)
        if expire < now():
            raise ProblemError(422, "CODE_EXPIRED", "The code has expired; request a new one")
        if doc.get("attempts", 0) >= self.s.code_max_attempts:
            raise ProblemError(422, "CODE_EXPIRED", "Too many attempts; request a new code")
        if not sec.code_matches(code, doc["codeHash"], self.s.code_pepper):
            await self.store.temp.update_one({"id": doc["id"]}, {"$inc": {"attempts": 1}})
            raise ProblemError(422, "CODE_INVALID", "The code is not valid")
        await self.store.temp.delete_one({"id": doc["id"]})
        return dict(doc)

    async def _push_event(
        self, account: dict[str, Any], event_type: str, payload: dict[str, Any], cid: str, actor_id: str | None = None
    ) -> None:
        evt = new_event(event_type, payload, correlation_id=cid, actor_id=actor_id)
        await self.store.accounts.update_one(
            {"id": account["id"]}, {"$push": {"outbox": evt.model_dump(mode="python")}}
        )

    # ------------------------------------------------------------------ registration (A1, A2)

    async def register(self, body: dict[str, Any], cid: str) -> None:
        email = body["email"].lower().strip()
        await self._check_new_password(body["password"])
        is_cimh = email.endswith(CIMH_DOMAIN)
        if not is_cimh and not (body.get("organisationText") or "").strip():
            raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": "organisationText", "message": "required"}])
        existing = await self.store.accounts.find_one({"email": email})
        if existing:
            # Always 202 (no enumeration). Re-send the code if still unverified.
            if existing["status"] == "PENDING_VERIFICATION":
                try:
                    ref = await self._issue_code(existing, "verify_email")
                    await self._push_event(existing, "user.registered", {**user_ref(existing), "codeRef": ref}, cid)
                except ProblemError:
                    pass
            return
        t = now()
        acc = {
            "id": new_id("USR"),
            "email": email,
            "passwordHash": sec.hash_password(body["password"]),
            "firstname": body["firstname"].strip(),
            "lastname": body["lastname"].strip(),
            "phone": body.get("phone"),
            "role": "user",
            "status": "PENDING_VERIFICATION",
            "isCimh": is_cimh,
            "organisationText": (body.get("organisationText") or "").strip() or None,
            "organisationId": None,
            "department": body.get("department"),
            "country": body.get("country"),
            "addresses": [],
            "statusHistory": [{"from": None, "to": "PENDING_VERIFICATION", "by": SYSTEM_ACTOR, "at": t}],
            "failedLogins": {"count": 0, "lockouts": 0},
            "mfa": {"enabled": False},
            "createdAt": t,
            "updatedAt": t,
            "version": 1,
            "outbox": [],
        }
        try:
            await self.store.accounts.insert_one(acc)
        except Exception as exc:  # duplicate email race: behave as if it existed
            if "duplicate" in str(exc).lower():
                return
            raise
        ref = await self._issue_code(acc, "verify_email")
        await self._push_event(acc, "user.registered", {**user_ref(acc), "codeRef": ref}, cid)

    async def resend_verification(self, email: str, cid: str) -> None:
        acc = await self.store.accounts.find_one({"email": email.lower().strip()})
        if acc and acc["status"] == "PENDING_VERIFICATION":
            ref = await self._issue_code(acc, "verify_email")
            await self._push_event(acc, "user.registered", {**user_ref(acc), "codeRef": ref}, cid)

    async def verify(self, email: str, code: str, cid: str) -> str:
        email = email.lower().strip()
        acc = await self.store.accounts.find_one({"email": email})
        if acc is None:
            # Maybe a pending email change to this address.
            pending = await self.store.temp.find_one({"kind": "change_email", "newEmail": email})
            if pending is None:
                raise ProblemError(422, "CODE_INVALID", "The code is not valid")
            return await self._apply_email_change(pending["accountId"], email, code, cid)
        if acc["status"] != "PENDING_VERIFICATION":
            raise ProblemError(422, "CODE_INVALID", "The code is not valid")
        await self._check_code(acc["id"], "verify_email", code)
        if acc.get("isCimh"):
            doc = await self._transition(
                acc["id"],
                from_status=("PENDING_VERIFICATION",),
                version=None,
                set_fields={"verifiedAt": now(), "approvedAt": now(), "approvedBy": SYSTEM_ACTOR},
                event_type="user.approved",
                actor=SYSTEM_ACTOR,
                correlation_id=cid,
                extra_payload={"auto": True},
                new_status="ACTIVE",
            )
        else:
            doc = await self._transition(
                acc["id"],
                from_status=("PENDING_VERIFICATION",),
                version=None,
                set_fields={"verifiedAt": now()},
                event_type="user.verified",
                actor=SYSTEM_ACTOR,
                correlation_id=cid,
                new_status="PENDING_APPROVAL",
            )
        return str(doc["status"])

    # ------------------------------------------------------------------ login (A6, TR-AUTH-1/4/6/9)

    async def login(
        self, email: str, password: str, totp: str | None, ip: str | None, cid: str
    ) -> tuple[dict[str, Any], IssuedTokens]:
        email = email.lower().strip()
        acc = await self.store.accounts.find_one({"email": email})
        t = now()
        if acc:
            locked = (acc.get("failedLogins") or {}).get("lockedUntil")
            if locked is not None:
                locked = locked if locked.tzinfo else locked.replace(tzinfo=UTC)
                if locked > t:
                    raise ProblemError(
                        403,
                        "ACCOUNT_LOCKED",
                        "Too many failed attempts; try again later",
                        headers={"Retry-After": str(int((locked - t).total_seconds()) + 1)},
                    )
        ok = False
        if acc and acc.get("passwordHash"):
            ok = sec.verify_password(acc["passwordHash"], password)
        elif acc and acc.get("legacyPasswordHash"):
            ok = sec.verify_legacy_werkzeug(acc["legacyPasswordHash"], password)
            if ok:  # upgrade to Argon2id at first login (BSD §5.1)
                await self.store.accounts.update_one(
                    {"id": acc["id"]},
                    {"$set": {"passwordHash": sec.hash_password(password)}, "$unset": {"legacyPasswordHash": ""}},
                )
        else:
            sec.verify_password(None, password)  # same cost for unknown emails
        if not acc or not ok:
            if acc:
                await self._register_failure(acc, ip, cid)
            raise unauthorized("Invalid email or password", code="INVALID_CREDENTIALS")

        if acc["status"] != "ACTIVE":
            raise forbidden("Account is not active", code=STATUS_403.get(acc["status"], "ACCOUNT_SUSPENDED"))

        mfa_passed = False
        if acc["role"] == "admin" and (acc.get("mfa") or {}).get("enabled"):
            if not totp:
                raise forbidden("Enter the code from your authenticator app", code="MFA_REQUIRED")
            secret = self.env.open(acc["mfa"]["totpSecretEnc"], acc["id"])
            step = sec.totp_verify(secret, totp)
            if step is None or not await self.tokens.accept_totp_step(acc["id"], step):
                await self._register_failure(acc, ip, cid)
                raise unauthorized("Invalid authentication code", code="MFA_INVALID")
            mfa_passed = True

        if acc.get("passwordHash") and sec.needs_rehash(acc["passwordHash"]):
            await self.store.accounts.update_one(
                {"id": acc["id"]}, {"$set": {"passwordHash": sec.hash_password(password)}}
            )
        await self.store.accounts.update_one(
            {"id": acc["id"]},
            {"$set": {"failedLogins.count": 0, "failedLogins.lockedUntil": None, "lastLoginAt": t}},
        )
        if acc["role"] == "admin":
            last_ip = acc.get("lastAdminIp")
            await self.store.record_audit(
                actor={"id": acc["id"], "name": acc["email"], "role": "admin"},
                action="auth.admin_login",
                entity_type="account",
                entity_id=acc["id"],
                correlation_id=cid,
                ip=ip,
                after={"newIp": bool(ip and last_ip and ip != last_ip)},
            )
            await self.store.accounts.update_one({"id": acc["id"]}, {"$set": {"lastAdminIp": ip}})
        tokens = await self.tokens.start_session(acc, mfa=mfa_passed or acc["role"] != "admin")
        return acc, tokens

    async def _register_failure(self, acc: dict[str, Any], ip: str | None, cid: str) -> None:
        fl = acc.get("failedLogins") or {}
        count = int(fl.get("count", 0)) + 1
        update: dict[str, Any] = {"failedLogins.count": count}
        if count >= self.s.lockout_threshold:
            lockouts = int(fl.get("lockouts", 0))
            seconds = self.s.lockout_base_seconds * (2 ** min(lockouts, 6))  # 15 min, 30, 60 … max ~16 h
            update.update(
                {
                    "failedLogins.count": 0,
                    "failedLogins.lockouts": lockouts + 1,
                    "failedLogins.lockedUntil": now() + timedelta(seconds=seconds),
                }
            )
            await self.store.record_audit(
                actor=SYSTEM_ACTOR,
                action="auth.locked",
                entity_type="account",
                entity_id=acc["id"],
                correlation_id=cid,
                ip=ip,
                after={"seconds": seconds, "role": acc["role"]},
            )
        await self.store.accounts.update_one({"id": acc["id"]}, {"$set": update})

    async def refresh(self, refresh_token: str) -> tuple[dict[str, Any], IssuedTokens]:
        async def load(sub: str) -> dict[str, Any] | None:
            doc = await self.store.accounts.find_one({"id": sub})
            return dict(doc) if doc else None

        try:
            tokens, acc = await self.tokens.refresh(refresh_token, load)
        except TokenError as exc:
            code = "TOKEN_REUSE" if exc.code == "TOKEN_REUSE" else "TOKEN_INVALID"
            if code == "TOKEN_REUSE":
                log.warning("refresh token reuse detected")
            raise unauthorized("Session is no longer valid; log in again", code=code) from exc
        return acc, tokens

    async def logout(self, p: Principal) -> None:
        if p.session_id:
            await self.tokens.revoke_session(p.session_id)
            await self.tokens.redis.srem(f"user_sess:{p.sub}", p.session_id)

    # ------------------------------------------------------------------ passwords (A8)

    async def forgot_password(self, email: str, cid: str) -> None:
        acc = await self.store.accounts.find_one({"email": email.lower().strip()})
        if acc and acc["status"] in ("ACTIVE", "SUSPENDED", "PENDING_APPROVAL"):
            try:
                ref = await self._issue_code(acc, "reset_password")
            except ProblemError:
                return  # rate limited; still 202
            await self._push_event(acc, "user.password_reset_requested", {**user_ref(acc), "codeRef": ref}, cid)

    async def reset_password(self, email: str, code: str, new_password: str, cid: str) -> None:
        acc = await self.store.accounts.find_one({"email": email.lower().strip()})
        if acc is None:
            raise ProblemError(422, "CODE_INVALID", "The code is not valid")
        await self._check_code(acc["id"], "reset_password", code)
        await self._check_new_password(new_password)
        await self.store.accounts.update_one(
            {"id": acc["id"]},
            {
                "$set": {
                    "passwordHash": sec.hash_password(new_password),
                    "failedLogins": {"count": 0, "lockouts": 0},
                    "updatedAt": now(),
                },
                "$unset": {"legacyPasswordHash": ""},
                "$inc": {"version": 1},
            },
        )
        await self.tokens.revoke_all(acc["id"])
        await self.store.record_audit(
            actor=SYSTEM_ACTOR,
            action="auth.password_reset",
            entity_type="account",
            entity_id=acc["id"],
            correlation_id=cid,
        )

    async def change_password(self, p: Principal, current: str, new: str, cid: str) -> None:
        acc = await self._me(p)
        if not sec.verify_password(acc.get("passwordHash"), current):
            raise unauthorized("Current password is wrong", code="INVALID_CREDENTIALS")
        await self._check_new_password(new)
        await self.store.accounts.update_one(
            {"id": acc["id"]},
            {"$set": {"passwordHash": sec.hash_password(new), "updatedAt": now()}, "$inc": {"version": 1}},
        )
        await self.tokens.revoke_all(acc["id"], except_sid=p.session_id)
        await self.store.record_audit(
            actor=actor_of(p),
            action="auth.password_changed",
            entity_type="account",
            entity_id=acc["id"],
            correlation_id=cid,
        )

    async def request_email_change(self, p: Principal, new_email: str, password: str, cid: str) -> None:
        acc = await self._me(p)
        if not sec.verify_password(acc.get("passwordHash"), password):
            raise unauthorized("Password is wrong", code="INVALID_CREDENTIALS")
        new_email = new_email.lower().strip()
        if await self.store.accounts.find_one({"email": new_email}):
            return  # 202 anyway; don't reveal that the address is taken
        if acc.get("isCimh") != new_email.endswith(CIMH_DOMAIN):
            raise ProblemError(422, "VALIDATION_FAILED", "Moving between CIMH and non-CIMH addresses needs an admin")
        ref = await self._issue_code(acc, "change_email", {"newEmail": new_email})
        await self._push_event(
            acc, "user.email_change_requested", {**user_ref(acc), "newEmail": new_email, "codeRef": ref}, cid, p.sub
        )

    async def _apply_email_change(self, account_id: str, new_email: str, code: str, cid: str) -> str:
        await self._check_code(account_id, "change_email", code)
        acc = await self.store.accounts.find_one({"id": account_id})
        if acc is None:
            raise ProblemError(422, "CODE_INVALID", "The code is not valid")
        doc = await self.store.accounts.find_one_and_update(
            {"id": account_id},
            _merge_update(
                {"$set": {"email": new_email, "updatedAt": now()}, "$inc": {"version": 1}},
                {
                    "$push": {
                        "outbox": new_event(
                            "user.profile_updated",
                            {**user_ref({**acc, "email": new_email})},
                            correlation_id=cid,
                            actor_id=account_id,
                        ).model_dump(mode="python")
                    }
                },
            ),
            return_document=ReturnDocument.AFTER,
        )
        await self.tokens.revoke_all(account_id)  # tokens carry the old email
        return str(doc["status"])

    # ------------------------------------------------------------------ MFA (TR-AUTH-9)

    async def mfa_setup(self, p: Principal) -> str:
        if p.role != "admin":
            raise forbidden("Only admins use multi-factor sign-in")
        acc = await self._me(p)
        if (acc.get("mfa") or {}).get("enabled"):
            raise conflict("MFA_ALREADY_ENABLED", "Multi-factor sign-in is already on")
        secret = sec.new_totp_secret()
        await self.store.accounts.update_one(
            {"id": acc["id"]}, {"$set": {"mfa.pendingSecretEnc": self.env.seal(secret, acc["id"])}}
        )
        return sec.otpauth_uri(secret, acc["email"])

    async def mfa_confirm(self, p: Principal, totp: str, cid: str) -> None:
        acc = await self._me(p)
        pending = (acc.get("mfa") or {}).get("pendingSecretEnc")
        if not pending:
            raise ProblemError(422, "VALIDATION_FAILED", "Start setup first")
        secret = self.env.open(pending, acc["id"])
        step = sec.totp_verify(secret, totp)
        if step is None or not await self.tokens.accept_totp_step(acc["id"], step):
            raise ProblemError(422, "CODE_INVALID", "The code is not valid")
        await self.store.accounts.update_one(
            {"id": acc["id"]},
            {"$set": {"mfa": {"enabled": True, "totpSecretEnc": pending}, "updatedAt": now()}, "$inc": {"version": 1}},
        )
        if p.session_id:
            await self.tokens.mark_session_mfa(p.session_id)
        await self.store.record_audit(
            actor=actor_of(p), action="auth.mfa_enabled", entity_type="account", entity_id=acc["id"], correlation_id=cid
        )

    # ------------------------------------------------------------------ profile (A12)

    async def _me(self, p: Principal) -> dict[str, Any]:
        acc = await self.store.accounts.find_one({"id": p.sub})
        if acc is None:
            raise unauthorized()
        return dict(acc)

    async def me(self, p: Principal) -> dict[str, Any]:
        acc = await self._me(p)
        return account_view(acc, staff_view=False, org_name=await self._org_name(acc.get("organisationId")))

    async def update_me(self, p: Principal, version: int, fields: dict[str, Any], cid: str) -> dict[str, Any]:
        acc = await self._me(p)
        doc = await self._transition(
            acc["id"],
            from_status=("ACTIVE", "PENDING_APPROVAL"),
            version=version,
            set_fields=fields,
            event_type="user.profile_updated",
            actor=actor_of(p),
            correlation_id=cid,
        )
        return account_view(doc, staff_view=False, org_name=await self._org_name(doc.get("organisationId")))

    # ------------------------------------------------------------------ admin: accounts (A3-A5, A7, A10)

    async def list_accounts(
        self, filters: dict[str, Any], cursor: str | None, limit: int | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        q: dict[str, Any] = {k: v for k, v in filters.items() if v and k in ("status", "role", "organisationId")}
        q["deletedAt"] = {"$exists": False}  # purged accounts wait only for their tombstone to be published
        text = filters.get("q")
        if text:
            import re

            rx = {"$regex": "^" + re.escape(text.strip()), "$options": "i"}
            q["$or"] = [{"email": rx}, {"firstname": rx}, {"lastname": rx}]
        docs, nxt = await page(self.store.accounts, q, sort_field="createdAt", cursor=cursor, limit=limit)
        names: dict[str, str | None] = {}
        out = []
        for d in docs:
            oid = d.get("organisationId")
            if oid and oid not in names:
                names[oid] = await self._org_name(oid)
            out.append(summary(d, names.get(oid) if oid else None))
        return out, nxt

    async def get_account(self, account_id: str) -> dict[str, Any]:
        acc = await self.store.accounts.find_one({"id": account_id})
        if acc is None:
            raise not_found("Account not found")
        return account_view(acc, staff_view=True, org_name=await self._org_name(acc.get("organisationId")))

    async def _active_org(self, org_id: str) -> dict[str, Any]:
        org = await self.store.organisations.find_one({"id": org_id})
        if org is None or not org.get("active", True) or org.get("mergedInto"):
            raise ProblemError(
                422,
                "VALIDATION_FAILED",
                errors=[{"field": "organisationId", "message": "unknown or inactive organisation"}],
            )
        return dict(org)

    async def approve(
        self, p: Principal, account_id: str, version: int, org_id: str, role: str | None, cid: str
    ) -> dict[str, Any]:
        org = await self._active_org(org_id)
        fields: dict[str, Any] = {"organisationId": org["id"], "approvedAt": now(), "approvedBy": actor_of(p)}
        if role:
            fields["role"] = role
        doc = await self._transition(
            account_id,
            from_status=("PENDING_APPROVAL",),
            version=version,
            set_fields=fields,
            event_type="user.approved",
            actor=actor_of(p),
            correlation_id=cid,
            extra_payload={"auto": False},
            new_status="ACTIVE",
        )
        await self.store.record_audit(
            actor=actor_of(p),
            action="account.approved",
            entity_type="account",
            entity_id=account_id,
            correlation_id=cid,
            after={"organisationId": org["id"], "role": doc["role"]},
        )
        return account_view(doc, staff_view=True, org_name=org["name"])

    async def deny(self, p: Principal, account_id: str, version: int, reason: str, cid: str) -> dict[str, Any]:
        doc = await self._transition(
            account_id,
            from_status=("PENDING_APPROVAL",),
            version=version,
            set_fields={"rejection": {"by": actor_of(p), "at": now(), "reason": reason}},
            event_type="user.rejected",
            actor=actor_of(p),
            correlation_id=cid,
            reason=reason,
            extra_payload={"reason": reason},
            new_status="REJECTED",
        )
        await self.store.record_audit(
            actor=actor_of(p),
            action="account.rejected",
            entity_type="account",
            entity_id=account_id,
            correlation_id=cid,
            reason=reason,
        )
        return account_view(doc, staff_view=True)

    async def suspend(self, p: Principal, account_id: str, version: int, reason: str, cid: str) -> dict[str, Any]:
        if account_id == p.sub:
            raise conflict("ACCOUNT_ILLEGAL_TRANSITION", "You cannot suspend yourself")
        target = await self.store.accounts.find_one({"id": account_id})
        if target and target["role"] == "admin":
            await self._ensure_not_last_admin(account_id)
        doc = await self._transition(
            account_id,
            from_status=("ACTIVE",),
            version=version,
            set_fields={},
            event_type="user.suspended",
            actor=actor_of(p),
            correlation_id=cid,
            reason=reason,
            new_status="SUSPENDED",
        )
        await self.tokens.revoke_all(account_id)
        await self.store.record_audit(
            actor=actor_of(p),
            action="account.suspended",
            entity_type="account",
            entity_id=account_id,
            correlation_id=cid,
            reason=reason,
        )
        return account_view(doc, staff_view=True, org_name=await self._org_name(doc.get("organisationId")))

    async def reactivate(self, p: Principal, account_id: str, version: int, cid: str) -> dict[str, Any]:
        doc = await self._transition(
            account_id,
            from_status=("SUSPENDED",),
            version=version,
            set_fields={},
            event_type="user.reactivated",
            actor=actor_of(p),
            correlation_id=cid,
            new_status="ACTIVE",
        )
        await self.store.record_audit(
            actor=actor_of(p),
            action="account.reactivated",
            entity_type="account",
            entity_id=account_id,
            correlation_id=cid,
        )
        return account_view(doc, staff_view=True, org_name=await self._org_name(doc.get("organisationId")))

    async def _ensure_not_last_admin(self, account_id: str) -> None:
        others = await self.store.accounts.count_documents(
            {"role": "admin", "status": "ACTIVE", "id": {"$ne": account_id}}
        )
        if others == 0:
            raise conflict("LAST_ADMIN", "At least one active admin must remain")

    async def change_role(self, p: Principal, account_id: str, version: int, role: str, cid: str) -> dict[str, Any]:
        target = await self.store.accounts.find_one({"id": account_id})
        if target is None:
            raise not_found("Account not found")
        if target["role"] == role:
            return account_view(target, staff_view=True, org_name=await self._org_name(target.get("organisationId")))
        if target["role"] == "admin":
            await self._ensure_not_last_admin(account_id)
        doc = await self._transition(
            account_id,
            from_status=("ACTIVE", "SUSPENDED", "PENDING_APPROVAL"),
            version=version,
            set_fields={"role": role},
            event_type="user.role_changed",
            actor=actor_of(p),
            correlation_id=cid,
            extra_payload={"previousRole": target["role"]},
        )
        await self.tokens.revoke_all(account_id)  # tokens carry the old role
        await self.store.record_audit(
            actor=actor_of(p),
            action="role.changed",
            entity_type="account",
            entity_id=account_id,
            correlation_id=cid,
            before={"role": target["role"]},
            after={"role": role},
        )
        return account_view(doc, staff_view=True, org_name=await self._org_name(doc.get("organisationId")))

    async def bulk_decision(self, p: Principal, decisions: list[dict[str, Any]], cid: str) -> list[dict[str, Any]]:
        results = []
        for d in decisions:
            try:
                if d["decision"] == "approve":
                    if not d.get("organisationId"):
                        raise ProblemError(
                            422,
                            "VALIDATION_FAILED",
                            errors=[{"field": "organisationId", "message": "required to approve"}],
                        )
                    await self.approve(p, d["accountId"], d["version"], d["organisationId"], d.get("role"), cid)
                else:
                    reason = (d.get("reason") or "").strip()
                    if len(reason) < 3:
                        raise ProblemError(
                            422, "VALIDATION_FAILED", errors=[{"field": "reason", "message": "required to deny"}]
                        )
                    await self.deny(p, d["accountId"], d["version"], reason, cid)
                results.append({"accountId": d["accountId"], "ok": True})
            except ProblemError as e:
                err = {
                    "type": f"https://errors.cimh.edu.bb/{e.type_path}",
                    "title": e.title,
                    "status": e.status,
                    "traceId": cid,
                }
                if e.code:
                    err["code"] = e.code
                if e.detail:
                    err["detail"] = e.detail
                results.append({"accountId": d["accountId"], "ok": False, "error": err})
        return results

    # ------------------------------------------------------------------ organisations (A11)

    @staticmethod
    def _org_view(org: dict[str, Any], members: int | None = None) -> dict[str, Any]:
        out = {
            k: org.get(k)
            for k in ("id", "name", "country", "type", "emailDomains", "aliases", "active", "mergedInto", "version")
        }
        out["emailDomains"] = out["emailDomains"] or []
        out["aliases"] = out["aliases"] or []
        out["createdAt"] = iso(org.get("createdAt"))
        if members is not None:
            out["memberCount"] = members
        return {k: v for k, v in out.items() if v is not None or k == "mergedInto"}

    async def list_orgs(
        self, q: str | None, domain: str | None, cursor: str | None, limit: int | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        import re

        filt: dict[str, Any] = {}
        if q:
            rx = {"$regex": re.escape(q.strip()), "$options": "i"}
            filt["$or"] = [{"name": rx}, {"aliases": rx}]
        if domain:
            filt["emailDomains"] = domain.lower().lstrip("@")
        docs, nxt = await page(self.store.organisations, filt, sort_field="nameKey", cursor=cursor, limit=limit)
        return [self._org_view(d) for d in docs], nxt

    async def get_org(self, p: Principal, org_id: str) -> dict[str, Any]:
        if not p.is_staff and p.org_id != org_id:
            raise not_found("Organisation not found")
        org = await self.store.organisations.find_one({"id": org_id})
        if org is None:
            raise not_found("Organisation not found")
        members = await self.store.accounts.count_documents({"organisationId": org_id}) if p.is_staff else None
        return self._org_view(org, members)

    async def create_org(self, p: Principal, body: dict[str, Any], cid: str) -> dict[str, Any]:
        key = body["name"].strip().lower()
        if await self.store.organisations.find_one({"nameKey": key}):
            raise conflict("DUPLICATE", "An organisation with this name exists")
        t = now()
        org = {
            "id": new_id("ORG"),
            "name": body["name"].strip(),
            "nameKey": key,
            "country": body["country"],
            "type": body.get("type"),
            "emailDomains": [d.lower().lstrip("@") for d in body.get("emailDomains") or []],
            "aliases": body.get("aliases") or [],
            "active": body.get("active", True),
            "mergedInto": None,
            "createdBy": actor_of(p),
            "createdAt": t,
            "updatedAt": t,
            "version": 1,
        }
        await self.store.organisations.insert_one(org)
        await self.store.record_audit(
            actor=actor_of(p),
            action="organisation.created",
            entity_type="organisation",
            entity_id=org["id"],
            correlation_id=cid,
            after={"name": org["name"]},
        )
        return self._org_view(org, 0)

    async def update_org(
        self, p: Principal, org_id: str, version: int, body: dict[str, Any], cid: str
    ) -> dict[str, Any]:
        fields = dict(body)
        if "name" in fields:
            fields["name"] = fields["name"].strip()
            fields["nameKey"] = fields["name"].lower()
            dup = await self.store.organisations.find_one({"nameKey": fields["nameKey"], "id": {"$ne": org_id}})
            if dup:
                raise conflict("DUPLICATE", "An organisation with this name exists")
        if "emailDomains" in fields:
            fields["emailDomains"] = [d.lower().lstrip("@") for d in fields["emailDomains"]]
        doc = await self.store.organisations.find_one_and_update(
            {"id": org_id, "version": version},
            {"$set": {**fields, "updatedAt": now()}, "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            if await self.store.organisations.find_one({"id": org_id}) is None:
                raise not_found("Organisation not found")
            raise conflict("VERSION_CONFLICT", "The organisation was changed by someone else")
        await self.store.record_audit(
            actor=actor_of(p),
            action="organisation.updated",
            entity_type="organisation",
            entity_id=org_id,
            correlation_id=cid,
            after=body,
        )
        return self._org_view(doc)

    async def merge_org(self, p: Principal, source_id: str, target_id: str, cid: str) -> dict[str, Any]:
        if source_id == target_id:
            raise conflict("ORG_MERGE_INVALID", "Cannot merge an organisation into itself")
        source = await self.store.organisations.find_one({"id": source_id})
        if source is None:
            raise not_found("Organisation not found")
        if source.get("mergedInto"):
            raise conflict("ORG_MERGE_INVALID", "Already merged")
        target = await self._active_org(target_id)
        moved = await self.store.accounts.update_many(
            {"organisationId": source_id}, {"$set": {"organisationId": target_id}, "$inc": {"version": 1}}
        )
        await self.store.organisations.update_one(
            {"id": source_id},
            {"$set": {"mergedInto": target_id, "active": False, "updatedAt": now()}, "$inc": {"version": 1}},
        )
        doc = await self.store.organisations.find_one_and_update(
            {"id": target_id},
            {
                "$addToSet": {
                    "aliases": {"$each": [source["name"], *(source.get("aliases") or [])]},
                    "emailDomains": {"$each": source.get("emailDomains") or []},
                },
                "$set": {"updatedAt": now()},
                "$inc": {"version": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        await self.store.record_audit(
            actor=actor_of(p),
            action="organisation.merged",
            entity_type="organisation",
            entity_id=source_id,
            correlation_id=cid,
            after={"mergedInto": target_id, "accountsMoved": moved.modified_count},
        )
        members = await self.store.accounts.count_documents({"organisationId": target_id})
        return self._org_view(doc or target, members)

    # ------------------------------------------------------------------ audit (A13)

    async def list_audit(
        self, filters: dict[str, Any], cursor: str | None, limit: int | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        q: dict[str, Any] = {}
        if filters.get("entityType"):
            q["entity.type"] = filters["entityType"]
        if filters.get("entityId"):
            q["entity.id"] = filters["entityId"]
        if filters.get("actorId"):
            q["actor.id"] = filters["actorId"]
        if filters.get("action"):
            q["action"] = filters["action"]
        rng: dict[str, Any] = {}
        if filters.get("from"):
            rng["$gte"] = filters["from"]
        if filters.get("to"):
            rng["$lte"] = filters["to"]
        if rng:
            q["at"] = rng
        docs, nxt = await page(self.store.audit, q, sort_field="at", cursor=cursor, limit=limit, descending=True)
        out = []
        for d in docs:
            item = {k: d.get(k) for k in ("id", "actor", "action", "entity", "reason", "correlationId")}
            item["at"] = iso(d["at"])
            if "from" in d:
                item["from"] = d["from"]
            if "to" in d:
                item["to"] = d["to"]
            out.append(item)
        return out, nxt

    # ------------------------------------------------------------------ internal

    async def service_token(self, service: str, secret: str) -> tuple[str, int]:
        import hmac as _hmac

        expected = self.s.service_secrets.get(service)
        if not expected or not _hmac.compare_digest(expected, secret):
            raise unauthorized("Invalid service credentials")
        return self.tokens.service_token(service)

    async def internal_account(self, account_id: str) -> dict[str, Any]:
        acc = await self.store.accounts.find_one({"id": account_id})
        if acc is None:
            raise not_found("Account not found")
        return summary(acc, await self._org_name(acc.get("organisationId")))

    async def claim_code(self, p: Principal, ref: str) -> dict[str, Any]:
        """notification-svc fetches a code ONCE to email it; the sealed copy is then removed."""
        if p.sub != "svc:notification":
            raise forbidden("Only notification-svc may read codes")
        doc = await self.store.temp.find_one_and_update(
            {"id": ref, "codeEnc": {"$exists": True}}, {"$unset": {"codeEnc": ""}}
        )
        if doc is None:
            raise not_found("Code not found or already delivered")
        expire = doc["expireAt"] if doc["expireAt"].tzinfo else doc["expireAt"].replace(tzinfo=UTC)
        if expire < now():
            raise not_found("Code expired")
        return {
            "code": self.env.open(doc["codeEnc"], ref),
            "kind": doc["kind"],
            "accountId": doc["accountId"],
            "email": doc.get("newEmail"),
            "expiresAt": iso(expire),
        }
