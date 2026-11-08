"""M08: legacy product images and order files -> v2 media layout (MIGRATION_PLAN §5 M08).

Usage:  python tools/migrate/files_to_v2.py <legacy-app-dir> <converted-dir> <out-dir>

<legacy-app-dir>  the legacy Flask `app/` folder (productImages/, invoices/, uploads/, tempquotations/)
<converted-dir>   output of legacy_to_v2.py (reads product.json, orders.json)
<out-dir>         gets `media/` (copy into /srv/sia-data) and `apply.js` (run with mongosh against `inventory`)

Product images are re-encoded with the media-worker's own code (WebP 1600/800/320, metadata stripped) to
`public/products/<productId>/<fileId>[@800|@320].webp`. Order files are copied unchanged to
`protected/orders/<orderId>/<fileId><ext>` with their SHA-256. Missing files are listed in `files-report.json`.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import secrets
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from bson import json_util

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/media-worker/src"))
from media_worker.imaging import ImageRejected, process

ORDER_DIRS = ("invoices", "uploads", "tempquotations")
NOW = datetime.now(UTC).replace(microsecond=0)
MIGRATE = {"id": "svc:migrate", "name": "Legacy migration", "role": "system"}


def main() -> None:
    legacy, conv, out = (Path(a) for a in sys.argv[1:4])
    media = out / "media"
    rep: dict[str, list[str]] = {"missing": [], "rejected": [], "done": []}
    updates: list[dict] = []

    products = json_util.loads((conv / "product.json").read_text(encoding="utf-8"))
    for p in products:
        images = []
        for name in p.get("legacyImages") or []:
            src = legacy / "productImages" / name
            if not src.is_file():
                rep["missing"].append(f"product {p['id']}: image {name}")
                continue
            fid = "IMG" + secrets.token_hex(12).upper()
            try:
                done = process(src, media / "public/products" / p["id"], fid, remove_background=False, remover=None)
            except ImageRejected as exc:
                rep["rejected"].append(f"product {p['id']}: {name}: {exc}")
                continue
            images.append(
                {
                    "fileId": fid,
                    "url": f"/media/products/{p['id']}/{fid}.webp",
                    "w": done.width,
                    "h": done.height,
                    "primary": not images,
                }
            )
        if images:
            rep["done"].append(f"product {p['id']}: {len(images)} image(s)")
            updates.append({"c": "product", "q": {"id": p["id"]}, "u": {"$set": {"images": images}}})

    index = {f.name: f for d in ORDER_DIRS if (legacy / d).is_dir() for f in (legacy / d).iterdir() if f.is_file()}
    orders = json_util.loads((conv / "orders.json").read_text(encoding="utf-8"))

    # Invoices the legacy app generated, named by order id: <id>.pdf (paid), <id>_nci.pdf (Pro Bono). A split
    # order's Pro Bono half has a new id; its history says "split from <legacy id>".
    def legacy_id(o: dict) -> str:
        m = re.search(r"split from (ORD\w+)", (o.get("history") or [{}])[0].get("reason") or "")
        return m.group(1) if m else o["id"]

    for o in orders:
        if o["status"] == "CART":
            continue
        name = f"{legacy_id(o)}{'_nci' if o['type'] == 'PROBONO' else ''}.pdf"
        if name in index:
            kind = "probono_invoice" if o["type"] == "PROBONO" else "invoice"
            o.setdefault("legacy", {}).setdefault("files", []).insert(
                0, {"legacyFile": name, "name": name, "kind": kind}
            )

    for o in orders:
        files = []
        for f in (o.get("legacy") or {}).get("files") or []:
            src = index.get(f["legacyFile"])
            if src is None:
                rep["missing"].append(f"order {o['id']}: file {f['legacyFile'][:40]}")
                continue
            fid = "FIL" + secrets.token_hex(12).upper()
            rel = f"protected/orders/{o['id']}/{fid}{src.suffix.lower()}"
            (media / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, media / rel)
            data = (media / rel).read_bytes()
            files.append(
                {
                    "id": fid,
                    "kind": f["kind"],
                    "name": f["name"],
                    "mime": mimetypes.guess_type(src.name)[0] or "application/octet-stream",
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "path": rel,
                    "uploadedBy": MIGRATE,
                    "uploadedAt": NOW,
                }
            )
        if files:
            rep["done"].append(f"order {o['id']}: {len(files)} file(s)")
            updates.append({"c": "orders", "q": {"id": o["id"]}, "u": {"$set": {"files": files}}})

    out.mkdir(parents=True, exist_ok=True)
    payload = json_util.dumps(updates, json_options=json_util.CANONICAL_JSON_OPTIONS)
    (out / "apply.js").write_text(
        f"const ups = EJSON.parse({json.dumps(payload)});\n"
        "let n = 0; for (const x of ups) { n += db[x.c].updateOne(x.q, x.u).modifiedCount; }\n"
        "print('updated', n, 'of', ups.length);\n",
        encoding="utf-8",
    )
    (out / "files-report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print({k: len(v) for k, v in rep.items()})


if __name__ == "__main__":
    main()
