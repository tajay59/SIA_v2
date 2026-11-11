# Deployment and release run book (#21)

For: whoever releases CIMH Stores (one developer, with Claude Code). Background: INFRASTRUCTURE §4, §9–§10; CI in `.github/workflows/ci.yml`.

## How a change reaches production

1. **Branch → PR → `main`.** `main` is protected: PR only, the 6 required checks (python, integration, web, security, infra, e2e), up to date, squash merge. Merge with `gh pr merge --squash --auto`.
2. **On `main`, CI builds, scans and signs** each service image (Trivy blocks on HIGH/CRITICAL; cosign keyless signature), runs the platform rehearsal, and **deploys staging-lite** (`deploy-staging`).
3. **Production is deployed per service by digest** on `sia-host` by the self-hosted runner:
   ```
   deploy/scripts/deploy.sh prod <service> sha256:<digest>
   ```
   It verifies the cosign signature (only images built by this repo's CI on `main`), pulls, `up -d`, waits for `/health/ready`, runs `scripts/smoke.sh`, and **rolls back to the previous digest** if any step fails. Digests are kept in `/srv/sia-deploy/prod`.

## Release checklist (each production release)

| # | Step | Check |
|---|---|---|
| 1 | All required checks green on `main`; no open S1/S2 (TEST_STRATEGY §10) | GitHub |
| 2 | Staging-lite updated and the changed journeys tried by hand | https://sia.hashiz.store |
| 3 | Data changes: validators (`MONGO_VALIDATION`), indexes and migrations reviewed; a backup newer than 24 h exists (`restic snapshots`) | BSD §7, OPERATIONS |
| 4 | Announce if users notice anything (downtime, new screens) | email lists (A-19) |
| 5 | Deploy services in dependency order: identity → catalog → inventory → order → document → notification → media-worker; relays and consumers follow their service (same image) | `deploy.sh` per service |
| 6 | Watch for 15 min: Prometheus `ServiceDown`, `HighErrorRate`, `SlowP95`, `OutboxBacklog`, `ConsumerLagHigh` quiet | `/ops/prometheus/` |
| 7 | Web apps: copy the SHOP and SIA builds to `/srv/sia-web/shop` and `/srv/sia-web/sia` (atomic: copy to `*.new`, then rename) | browser hard refresh |
| 8 | Mobile: signed APK from the CI artifact `sia-mobile-<run>` → staff devices | M-01 login |
| 9 | Note the release (date, digests, what changed) in the CLAUDE.md progress log | — |

## Rollback

- **One service:** `deploy.sh prod <service> <previous digest>` (the previous digest is in `/srv/sia-deploy/prod/<service>`). Images are immutable and signed, so a rollback is the same path as a release.
- **Web apps:** rename the previous build directory back.
- **Data changes:** rolling code back does not roll data back. Changes must be backward-compatible for one release (add fields, then remove later). If a release corrupted data: INCIDENT_RESPONSE + DISASTER_RECOVERY (restore to the last good snapshot).

## Edge and certificates

- nginx config lives in `deploy/nginx/` (templates rendered from `env/prod.env`). After a change: `bash deploy/nginx/test-config.sh`, then `docker compose -f compose.prod.yml up -d nginx`.
- Certificates renew automatically (certbot every 12 h, nginx reloads every 6 h). First certificate or a name change: `bash nginx/certs.sh` (INFRASTRUCTURE §10 step 7).

## Secrets

Never in git or images. Created once by `deploy/scripts/make-secrets.sh` into `deploy/secrets/` (copy every new value to the CIMH password manager). Rotation: OPERATIONS §Secrets.
