# ADR-0008: Local file volume and nginx X-Accel-Redirect; no object storage

- Status: Accepted (2026-11-06)
- Related: TAD §7.5, INFRASTRUCTURE, ADR-0009

## Context
Files are product photos (public) and customer uploads, quotes, agreements and invoices (private). Volumes are small (hundreds of files). Everything runs on one host with Docker Compose.

## Options
1. **Object storage (MinIO / S3)**: presigned URLs and easy scaling; another stateful service to run, back up and secure.
2. **Files in MongoDB (GridFS)**: one backup; bloats the replica set and the Pis.
3. **Local volume `/srv/sia-data`; nginx serves a file after the service says yes (`X-Accel-Redirect`).**

## Decision
Option 3. `public/` is served directly; `protected/` only through the internal `/_protected/` location after document-svc checks access. Uploads are size-limited, sniffed, scanned by ClamAV and re-encoded when they are images; metadata lives in a sidecar `protected/meta/<fileId>.json`.

## Consequences
- Downloads are fast and never stream through Python; permission checks stay in the service.
- Files are backed up with restic next to the database; the volume is tied to the host (ADR-0013).
- File modes matter: protected files must be readable by nginx (0644 under a 0755 tree).
- Moving to object storage later changes only document-svc and the media-worker.
