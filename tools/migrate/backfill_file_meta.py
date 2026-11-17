"""Write document-svc metadata sidecars for files already listed on orders.

Migrated files (files_to_v2.py before 2026-11-17) were copied to protected/orders/ and listed on the
order, but got no `protected/meta/<fileId>.json`, so document-svc answered 404 for them.

Run inside the document-svc container (read-only rootfs: the script comes in with -c, the data on
stdin, one JSON object per line {"id", "files"} from mongosh):

    docker compose exec -T mongo mongosh inventory --quiet --eval \
      'db.orders.find({"files.0": {$exists: true}}, {_id: 0, id: 1, files: 1}).forEach(o => print(EJSON.stringify(o, {relaxed: true})))' \
      > /tmp/orders-files.jsonl
    docker compose exec -T document-svc python -c "$(cat backfill_file_meta.py)" [--dry-run] < /tmp/orders-files.jsonl

Prints counts only (never names or ids). Existing sidecars are left alone. Pass --dry-run to only count.
"""

import json
import os
import sys
from pathlib import Path

GENERATED = {"invoice", "probono_invoice", "cimh_quote", "agreement", "probono_note", "commercial_invoice"}


def main(lines: list[str], root: Path, dry: bool) -> None:
    meta_dir = root / "protected" / "meta"
    stats = {"written": 0, "exists": 0, "no_file": 0}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        for f in o.get("files") or []:
            path = meta_dir / f"{f['id']}.json"
            if path.exists():
                stats["exists"] += 1
                continue
            rel = f.get("path") or ""
            if not rel or not (root / rel).is_file():
                stats["no_file"] += 1
                continue
            at = f.get("uploadedAt")
            if isinstance(at, dict):
                at = at.get("$date")
            meta = {
                "id": f["id"],
                "requestId": o["id"],
                "kind": f["kind"],
                "name": f["name"],
                "mime": f["mime"],
                "size": f["size"],
                "sha256": f["sha256"],
                "uploadedBy": f.get("uploadedBy"),
                "uploadedAt": at,
                "generated": f["kind"] in GENERATED,
            }
            if not dry:
                meta_dir.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(meta, default=str))
                os.replace(tmp, path)
            stats["written"] += 1
    print(("dry run: " if dry else "") + json.dumps(stats))


if __name__ == "__main__":
    data = sys.stdin.read().splitlines()
    main(data, Path(os.environ.get("DATA_DIR", "/srv/sia-data")), "--dry-run" in sys.argv)
