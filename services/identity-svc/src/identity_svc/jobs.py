"""Scheduled jobs of identity-svc (TAD §4 identity "Scheduled jobs", BSD §8 retention, TR-PRIV-1).

    python -m identity_svc.jobs            # loop: one leader (Redis lock) runs every JOBS_INTERVAL_SECONDS
    python -m identity_svc.jobs --once     # run every job once and exit (ops, tests)

Jobs:
  expire_unverified   PENDING_VERIFICATION older than 24 h -> EXPIRED (PRD A2); their codes are deleted.
  remind_approvals    PENDING_APPROVAL waiting > 48 h -> one `user.approval_pending` event (admins emailed, J-08).
  purge_accounts      REJECTED / EXPIRED for > 90 days -> personal data removed, `user.deleted` published,
                      audit entries of that person anonymised; the emptied document is removed once the
                      relay has published the tombstone (the outbox lives on the document, so deletion is
                      two-phase).
Every job is idempotent and bounded per run (`batch`), so a crash or a second runner is harmless.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from cimh_common.outbox import new_event

from .service import user_ref
from .store import Store, now

log = logging.getLogger("identity.jobs")

SYSTEM_ACTOR = {"id": "system", "name": "System", "role": "service"}
DELETED = "[deleted]"


@dataclass(frozen=True)
class JobSettings:
    unverified_after: timedelta = timedelta(hours=24)
    reminder_after: timedelta = timedelta(hours=48)
    purge_after: timedelta = timedelta(days=90)
    batch: int = 200

    @classmethod
    def from_env(cls) -> JobSettings:
        env = os.environ.get
        return cls(
            unverified_after=timedelta(hours=float(env("UNVERIFIED_EXPIRE_HOURS", "24"))),
            reminder_after=timedelta(hours=float(env("APPROVAL_REMINDER_HOURS", "48"))),
            purge_after=timedelta(days=float(env("PURGE_AFTER_DAYS", "90"))),
        )


def _event(event_type: str, payload: dict[str, Any], cid: str) -> dict[str, Any]:
    return new_event(event_type, payload, correlation_id=cid, actor_id=SYSTEM_ACTOR["id"]).model_dump(mode="python")


class Jobs:
    def __init__(self, store: Store, settings: JobSettings | None = None) -> None:
        self.store = store
        self.s = settings or JobSettings()

    async def run_all(self, at: datetime | None = None) -> dict[str, int]:
        t = at or now()
        return {
            "expired": await self.expire_unverified(t),
            "reminded": await self.remind_approvals(t),
            **await self.purge_accounts(t),
        }

    async def expire_unverified(self, t: datetime) -> int:
        cutoff = t - self.s.unverified_after
        n = 0
        cursor = self.store.accounts.find(
            {"status": "PENDING_VERIFICATION", "createdAt": {"$lt": cutoff}}, {"id": 1}
        ).limit(self.s.batch)
        async for acc in cursor:
            cid = f"job-expire-{acc['id']}"
            # Conditional on the status: a verification landing at the same moment wins.
            res = await self.store.accounts.update_one(
                {"id": acc["id"], "status": "PENDING_VERIFICATION"},
                {
                    "$set": {"status": "EXPIRED", "updatedAt": t},
                    "$inc": {"version": 1},
                    "$push": {
                        "statusHistory": {
                            "$each": [
                                {
                                    "from": "PENDING_VERIFICATION",
                                    "to": "EXPIRED",
                                    "by": SYSTEM_ACTOR,
                                    "at": t,
                                    "reason": "Email not verified within 24 hours",
                                }
                            ],
                            "$slice": -50,
                        }
                    },
                },
            )
            if res.modified_count:
                await self.store.temp.delete_many({"accountId": acc["id"]})
                await self.store.record_audit(
                    actor=SYSTEM_ACTOR,
                    action="account.expired",
                    entity_type="account",
                    entity_id=acc["id"],
                    correlation_id=cid,
                    before="PENDING_VERIFICATION",
                    after="EXPIRED",
                )
                n += 1
        return n

    async def remind_approvals(self, t: datetime) -> int:
        cutoff = t - self.s.reminder_after
        n = 0
        cursor = self.store.accounts.find(
            {
                "status": "PENDING_APPROVAL",
                "approvalReminderAt": {"$exists": False},
                "$or": [
                    {"verifiedAt": {"$lt": cutoff}},
                    {"verifiedAt": {"$exists": False}, "createdAt": {"$lt": cutoff}},
                ],
            }
        ).limit(self.s.batch)
        async for acc in cursor:
            waiting_since = acc.get("verifiedAt") or acc.get("createdAt")
            evt = _event(
                "user.approval_pending",
                {**user_ref(acc), "waitingSince": waiting_since.isoformat() if waiting_since else None},
                f"job-remind-{acc['id']}",
            )
            res = await self.store.accounts.update_one(
                {"id": acc["id"], "status": "PENDING_APPROVAL", "approvalReminderAt": {"$exists": False}},
                {"$set": {"approvalReminderAt": t}, "$push": {"outbox": evt}},
            )
            n += res.modified_count
        return n

    async def purge_accounts(self, t: datetime) -> dict[str, int]:
        cutoff = t - self.s.purge_after
        stripped = 0
        cursor = self.store.accounts.find(
            {"status": {"$in": ["REJECTED", "EXPIRED"]}, "updatedAt": {"$lt": cutoff}, "deletedAt": {"$exists": False}}
        ).limit(self.s.batch)
        async for acc in cursor:
            if await self._strip(acc, t):
                stripped += 1
        # Phase 2: the tombstone was published (outbox empty) -> remove the document.
        res = await self.store.accounts.delete_many({"deletedAt": {"$exists": True}, "outbox.0": {"$exists": False}})
        return {"purged": stripped, "removed": res.deleted_count}

    async def _strip(self, acc: dict[str, Any], t: datetime) -> bool:
        aid = acc["id"]
        cid = f"job-purge-{aid}"
        evt = _event("user.deleted", {"userId": aid}, cid)
        res = await self.store.accounts.update_one(
            {"id": aid, "status": acc["status"], "deletedAt": {"$exists": False}},
            {
                "$set": {
                    "deletedAt": t,
                    "updatedAt": t,
                    # Keeps the unique email index happy and frees the real address for a new sign-up.
                    "email": f"deleted-{aid.lower()}@deleted.invalid",
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
                },
                "$inc": {"version": 1},
                "$push": {"outbox": evt},
            },
        )
        if not res.modified_count:
            return False
        await self.store.temp.delete_many({"accountId": aid})
        # BSD §5.4: audit entries stay; the person's name and IP go.
        await self.store.audit.update_many({"actor.id": aid}, {"$set": {"actor.name": DELETED}, "$unset": {"ip": ""}})
        await self.store.record_audit(
            actor=SYSTEM_ACTOR,
            action="account.deleted",
            entity_type="account",
            entity_id=aid,
            correlation_id=cid,
            before=acc["status"],
            reason="Retention: 90 days after rejection or expiry",
        )
        return True


async def main(once: bool = False) -> None:
    from pymongo import AsyncMongoClient
    from redis.asyncio import from_url

    from cimh_common.locks import RedisLock
    from cimh_common.logging import configure_logging
    from cimh_common.settings import env_secret

    configure_logging("identity-jobs", os.environ.get("LOG_LEVEL", "INFO"))
    db: Any = AsyncMongoClient(env_secret("MONGO_URL"), tz_aware=True)[os.environ.get("MONGO_DB", "inventory")]
    jobs = Jobs(Store(db), JobSettings.from_env())
    if once:
        log.info("jobs done", extra=await jobs.run_all())
        return

    redis = from_url(env_secret("REDIS_URL"))
    interval = float(os.environ.get("JOBS_INTERVAL_SECONDS", "900"))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    lock = RedisLock(redis, "identity:jobs", ttl_ms=int(interval * 1000))
    while not stop.is_set():
        if await lock.acquire():
            try:
                log.info("jobs done", extra=await jobs.run_all())
            except Exception:
                log.exception("jobs failed")
        # Keep the lock for the interval: only one runner per interval, even with several replicas.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    asyncio.run(main(ap.parse_args().once))
