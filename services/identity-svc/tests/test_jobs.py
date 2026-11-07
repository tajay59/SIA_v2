"""Scheduled jobs (TAD §4, BSD §8, PRD A2, J-08, TR-PRIV-1) and the audit.events consumer."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from cimh_common.outbox import new_event
from cimh_common.testing import AsyncMongoMock
from identity_svc.audit_consumer import entry_from_event, make_handler
from identity_svc.jobs import DELETED, Jobs
from identity_svc.store import Store

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def account(aid: str, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": aid,
        "email": f"{aid.lower()}@example.org",
        "firstname": "Ann",
        "lastname": "Smith",
        "role": "user",
        "status": status,
        "isCimh": False,
        "version": 1,
        "phone": "+1 246 555 0100",
        "passwordHash": "argon2...",
        "addresses": [{"line1": "1 Main St"}],
        "statusHistory": [{"to": status, "by": {"id": "x", "name": "Admin", "role": "admin"}, "at": NOW}],
        "outbox": [],
        "createdAt": NOW - timedelta(days=1),
        "updatedAt": NOW - timedelta(days=1),
        **extra,
    }


@pytest.fixture
def store() -> Store:
    return Store(AsyncMongoMock())


def doc(store: Store, aid: str) -> dict[str, Any] | None:
    return run(store.accounts.find_one({"id": aid}))  # type: ignore[no-any-return]


def test_unverified_accounts_expire_after_24_hours(store: Store) -> None:
    run(store.accounts.insert_one(account("USR_OLD", "PENDING_VERIFICATION", createdAt=NOW - timedelta(hours=25))))
    run(store.accounts.insert_one(account("USR_NEW", "PENDING_VERIFICATION", createdAt=NOW - timedelta(hours=23))))
    run(store.temp.insert_one({"id": "TMP1", "accountId": "USR_OLD", "kind": "verify_email"}))

    assert run(Jobs(store).expire_unverified(NOW)) == 1
    old = doc(store, "USR_OLD")
    assert old is not None
    assert old["status"] == "EXPIRED"
    assert old["version"] == 2
    assert old["statusHistory"][-1]["to"] == "EXPIRED"
    assert doc(store, "USR_NEW")["status"] == "PENDING_VERIFICATION"  # type: ignore[index]
    assert run(store.temp.count_documents({"accountId": "USR_OLD"})) == 0
    assert run(store.audit.count_documents({"action": "account.expired", "entity.id": "USR_OLD"})) == 1
    assert run(Jobs(store).expire_unverified(NOW)) == 0  # idempotent


def test_admins_are_reminded_once_about_accounts_waiting_48_hours(store: Store) -> None:
    run(store.accounts.insert_one(account("USR_WAIT", "PENDING_APPROVAL", verifiedAt=NOW - timedelta(hours=49))))
    run(store.accounts.insert_one(account("USR_FRESH", "PENDING_APPROVAL", verifiedAt=NOW - timedelta(hours=10))))

    jobs = Jobs(store)
    assert run(jobs.remind_approvals(NOW)) == 1
    waiting = doc(store, "USR_WAIT")
    assert waiting is not None
    assert [e["type"] for e in waiting["outbox"]] == ["user.approval_pending"]
    assert waiting["outbox"][0]["payload"]["userId"] == "USR_WAIT"
    assert waiting["outbox"][0]["payload"]["waitingSince"].startswith("2026-11-05")
    assert doc(store, "USR_FRESH")["outbox"] == []  # type: ignore[index]
    # Three days later the fresh account is due too; the first one is never reminded twice.
    assert run(jobs.remind_approvals(NOW + timedelta(days=3))) == 1
    assert len(doc(store, "USR_WAIT")["outbox"]) == 1  # type: ignore[index]
    assert len(doc(store, "USR_FRESH")["outbox"]) == 1  # type: ignore[index]


def test_rejected_and_expired_accounts_are_purged_after_90_days(store: Store) -> None:
    old = NOW - timedelta(days=91)
    run(store.accounts.insert_one(account("USR_REJ", "REJECTED", updatedAt=old, mfa={"enabled": True})))
    run(store.accounts.insert_one(account("USR_EXP", "EXPIRED", updatedAt=NOW - timedelta(days=30))))
    run(store.accounts.insert_one(account("USR_ACT", "ACTIVE", updatedAt=old)))
    run(
        store.audit.insert_one(
            {"id": "AUD1", "actor": {"id": "USR_REJ", "name": "Ann Smith", "role": "user"}, "ip": "1.2.3.4"}
        )
    )

    out = run(Jobs(store).purge_accounts(NOW))
    assert out == {"purged": 1, "removed": 0}  # phase 1 only: the tombstone is still in the outbox
    rej = doc(store, "USR_REJ")
    assert rej is not None
    assert rej["firstname"] == DELETED
    assert rej["phone"] is None
    assert rej["addresses"] == []
    assert "passwordHash" not in rej
    assert "mfa" not in rej
    assert rej["email"].endswith("@deleted.invalid")
    assert [e["type"] for e in rej["outbox"]] == ["user.deleted"]
    assert rej["outbox"][0]["payload"] == {"userId": "USR_REJ"}
    audit = run(store.audit.find_one({"id": "AUD1"}))
    assert audit["actor"]["name"] == DELETED
    assert "ip" not in audit
    assert run(store.audit.count_documents({"action": "account.deleted"})) == 1
    assert doc(store, "USR_EXP")["firstname"] == "Ann"  # type: ignore[index]  # only 30 days
    assert doc(store, "USR_ACT")["firstname"] == "Ann"  # type: ignore[index]  # never purged

    # The relay publishes the tombstone (outbox emptied) -> the next run removes the document.
    run(store.accounts.update_one({"id": "USR_REJ"}, {"$set": {"outbox": []}}))
    assert run(Jobs(store).purge_accounts(NOW)) == {"purged": 0, "removed": 1}
    assert doc(store, "USR_REJ") is None
    # The real address is free again for a new sign-up.
    assert run(store.accounts.count_documents({"email": "usr_rej@example.org"})) == 0


def test_run_all_reports_counts(store: Store) -> None:
    assert run(Jobs(store).run_all(NOW)) == {"expired": 0, "reminded": 0, "purged": 0, "removed": 0}


def test_audit_events_from_other_services_are_stored_once(store: Store) -> None:
    evt = new_event(
        "audit.recorded",
        {
            "action": "order.quoted",
            "entity": {"type": "request", "id": "ORD1"},
            "actor": {"id": "USR_STAFF", "name": "Sam Staff", "role": "staff"},
            "from": "QUOTING",
            "to": "QUOTED",
            "ip": None,
        },
        correlation_id="c1",
        actor_id="USR_STAFF",
    )
    handle = make_handler(store)
    run(handle(evt.envelope()))
    run(handle(evt.envelope()))  # redelivery after the processed-key expired
    entries = run(store.audit.find({}).to_list())
    assert len(entries) == 1
    e = entries[0]
    assert e["id"] == f"AUD{evt.eventId}"
    assert e["action"] == "order.quoted"
    assert e["to"] == "QUOTED"
    assert "ip" not in e


def test_malformed_audit_event_is_rejected_for_the_dlq() -> None:
    evt = new_event("audit.recorded", {"action": "x"}, correlation_id="c")
    with pytest.raises(ValueError, match="lacks action/entity/actor"):
        entry_from_event(evt.envelope())


def test_job_thresholds_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from identity_svc.jobs import JobSettings

    monkeypatch.setenv("UNVERIFIED_EXPIRE_HOURS", "12")
    monkeypatch.setenv("APPROVAL_REMINDER_HOURS", "24")
    monkeypatch.setenv("PURGE_AFTER_DAYS", "30")
    s = JobSettings.from_env()
    assert (s.unverified_after, s.reminder_after, s.purge_after) == (
        timedelta(hours=12),
        timedelta(hours=24),
        timedelta(days=30),
    )
