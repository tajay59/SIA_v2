"""End-to-end smoke of identity-svc against a running stack (real MongoDB replica set + Redis).

    docker run --rm --network sia-dev_default -v "$PWD/tools/e2e:/e2e:ro" cimh/identity-svc:dev \
        python /e2e/identity_smoke.py --base http://identity-svc:8000 --mongo "mongodb://mongo:27017/?replicaSet=rs0"

Journey: register (member + CIMH) -> claim codes as notification-svc -> verify -> bootstrap an admin
-> MFA setup/confirm -> org create -> approve -> member login (web cookies + CSRF) -> refresh rotation
-> reuse detection -> logout. Uses unique emails each run; writes only to a dev database.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import struct
import sys
import time
import uuid

import httpx
from pymongo import MongoClient

API = "/api/identity/v1"


def totp(secret: str, at: float) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", int(at // 30)), hashlib.sha1).digest()
    o = digest[-1] & 15
    return f"{(struct.unpack('>I', digest[o : o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def check(cond: bool, label: str, resp: httpx.Response | None = None) -> None:
    detail = f" -> {resp.status_code} {resp.text[:200]}" if resp is not None and not cond else ""
    print(("PASS " if cond else "FAIL ") + label + detail)
    if not cond:
        sys.exit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:18001")
    ap.add_argument("--mongo", required=True)
    ap.add_argument("--service-secret", default="dev-notification-secret")
    a = ap.parse_args()

    run = uuid.uuid4().hex[:8]
    pw = "a long dev password " + run
    db = MongoClient(a.mongo)["inventory"]
    c = httpx.Client(base_url=a.base + API, timeout=10)

    svc = c.post("/internal/service-token", json={"service": "notification", "secret": a.service_secret})
    check(svc.status_code == 200, "notification-svc gets a service token", svc)
    sh = {"Authorization": "Bearer " + svc.json()["token"]}

    def claim(email: str, event_type: str = "user.registered") -> str:
        acc = db.accounts.find_one({"email": email})
        ref = next(e for e in reversed(acc["outbox"]) if e["type"] == event_type)["payload"]["codeRef"]
        r = c.get(f"/internal/codes/{ref}", headers=sh)
        check(r.status_code == 200, f"claim code for {email}", r)
        again = c.get(f"/internal/codes/{ref}", headers=sh)
        check(again.status_code == 404, "code can only be claimed once", again)
        return str(r.json()["code"])

    member = f"member.{run}@example.org"
    r = c.post(
        "/auth/register",
        json={
            "firstname": "Mem",
            "lastname": "Ber",
            "email": member,
            "password": pw,
            "organisationText": "Example Met",
            "country": "BB",
        },
    )
    check(r.status_code == 202, "member registers", r)
    r = c.post("/auth/verify", json={"email": member, "code": claim(member)})
    check(r.json().get("status") == "PENDING_APPROVAL", "member verified -> PENDING_APPROVAL", r)

    boss = f"boss.{run}@cimh.edu.bb"
    c.post("/auth/register", json={"firstname": "Bo", "lastname": "Ss", "email": boss, "password": pw, "country": "BB"})
    r = c.post("/auth/verify", json={"email": boss, "code": claim(boss)})
    check(r.json().get("status") == "ACTIVE", "CIMH account auto-activates", r)
    # Bootstrap: the first admins come from the migration; here we promote directly in the dev DB.
    db.accounts.update_one({"email": boss}, {"$set": {"role": "admin"}})

    r = c.post("/auth/login", json={"email": boss, "password": pw, "client": "mobile"})
    check(r.status_code == 200, "admin logs in (no MFA yet)", r)
    ah = {"Authorization": "Bearer " + r.json()["accessToken"]}
    r = c.get("/admin/accounts", headers=ah)
    check(r.json().get("code") == "MFA_REQUIRED", "admin endpoints blocked until MFA", r)
    uri = c.post("/auth/mfa/setup", headers=ah).json()["otpauthUri"]
    secret = uri.split("secret=")[1].split("&")[0]
    r = c.post("/auth/mfa/confirm", headers=ah, json={"totp": totp(secret, time.time())})
    check(r.status_code == 204, "MFA confirmed", r)
    r = c.post("/auth/login", json={"email": boss, "password": pw, "client": "mobile"})
    check(r.json().get("code") == "MFA_REQUIRED", "login now requires TOTP", r)
    r = c.post(
        "/auth/login", json={"email": boss, "password": pw, "client": "mobile", "totp": totp(secret, time.time() + 30)}
    )
    check(r.status_code == 200, "admin logs in with TOTP", r)
    ah = {"Authorization": "Bearer " + r.json()["accessToken"]}

    r = c.post("/organisations", headers=ah, json={"name": f"Example Met {run}", "country": "BB"})
    check(r.status_code == 201, "admin creates organisation", r)
    org = r.json()["id"]
    pend = c.get("/admin/accounts", headers=ah, params={"status": "PENDING_APPROVAL", "q": "member." + run})
    acc = pend.json()["items"][0]
    check(acc["email"] == member, "member is in the approval queue", pend)
    r = c.post(f"/admin/accounts/{acc['id']}/approve", headers={**ah, "If-Match": '"2"'}, json={"organisationId": org})
    check(r.status_code == 200 and r.json()["status"] == "ACTIVE", "admin approves member", r)

    web = httpx.Client(base_url=a.base + API, timeout=10)
    r = web.post("/auth/login", json={"email": member, "password": pw})
    check(r.status_code == 200 and "access_token" in web.cookies, "member web login sets cookies", r)
    me = web.get("/me")
    check(me.json().get("organisationName") == f"Example Met {run}", "member sees own org", me)
    r = web.patch("/me", headers={"If-Match": me.headers["ETag"]}, json={"phone": "+1 246 555 0100"})
    check(r.status_code == 403, "write without CSRF header refused", r)
    csrf = web.cookies["csrf_token"]
    r = web.patch(
        "/me", headers={"If-Match": me.headers["ETag"], "X-CSRF-Token": csrf}, json={"phone": "+1 246 555 0100"}
    )
    check(r.status_code == 200, "profile update with CSRF + If-Match", r)

    m = c.post("/auth/login", json={"email": member, "password": pw, "client": "mobile"}).json()
    r1 = c.post("/auth/refresh", json={"refreshToken": m["refreshToken"]})
    check(r1.status_code == 200, "refresh rotates", r1)
    r2 = c.post("/auth/refresh", json={"refreshToken": m["refreshToken"]})
    check(r2.json().get("code") == "TOKEN_REUSE", "reused refresh token detected", r2)
    r3 = web.get("/me")
    check(r3.status_code == 401, "reuse revoked ALL member sessions (web too)", r3)

    audit = c.get("/audit", headers=ah, params={"entityId": acc["id"]}).json()["items"]
    check(any(i["action"] == "account.approved" for i in audit), "approval is in the audit log")
    pending_events = db.accounts.find_one({"email": member})["outbox"]
    check(len(pending_events) >= 3, f"outbox holds {len(pending_events)} events for the relay")
    r = c.post("/auth/logout", headers=ah)
    check(r.status_code == 204, "admin logs out", r)
    check(c.get("/me", headers=ah).status_code == 401, "token dead after logout")
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
