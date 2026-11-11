# Operations run book (#22)

For: the person who keeps CIMH Stores running day to day. Commands run on `sia-host` in `/srv/sia/deploy` (the `deploy/` directory) unless noted. `C="docker compose -f compose.prod.yml"`.

## Daily (5 minutes)

| Check | How | Normal |
|---|---|---|
| Alerts | Alert email inbox; `https://<SIA_HOST>/ops/prometheus/alerts` (CIMH LAN, user `ops`) | Nothing firing |
| Last backup | `$C --profile tools run --rm backup restic snapshots --latest 1` | < 26 h old |
| Containers | `$C ps --format '{{.Service}} {{.Status}}'` | all `Up … (healthy)` |
| Replica set | `$C exec mongo1 mongosh --quiet --tls … --eval 'rs.status().members.map(m=>m.stateStr)'` | 1 PRIMARY (sia-host), 2 SECONDARY |
| Dead letters | Prometheus `DlqNotEmpty` | none |

## Weekly

- Disk: `df -h /srv` (alert at 80 %); Kafka retention trims old segments by itself.
- Approvals waiting (A-16) and erasure requests (A-17): the admin reads the `registration` emails.
- Stale carts are emptied by `order-jobs` after 180 days; nothing to do.

## Monthly (patch window, TRD)

1. OS updates on the host and both Pis (`unattended-upgrades` covers security; reboot in the window). **Pis need a manual LUKS unlock after a reboot** (DISASTER_RECOVERY §Power).
2. Rebuild images on `main` to pick up base-image fixes (CI `apt-get upgrade` in every runtime stage) and deploy (DEPLOYMENT).
3. Restore test: restore the latest backup into staging and check the counts (`$C --profile tools run --rm backup restore.sh latest`; quarterly at minimum, SECURITY T-32).

## Common tasks

| Task | Steps |
|---|---|
| Restart one service | `$C restart <service>`; Redis/Mongo restarts are safe: clients retry (pen test F-07) |
| Scale a service | `$C up -d --scale catalog-svc=4 catalog-svc` (nginx resolves replicas through Docker DNS) |
| Read logs | `$C logs --since 30m <service>`: JSON lines with `traceId`; the `X-Trace-Id` response header ties a user report to the log |
| Change alert email / SMTP | edit `env/prod.env`, then `scripts/render-config.sh prod && $C up -d alertmanager` |
| Unlock an account | locks expire by themselves (15 min, longer after repeats); there is no admin unlock |
| Admin lost the TOTP device | **No admin MFA-reset function exists yet** (gap, P10 backlog). Until then: with the Mongo root user, `$unset` the admin's `mfa` field in `accounts` and suspend/reactivate them to revoke sessions; they enrol again at next login. Record it in the incident log. Keep at least two admins (`LAST_ADMIN` guard) |
| Run the migration again (staging) | `tools/migrate/` README; never against production after cut-over |

## Secrets rotation (yearly, or at once after a leak)

| Secret | Rotate | Effect |
|---|---|---|
| JWT signing key | new `jwt_private_key`, restart identity; JWKS publishes the new `kid`, old tokens expire within 15 min | users stay signed in (refresh) |
| Mongo / Kafka / Redis passwords | new file, re-run `mongo/roles.js` / `kafka/setup.sh` / `redis/render-acl.sh`, restart the service | short restart |
| Service secrets | new `service_secrets` + each `service_secret_<name>`, restart identity then the callers | short restart |
| `data_key` (envelopes) | needs re-encryption of TOTP secrets: plan with a script; do not just replace | — |
| SMTP app password | Google account → new app password → `secrets/smtp_password`, restart notification + alertmanager | — |
| `ops` password | delete `ops_password` and `ops_htpasswd`, re-run `make-secrets.sh`, restart nginx | — |

## Capacity notes (P9 measurements)

- catalog-svc: ~145 req/s per 0.5-CPU replica before latency rises; search at 2M products p95 20 ms (bounded ranking, `SEARCH_CANDIDATES` = 300).
- identity-svc: ~6–7 logins/s per 0.5-CPU replica (Argon2id 19 MiB/t=2); overload answers 503 `AUTH_BUSY` with `Retry-After`. A login storm of 33/s needs ~5 replicas.
- MongoDB: 6 GB cache in an 8 GB container leaves ~2 GB for queries (64 GB upgrade decision, INFRASTRUCTURE Q4).
