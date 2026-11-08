"""document-svc smoke test on the DEV stack (P6 exit criteria: EICAR quarantined, uploads and downloads work).

    SCAN_ENABLED=true docker compose -f deploy/compose.dev.yml --profile kafka --profile clamav up -d --wait \
        clamav document-svc
    docker run --rm --network sia-dev_default -v "$PWD/tools:/w/tools:ro" -v sia-dev_media:/srv/sia-data:ro \
        cimh/order-svc:dev python /w/tools/e2e/document_smoke.py

Uses any existing request in the dev DB (run the Playwright order journeys or order_smoke.py first).
Without ClamAV (SCAN_ENABLED=false) the EICAR step is reported as skipped, not passed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx
from pymongo import MongoClient

DOC = "http://document-svc:8000/api/documents/v1"
MONGO = "mongodb://mongo:27017/?replicaSet=rs0"
QUARANTINE = Path("/srv/sia-data/quarantine")
# The standard anti-virus test file: harmless, but every scanner reports it (Eicar-Test-Signature).
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def check(cond: bool, label: str, r: httpx.Response | None = None) -> None:
    print(("ok   " if cond else "FAIL ") + label + ("" if cond or r is None else f"  [{r.status_code}] {r.text[:300]}"))
    if not cond:
        sys.exit(1)


def main() -> int:
    tok = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "perf" / "staff_token.py")],
        check=True, capture_output=True, text=True,
    ).stdout.strip()  # fmt: skip
    staff = {"Authorization": f"Bearer {tok}"}
    req = MongoClient(MONGO)["inventory"].orders.find_one({"status": {"$ne": "CART"}}, {"id": 1})
    check(req is not None, "a request exists in the dev DB")
    rid = req["id"]  # type: ignore[index]
    c = httpx.Client(timeout=60)

    def upload(data: bytes, name: str) -> httpx.Response:
        return c.post(f"{DOC}/files", headers=staff, data={"requestId": rid, "kind": "upload"},
                      files={"file": (name, data, "application/pdf")})  # fmt: skip

    pdf = b"%PDF-1.4\n% document smoke\n%%EOF\n"
    r = upload(pdf, "smoke.pdf")
    check(r.status_code == 201, "clean PDF uploaded", r)
    fid = r.json()["id"]
    r = c.get(f"{DOC}/files/{fid}", headers=staff)
    check(r.status_code == 200 and (r.content == pdf or "x-accel-redirect" in r.headers), "staff download", r)
    check(c.get(f"{DOC}/files/{fid}").status_code == 401, "anonymous download refused")

    before = set(QUARANTINE.glob("*.json")) if QUARANTINE.exists() else set()
    r = upload(EICAR, "eicar.pdf")  # clamd matches EICAR only at the start of a file
    if r.status_code == 415:
        print("SKIP EICAR refused as a non-PDF: scanning is off (SCAN_ENABLED=false); this is not a pass")
        return 0
    check(r.status_code == 422 and r.json().get("code") == "FILE_INFECTED", "EICAR refused (FILE_INFECTED)", r)
    new = set(QUARANTINE.glob("*.json")) - before
    check(len(new) == 1, "EICAR quarantined")
    info = json.loads(next(iter(new)).read_text())
    check("Eicar" in info.get("signature", ""), f"signature recorded: {info.get('signature')}")
    print("document smoke passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
