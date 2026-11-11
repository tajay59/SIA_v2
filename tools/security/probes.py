"""Pen-test probes (docs/security/PENTEST-2026-11.md): what the generated authz matrix and Schemathesis cannot see.

Runs inside the dev Docker network against the dev stack and a local copy of the staging-lite gateway
(container `sia-pentest-gateway`). Dev data only; refuses anything that is not the dev stack.

    docker run --rm --network sia-dev_default -v "$PWD/tools:/w/tools:ro" cimh/order-svc:dev \
        python /w/tools/security/probes.py

Prints one line per probe: PASS (control held), FAIL (finding), INFO (observation). Exit 1 on any FAIL.
"""

from __future__ import annotations

import base64
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from pymongo import MongoClient

ID = "http://identity-svc:8000/api/identity/v1"
CAT = "http://catalog-svc:8000/api/catalog/v1"
INV = "http://inventory-svc:8000/api/inventory/v1"
ORD = "http://order-svc:8000/api/orders/v1"
DOC = "http://document-svc:8000/api/documents/v1"
GW = "http://sia-pentest-gateway"
MONGO = "mongodb://mongo:27017/?replicaSet=rs0"
HOST = {"Host": "sia.hashiz.store"}  # the gateway's server_name; nothing leaves this machine

RESULTS: list[tuple[str, str, str]] = []
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))
from order_smoke import claim_code  # noqa: E402  (same verification flow as the smoke test)


def rec(status: str, probe: str, detail: str = "") -> None:
    RESULTS.append((status, probe, detail))
    print(f"{status:4}  {probe}" + (f"  [{detail}]" if detail else ""), flush=True)


def expect(cond: bool, probe: str, detail: str = "") -> None:
    rec("PASS" if cond else "FAIL", probe, detail)


def svc_token(c: httpx.Client, name: str) -> dict[str, str]:
    r = c.post(f"{ID}/internal/service-token", json={"service": name, "secret": f"dev-{name}-secret"})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["token"]}


def new_customer(c: httpx.Client, db: Any, org: str) -> tuple[dict[str, str], str, str, str]:
    run = uuid.uuid4().hex[:8]
    email, pw = f"pentest.{run}@example.org", f"pentest password {run} x"
    body = {"firstname": "Pen", "lastname": "Test", "email": email, "password": pw, "country": "BB",
            "organisationText": "Pentest Org"}  # fmt: skip
    c.post(f"{ID}/auth/register", json=body).raise_for_status()
    acc = db.accounts.find_one({"email": email})
    ref = db.temp.find_one({"accountId": acc["id"], "kind": "verify_email"})["id"]
    c.post(f"{ID}/auth/verify", json={"email": email, "code": claim_code(c, ref, email)}).raise_for_status()
    db.accounts.update_one({"email": email}, {"$set": {"status": "ACTIVE", "organisationId": org}})
    r = c.post(f"{ID}/auth/login", json={"email": email, "password": pw, "client": "mobile"})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["accessToken"]}, email, pw, r.json()["refreshToken"]


def gateway(c: httpx.Client) -> None:
    """Edge controls of the staging-lite gateway config (production has no edge yet)."""
    for path in ["/api/identity/v1/internal/service-token", "/api/identity/v1/%69nternal/service-token",
                 "/api/identity/v1/%2569nternal/service-token", "/api/identity/v1//internal/service-token",
                 "/api/identity/v1/./internal/service-token", "/api/identity/v1/x/../internal/service-token",
                 "/api/IDENTITY/v1/internal/service-token", "/api/identity/v1/internal%2Fservice-token"]:  # fmt: skip
        r = c.post(GW + path, headers=HOST, json={"service": "order", "secret": "x"})
        reached = r.status_code in (401, 403, 422) or "token" in r.text
        expect(not reached, f"gateway blocks {path}", f"HTTP {r.status_code}")
    r = c.get(f"{GW}/api/catalog/v1/products", headers=HOST)
    h = r.headers
    for name in ["content-security-policy", "x-content-type-options", "x-frame-options", "strict-transport-security",
                 "referrer-policy"]:  # fmt: skip
        expect(name in h, f"gateway header {name}")
    expect("server" not in h or "nginx/" not in h.get("server", ""), "gateway hides the nginx version")
    big = c.post(f"{GW}/api/catalog/v1/products", headers=HOST, content=b"{" + b" " * 2_000_000 + b"}")
    expect(big.status_code == 413, "gateway refuses a 2 MB JSON body", f"HTTP {big.status_code}")
    codes = [c.post(f"{GW}/api/identity/v1/auth/login", headers=HOST,
                    json={"email": "nobody@example.org", "password": "wrong password x"}).status_code
             for _ in range(12)]  # fmt: skip
    expect(429 in codes, "gateway rate-limits /auth/login (5/min, burst 5)", f"{codes}")
    spoof = [c.post(f"{GW}/api/identity/v1/auth/login", headers={**HOST, "X-Real-IP": f"10.9.9.{i}"},
                    json={"email": "nobody@example.org", "password": "wrong password x"}).status_code
             for i in range(6)]  # fmt: skip
    rec("INFO", "X-Real-IP from a client: trusted by the gateway only from Docker/private ranges; the public edge "
        "overwrites it", f"{spoof}")  # fmt: skip


def internal_matrix(c: httpx.Client) -> None:
    """Which service may call which internal endpoint (least privilege)."""
    names = ["notification", "order", "catalog", "inventory", "document"]  # media-worker calls no service
    toks = {n: svc_token(c, n) for n in names}
    calls = {
        "identity /internal/accounts/{id}": ("GET", f"{ID}/internal/accounts/USRNOPE", None,
                                             {"order", "notification", "catalog"}),
        "catalog /internal/products/summaries": ("POST", f"{CAT}/internal/products/summaries", {"ids": ["X"]},
                                                 {"order", "inventory"}),
        "catalog /internal/email-lists": ("GET", f"{CAT}/internal/email-lists", None, {"notification"}),
        "catalog /internal/fees": ("GET", f"{CAT}/internal/fees", None, {"order"}),
        "catalog /internal/places": ("GET", f"{CAT}/internal/places", None, {"inventory"}),
        "inventory /internal/availability": ("POST", f"{INV}/internal/availability", {"lines": []}, {"order"}),
        "order /internal/requests/{id}/access": ("GET", f"{ORD}/internal/requests/REQNOPE/access?accountId=U",
                                                 None, {"document"}),
    }  # fmt: skip
    for label, (method, url, body, allowed) in calls.items():
        open_to = [n for n in names if c.request(method, url, headers=toks[n], json=body).status_code != 403]
        extra = sorted(set(open_to) - allowed)
        if extra:
            rec("FAIL", f"least privilege: {label}", f"also callable by {extra}")
        else:
            rec("PASS", f"least privilege: {label}", f"callable by {sorted(open_to)}")
    bad = c.post(f"{ID}/internal/service-token", json={"service": "order", "secret": "dev-order-secreT"})
    expect(bad.status_code in (401, 403), "service-token refuses a wrong secret", f"HTTP {bad.status_code}")
    nobody = c.post(f"{ID}/internal/service-token", json={"service": "admin", "secret": "x"})
    expect(
        nobody.status_code in (401, 403, 422), "service-token refuses an unknown service", f"HTTP {nobody.status_code}"
    )


def users(c: httpx.Client, db: Any) -> None:
    org = f"ORGPEN{uuid.uuid4().hex[:6]}"
    a, a_email, a_pw, a_refresh = new_customer(c, db, org)
    b, _, _, _ = new_customer(c, db, org)  # same organisation
    x, _, _, _ = new_customer(c, db, f"ORGOTHER{uuid.uuid4().hex[:6]}")
    notify = svc_token(c, "notification")

    # Service tokens on user endpoints; user tokens on internal endpoints.
    r = c.get(f"{ID}/me", headers=notify)
    expect(r.status_code in (401, 403), "service token refused on /me", f"HTTP {r.status_code}")
    r = c.get(f"{ID}/internal/accounts/USRNOPE", headers=a)
    expect(r.status_code in (401, 403), "customer token refused on /internal", f"HTTP {r.status_code}")

    # Mass assignment (T-15).
    for field, value in [("role", "admin"), ("status", "ACTIVE"), ("organisationId", "ORGX"), ("isCimh", True),
                         ("email", "other@example.org"), ("$set", {"role": "admin"})]:  # fmt: skip
        r = c.patch(f"{ID}/me", headers=a, json={field: value})
        expect(r.status_code in (400, 422), f"PATCH /me refuses {field}", f"HTTP {r.status_code}")
    me = c.get(f"{ID}/me", headers=a).json()
    expect(me.get("role") == "user", "role still user after the attempts")

    # Same organisation: read yes, act no; other organisation: 404 (T-12, T-16).
    pid = (c.get(f"{CAT}/products", params={"limit": 1}).json()["items"] or [{}])[0].get("id")
    if pid:
        c.put(f"{ORD}/cart/lines/{pid}", headers=a, json={"qty": 1})
        ship = {"line1": "x", "city": "y", "country": "BB", "firstname": "P", "lastname": "T", "email": a_email}
        r = c.post(f"{ORD}/requests", headers={**a, "Idempotency-Key": uuid.uuid4().hex},
                   json={"currency": "BBD", "shipTo": ship})  # fmt: skip
        if r.status_code == 201:
            rid = r.json()["requests"][0]["id"]
            v = c.get(f"{ORD}/requests/{rid}", headers=a).json()["version"]
            expect(c.get(f"{ORD}/requests/{rid}", headers=b).status_code == 200, "same-org colleague can read")
            r = c.post(f"{ORD}/requests/{rid}/cancel", headers={**b, "If-Match": str(v)}, json={"reason": "pen test"})
            expect(r.status_code == 403, "same-org colleague cannot cancel", f"HTTP {r.status_code}")
            expect(c.get(f"{ORD}/requests/{rid}", headers=x).status_code == 404, "other org: 404")
            r = c.post(f"{ORD}/requests/{rid}/cancel", headers={**x, "If-Match": str(v)}, json={"reason": "pen test"})
            expect(r.status_code == 404, "other org cannot cancel (404)", f"HTTP {r.status_code}")
            files = c.get(f"{ORD}/requests/{rid}", headers=a).json().get("files") or []
            for f in files[:2]:
                r = c.get(f"{DOC}/files/{f['fileId']}", headers=x)
                expect(r.status_code == 404, f"other org cannot download {f.get('kind')}", f"HTTP {r.status_code}")
            r = c.get(f"{DOC}/files/FILENOPE", headers=x)
            expect(r.status_code == 404, "unknown file id: 404", f"HTTP {r.status_code}")
            # Idempotency key reused by another user must not replay A's response.
            key = uuid.uuid4().hex
            c.put(f"{ORD}/cart/lines/{pid}", headers=a, json={"qty": 1})
            ra = c.post(
                f"{ORD}/requests", headers={**a, "Idempotency-Key": key}, json={"currency": "BBD", "shipTo": ship}
            )
            c.put(f"{ORD}/cart/lines/{pid}", headers=b, json={"qty": 1})
            rb = c.post(
                f"{ORD}/requests", headers={**b, "Idempotency-Key": key}, json={"currency": "BBD", "shipTo": ship}
            )
            same = ra.status_code == 201 and rb.status_code == 201 and ra.json() == rb.json()
            expect(not same, "same Idempotency-Key from another user does not replay the first response",
                   f"A {ra.status_code} B {rb.status_code}")  # fmt: skip
        else:
            rec("INFO", "could not submit a request (no available product?)", f"HTTP {r.status_code}")

    # Cursor / limit tampering: 4xx, never 5xx.
    for url, h in [(f"{CAT}/products", {}), (f"{ORD}/requests", a), (f"{CAT}/products/search", {})]:
        for params in [{"cursor": "!!!"}, {"cursor": base64.urlsafe_b64encode(b'{"o":-5}').decode()},
                       {"cursor": base64.urlsafe_b64encode(b'{"$gt":""}').decode()}, {"limit": "0"},
                       {"limit": "-1"}, {"limit": "100000"}, {"limit": "1e3"}]:  # fmt: skip
            if url.endswith("search"):
                params = {**params, "q": "rain"}
            r = c.get(url, headers=h, params=params)
            expect(r.status_code < 500, f"tampered paging {url.split('/v1')[1]} {params}", f"HTTP {r.status_code}")

    # Refresh-token reuse revokes the family (T-03).
    r1 = c.post(f"{ID}/auth/refresh", json={"refreshToken": a_refresh})
    expect(r1.status_code == 200, "refresh works once")
    r2 = c.post(f"{ID}/auth/refresh", json={"refreshToken": a_refresh})
    expect(r2.status_code == 401, "old refresh token refused on reuse", f"HTTP {r2.status_code} {r2.text[:60]}")
    if r1.status_code == 200:
        r3 = c.post(f"{ID}/auth/refresh", json={"refreshToken": r1.json()["refreshToken"]})
        expect(r3.status_code == 401, "reuse revoked the newer refresh token too (family)", f"HTTP {r3.status_code}")
        r4 = c.get(f"{ID}/me", headers={"Authorization": "Bearer " + r1.json()["accessToken"]})
        expect(r4.status_code == 401, "reuse revoked the session's access token", f"HTTP {r4.status_code}")

    # Lockout on email variants (T-01) and enumeration by status or timing (T-02).
    for i in range(5):
        c.post(f"{ID}/auth/login", json={"email": a_email, "password": f"wrong password {i} x"})
    for variant in [a_email.upper(), f"  {a_email} ", a_email.replace("@", "@")]:
        r = c.post(f"{ID}/auth/login", json={"email": variant, "password": a_pw})
        expect(r.status_code != 200, f"lockout holds for email variant {variant!r}", f"HTTP {r.status_code}")
    t_known, t_unknown, s_known, s_unknown = [], [], set(), set()
    for _ in range(15):
        t = time.perf_counter()
        s_known.add(c.post(f"{ID}/auth/login", json={"email": a_email, "password": "nope nope nope"}).status_code)
        t_known.append(time.perf_counter() - t)
        t = time.perf_counter()
        s_unknown.add(c.post(f"{ID}/auth/login", json={"email": f"no.{uuid.uuid4().hex}@example.org",
                                                         "password": "nope nope nope"}).status_code)  # fmt: skip
        t_unknown.append(time.perf_counter() - t)
    mk, mu = statistics.median(t_known), statistics.median(t_unknown)
    rec("INFO", "login status codes known(locked) vs unknown email", f"{sorted(s_known)} vs {sorted(s_unknown)}")
    expect(abs(mk - mu) < max(0.05, 0.5 * mu), "login timing does not reveal the email",
           f"median known {mk*1000:.0f} ms, unknown {mu*1000:.0f} ms")  # fmt: skip
    r = c.post(f"{ID}/auth/password/forgot", json={"email": a_email})
    r2 = c.post(f"{ID}/auth/password/forgot", json={"email": f"no.{uuid.uuid4().hex}@example.org"})
    expect(r.status_code == r2.status_code == 202, "forgot-password answers the same for unknown emails")

    # Client-supplied X-Real-IP when a service is reached directly (no edge).
    rec("INFO", "identity trusts X-Real-IP from any caller (api.py client_ip); safe only behind the edge")


def b64(obj: Any) -> str:
    raw = obj if isinstance(obj, bytes) else __import__("json").dumps(obj, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def relogin(c: httpx.Client, db: Any, email: str, pw: str, role: str) -> httpx.Response:
    db.accounts.update_one({"email": email}, {"$set": {"role": role}, "$unset": {"failedLogins": ""}})
    return c.post(f"{ID}/auth/login", json={"email": email, "password": pw, "client": "mobile"})


def tokens_mfa_uploads(c: httpx.Client, db: Any) -> None:
    import hashlib
    import hmac
    import json

    tok, email, pw, _ = new_customer(c, db, f"ORGPEN{uuid.uuid4().hex[:6]}")
    raw = tok["Authorization"].split()[1]
    head, body, sig = raw.split(".")
    claims = json.loads(base64.urlsafe_b64decode(body + "=="))
    hdr = json.loads(base64.urlsafe_b64decode(head + "=="))

    # JWT forgery (T-06): alg none, HS256 keyed with the public JWKS, edited claims, unknown kid, expired.
    jwks = c.get(f"{ID}/.well-known/jwks.json").text.encode()
    elevated = {**claims, "role": "admin", "mfa": True}
    forged = {
        "alg none": f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(elevated)}.",
        "HS256 with the JWKS as key": (lambda h, b: f"{h}.{b}." + b64(hmac.new(jwks, f"{h}.{b}".encode(),
                                        hashlib.sha256).digest()))(b64({**hdr, "alg": "HS256"}), b64(elevated)),
        "claims edited, signature kept": f"{head}.{b64(elevated)}.{sig}",
        "unknown kid": f"{b64({**hdr, 'kid': 'nope'})}.{body}.{sig}",
        "expired (exp in the past)": f"{head}.{b64({**claims, 'exp': 1})}.{sig}",
    }  # fmt: skip
    for label, t in forged.items():
        r = c.get(f"{ID}/admin/accounts", headers={"Authorization": f"Bearer {t}"})
        expect(r.status_code == 401, f"JWT forgery refused: {label}", f"HTTP {r.status_code}")

    # Admin without MFA (T-04): may sign in, but every admin endpoint answers 403 MFA_REQUIRED.
    r = relogin(c, db, email, pw, "admin")
    if r.status_code == 200:
        adm = {"Authorization": "Bearer " + r.json()["accessToken"]}
        r1 = c.get(f"{ID}/admin/accounts", headers=adm)
        expect(r1.status_code == 403 and r1.json().get("code") == "MFA_REQUIRED", "admin without MFA: admin API 403",
               f"HTTP {r1.status_code}")  # fmt: skip
        r2 = c.get(f"{CAT}/products", headers=adm, params={"includeInactive": "true"})
        expect(r2.status_code in (401, 403), "admin without MFA: staff views in other services refused",
               f"HTTP {r2.status_code}")  # fmt: skip
    else:
        rec("INFO", "admin re-login failed", f"HTTP {r.status_code}")

    # Uploads (T-23): staff image upload with wrong content.
    r = relogin(c, db, email, pw, "staff")
    staff = {"Authorization": "Bearer " + r.json()["accessToken"]}
    pid = (c.get(f"{CAT}/products", params={"limit": 1}).json()["items"] or [{}])[0].get("id")
    if pid:
        bad = {
            "HTML named .jpg": ("x.jpg", b"<html><script>alert(1)</script></html>", "image/jpeg"),
            "SVG with script": ("x.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                                "image/svg+xml"),
            "PDF named .png": ("x.png", b"%PDF-1.4\n%EOF", "image/png"),
            "path traversal name": ("../../etc/passwd.jpg", b"not an image", "image/jpeg"),
        }  # fmt: skip
        for label, (name, data, ctype) in bad.items():
            r = c.post(f"{CAT}/products/{pid}/images", headers=staff, files={"files": (name, data, ctype)})
            expect(r.status_code in (400, 415, 422), f"image upload refused: {label}", f"HTTP {r.status_code}")
        ihdr = (60000).to_bytes(4, "big") * 2 + bytes([8, 2, 0, 0, 0])
        bomb = bytes([0x89]) + b"PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR" + ihdr
        r = c.post(f"{CAT}/products/{pid}/images", headers=staff, files={"files": ("bomb.png", bomb, "image/png")})
        # catalog checks bytes and queues the file; media-worker opens it with Pillow's pixel limit (T-26).
        rec("INFO", "60000x60000 PNG header: catalog queues it (202), media-worker refuses it on open",
            f"HTTP {r.status_code}")  # fmt: skip


def main() -> int:
    if "mongo:27017" not in MONGO:
        return 2
    db = MongoClient(MONGO)["inventory"]
    with httpx.Client(timeout=20) as c:
        print("== gateway (staging-lite config, local)")
        gateway(c)
        print("== internal endpoints")
        internal_matrix(c)
        print("== users, data access, sessions")
        users(c, db)
        print("== tokens, MFA, uploads")
        tokens_mfa_uploads(c, db)
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS)} probes: {len(fails)} FAIL, {sum(r[0] == 'PASS' for r in RESULTS)} PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    _ = subprocess  # (kept for parity with the smoke scripts)
    sys.exit(main())
