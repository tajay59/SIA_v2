"""Personal-data rights (TR-PRIV-1, BSD §8, SECURITY §10): export and erasure.

Erasure is shared by the 90-day retention purge (jobs.py) and an admin erasure on request. Both strip the
document in one conditional update that also queues `user.deleted`; the emptied document is removed by the
jobs once the relay has published the tombstone (the outbox lives on the document).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from cimh_common.outbox import new_event

from .store import Store

DELETED = "[deleted]"
AUDIT_EXPORT_LIMIT = 1000


def deleted_email(account_id: str) -> str:
    # Keeps the unique email index happy and frees the real address for a new sign-up.
    return f"deleted-{account_id.lower()}@deleted.invalid"


async def strip_account(
    store: Store,
    acc: dict[str, Any],
    t: datetime,
    *,
    actor: dict[str, Any],
    action: str,
    reason: str,
    correlation_id: str,
    version: int | None = None,
) -> bool:
    """Remove the person's data from `acc`. False if it changed meanwhile (status/version) or is already gone."""
    aid = acc["id"]
    evt = new_event("user.deleted", {"userId": aid}, correlation_id=correlation_id, actor_id=actor["id"])
    filt: dict[str, Any] = {"id": aid, "status": acc["status"], "deletedAt": {"$exists": False}}
    if version is not None:
        filt["version"] = version
    res = await store.accounts.update_one(
        filt,
        {
            "$set": {
                "deletedAt": t,
                "updatedAt": t,
                "email": deleted_email(aid),
                "firstname": DELETED,
                "lastname": DELETED,
                "phone": None,
                "department": None,
                "organisationText": None,
                "addresses": [],
                "image": None,
                "statusHistory": [],
            },
            "$unset": {
                "passwordHash": "",
                "legacyPasswordHash": "",
                "mfa": "",
                "totpSecretEnc": "",
                "failedLogins": "",
                "lockouts": "",
                "lockedUntil": "",
                "erasureRequestedAt": "",
                "defaults": "",
            },
            "$inc": {"version": 1},
            "$push": {"outbox": evt.model_dump(mode="python")},
        },
    )
    if not res.modified_count:
        return False
    await store.temp.delete_many({"accountId": aid})
    # BSD §5.4: audit entries stay; the person's name and IP go. This is the only update svc_identity makes
    # on auditlog.
    await store.audit.update_many({"actor.id": aid}, {"$set": {"actor.name": DELETED}, "$unset": {"ip": ""}})
    await store.record_audit(
        actor=actor,
        action=action,
        entity_type="account",
        entity_id=aid,
        correlation_id=correlation_id,
        before=acc["status"],
        reason=reason,
    )
    return True


def _by(actor: dict[str, Any] | None, subject_id: str, *, for_admin: bool) -> str:
    actor = actor or {}
    if actor.get("id") == subject_id:
        return "you" if not for_admin else f"{actor.get('name', '')} (account holder)".strip()
    role = actor.get("role", "service")
    if for_admin:
        return f"{actor.get('name') or actor.get('id', '')} ({role})"
    return "system" if role == "service" else f"CIMH {role}"


def _status_by(actor: dict[str, Any] | None, subject_id: str, *, for_admin: bool) -> dict[str, Any]:
    actor = actor or {}
    if for_admin or actor.get("id") == subject_id:
        return actor
    role = actor.get("role", "service")
    return {"id": "", "name": _by(actor, subject_id, for_admin=False), "role": role}


async def audit_trail(store: Store, subject_id: str, *, for_admin: bool) -> list[dict[str, Any]]:
    from .service import iso

    cursor = (
        store.audit.find({"$or": [{"entity.id": subject_id}, {"actor.id": subject_id}]}, {"_id": 0})
        .sort("at", -1)
        .limit(AUDIT_EXPORT_LIMIT)
    )
    out = []
    async for d in cursor:
        item: dict[str, Any] = {
            "at": iso(d["at"]),
            "action": d["action"],
            "by": _by(d.get("actor"), subject_id, for_admin=for_admin),
            "reason": d.get("reason"),
        }
        for k in ("from", "to"):
            if k in d:
                item[k] = d[k]
        out.append(item)
    return out


def export_account_view(view: dict[str, Any], subject_id: str, *, for_admin: bool) -> dict[str, Any]:
    """Account view with staff identities hidden in the status history for a self-service export."""
    out = dict(view)
    out["statusHistory"] = [
        {**h, "by": _status_by(h.get("by"), subject_id, for_admin=for_admin)} for h in view.get("statusHistory", [])
    ]
    return out
