"""Print a staff Bearer token for perf runs on the DEV stack (15-minute access token).

Registers a throwaway @cimh.edu.bb account, verifies it with the code claimed through the internal endpoint
(as notification-svc would), promotes it to staff directly in the dev DB (as tools/e2e/identity_smoke.py does
for admins), then logs in as a mobile client. Dev only: refuses non-local Mongo hosts.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from urllib.parse import urlparse

import httpx
from pymongo import MongoClient

API = "/api/identity/v1"
SAFE_HOSTS = {"localhost", "127.0.0.1", "mongo"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", default="http://identity-svc:8000")
    ap.add_argument("--mongo", default="mongodb://mongo:27017/?replicaSet=rs0")
    ap.add_argument("--service-secret", default="dev-notification-secret")
    a = ap.parse_args()
    if (urlparse(a.mongo).hostname or "") not in SAFE_HOSTS:
        print("dev stack only", file=sys.stderr)
        return 2

    db = MongoClient(a.mongo)["inventory"]
    c = httpx.Client(base_url=a.identity + API, timeout=10)
    run = uuid.uuid4().hex[:8]
    email, pw = f"perf.staff.{run}@cimh.edu.bb", f"perf staff password {run}"

    body = {"firstname": "Perf", "lastname": "Staff", "email": email, "password": pw, "country": "BB"}
    r = c.post("/auth/register", json=body)
    r.raise_for_status()
    svc = c.post("/internal/service-token", json={"service": "notification", "secret": a.service_secret})
    svc.raise_for_status()
    acc = db.accounts.find_one({"email": email})
    ref = db.temp.find_one({"accountId": acc["id"], "kind": "verify_email"})["id"]
    code = c.get(f"/internal/codes/{ref}", headers={"Authorization": "Bearer " + svc.json()["token"]})
    code.raise_for_status()
    c.post("/auth/verify", json={"email": email, "code": str(code.json()["code"])}).raise_for_status()
    db.accounts.update_one({"email": email}, {"$set": {"role": "staff"}})
    r = c.post("/auth/login", json={"email": email, "password": pw, "client": "mobile"})
    r.raise_for_status()
    print(r.json()["accessToken"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
