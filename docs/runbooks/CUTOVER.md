# Cut-over run book: legacy → v2 production (P10)

For: whoever runs the cut-over (the developer, with an admin and one staff member on call). Background: MIGRATION_PLAN §3–§10 (strategy, mapping, checks, rollback); this book is the exact command sequence for §8. DR-3 must run **this book, unchanged**, on staging.

## 0. What must exist first (gaps found 2026-11-19)

The plan's one-off `migrate --apply/--verify` container was never built. The working tools are `tools/migrate/legacy_to_v2.py` (convert), `dr1.sh`/`dr1.py` (load into a throwaway Mongo + every §6 check) and `load_staging.sh` / `load_files_staging.sh` (staging only). Before DR-2:

| # | Gap | To build |
|---|---|---|
| G1 | Production loader | **Built** `tools/migrate/load_prod.sh` (2026-11-19); first run = DR-2 |
| G2 | Production count check | **Built** `load_prod.sh --verify-only` (counts = files, validator levels, stock = product, `xuser`); the full §6 check stays `dr1.sh` on the same files |
| G3 | Production files loader | **Built** `tools/migrate/load_files_prod.sh` (copy, one-off `clamscan`, `apply.js`) |
| G4 | Read-only source user `svc_migrate_ro` not created | Create on 172.16.0.203 (`read` on `inventory`); drop after sign-off |
| G5 | Legacy maintenance page not written | One nginx `server` block on the legacy box returning 503 + a static page for SHOP/SIA, and 503 JSON for `/sia/api/` |
| G6 | 66 order uploads missing | Copy the legacy `uploads/` folder in the final file copy (step T-0:10) and re-run `files_to_v2.py` |

## 1. Days before

| When | Step | Done when |
|---|---|---|
| T-14 d | G1–G6 built; DR-2 run on staging with them (MIGRATION_PLAN §7) | All §6 checks green; spot-check signed |
| T-7 d | Staff trained on SIA v2; signed mobile APK on every staff device (DEPLOYMENT #8) | Each device logs in to production |
| T-7 d | Admins assigned an organisation to every active customer (DR report warning = 0) | `report.json` `warnings` empty |
| T-5 d | Announce the window: email to all ACTIVE accounts + SHOP banner (MIGRATION_PLAN §9) | Sent |
| ≤ T-7 d | **DR-3** on staging with a fresh dump and this book | ≤ 45 min, zero manual fixes |
| T-1 d | Production stack healthy with an **empty** database (`provision.sh prod`, every service deployed by digest); a restic backup of the empty stack; web builds copied to `/srv/sia-web/{shop,sia}.new` | `smoke.sh` passes; Prometheus quiet |

## 2. The window (weekday after 17:00 Barbados time; 2 h reserved)

Shell variables used below (set them once on each machine):

```bash
# legacy box
SRC='mongodb://svc_migrate_ro:<pw>@172.16.0.203:27017/inventory?authSource=admin'   # typed, never saved
OUT=/root/cutover-$(date -u +%Y%m%d)
# workstation (repo root, .venv)
EXP=db/cutover          # git-ignored; real personal data
```

| T | Step | Command / check | Owner |
|---|---|---|---|
| 0:00 | Legacy maintenance on | enable the G5 server block; `nginx -t && nginx -s reload`; SHOP shows the page, `/sia/api/` 503 | Ops |
| 0:05 | Stop Flask, confirm no writes | stop gunicorn; `mongosh "$SRC" --eval 'db.history.find().sort({date:-1}).limit(1).forEach(d=>print(d.date))'` (time only) stays the same for 2 min | Ops |
| 0:10 | Final dump + files | `for c in accounts product storage history orders misc temp; do mongoexport --uri "$SRC" -c $c --jsonArray --jsonFormat=canonical -o "$OUT/inventory.$c.json"; done`; `tar czf $OUT/app-files.tgz -C <legacy app dir> productImages invoices uploads tempquotations`; `sha256sum $OUT/* > $OUT/SHA256SUMS`; copy `$OUT` to the workstation as `$EXP` and check the sums | Ops |
| 0:20 | Convert + full check | `bash tools/migrate/dr1.sh $EXP` → **0 failures**, warnings reviewed (`$EXP/v2/dr1/verify.md`); `python tools/migrate/files_to_v2.py <unpacked app dir> $EXP/v2 $EXP/v2-files` | Tech lead |
| 0:30 | Load data | copy `$EXP/v2/*.json` to the host (mode 600); `bash load_prod.sh <dir>` (G1); delete the json files | Tech lead |
| 0:38 | Load files | `bash load_files_prod.sh $EXP/v2-files` (G3); the script scans with ClamAV: 0 infected | Tech lead |
| 0:42 | Verify production | `bash load_prod.sh <dir> --verify-only` (G2): all PASS, validators `strict`; every service `/health/ready` | Tech lead |
| 0:45 | Spot-check + role logins | staff: 10 orders, 10 products, 10 units, 5 accounts side by side (legacy read-only copy vs v2); one admin, one staff, one customer log in with their **existing** password (admin then enrols MFA) | Staff + admin |
| 0:55 | **Go / no-go** | all of 0:20–0:45 green and spot-check signed → go; anything else → §3 | Owner |
| 1:00 | Switch | `mv /srv/sia-web/shop.new /srv/sia-web/shop` (same for sia); point DNS/edge at v2 (`deploy/nginx`, `test-config.sh`, `up -d nginx`); legacy routes removed | Ops |
| 1:05 | Smoke | `deploy/scripts/smoke.sh`; by hand: log in per role, browse, submit a test request and cancel it, stow + pick a test unit, download a migrated invoice, a staff device scans once | QA |
| 1:15 | Open | remove the banner; post "We've upgraded" (log in again, same password) | Admin |
| +1 h | Watch | Prometheus `/ops/prometheus/`: `ServiceDown`, `HighErrorRate`, `SlowP95`, `OutboxBacklog`, `ConsumerLagHigh`, `security_events_total` quiet; legacy stays stopped but intact | Ops |

Record each step's actual time; DR-3 and the real run are compared in the close-out.

## 3. Rollback

| Situation | Action |
|---|---|
| No-go (before 1:00) | Stop v2 app services; drop the production `inventory` db (backup from `load_prod.sh` kept); start Flask; legacy maintenance off. Nothing lost: the source was never written |
| Critical defect ≤ 48 h after go-live | MIGRATION_PLAN §10: v2 maintenance; export changes since cut-over (ids only report + CSV for staff); restart legacy on its untouched DB; staff re-key |
| After 48 h | Fix forward |

## 4. After

| When | Step |
|---|---|
| T+1 d | Email customers with SUBMITTED paid requests: a formal quote follows, they view and sign it (MIGRATION_PLAN §9) |
| T+2 d | Drop `svc_migrate_ro`; delete `$EXP` and every copy of the dump from the workstation and host (`shred`); keep only the restic snapshot |
| T+30 d | Archive legacy DB + files (encrypted, restic); decommission the legacy server; rotate any secret it held |
| T+30 d | Close-out notes: timings vs DR-3, issues, lessons (Documentation Index #32) |
