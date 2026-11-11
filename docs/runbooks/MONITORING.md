# Monitoring and alerting guide (#24)

For: whoever receives the alert emails. Stack: Prometheus + Alertmanager only (TRD; no Grafana). Prometheus UI: `https://<SIA_HOST>/ops/prometheus/` (CIMH LAN + user `ops`). Rules: `deploy/prometheus/rules/alerts.yml` (unit tests in `deploy/prometheus/tests/`, CI).

Alerts go to `ALERT_EMAIL_TO` (Gmail SMTP). Critical alerts repeat every hour, warnings every 4 hours, until they clear.

## What is scraped

| Job | Target | Gives |
|---|---|---|
| services | every API service `/metrics` | request rate, errors, latency (RED), `outbox_pending_events`, `outbox_oldest_event_age_seconds` |
| node | host + both Pis (node-exporter) | CPU, memory, disk, reboots |
| mongodb | mongodb-exporter (`svc_monitor`, clusterMonitor) | replica set member health, lag |
| kafka | kafka-exporter (`exporter`, Describe only) | topic offsets, consumer-group lag, DLQs |
| redis | redis-exporter | up, memory, clients |
| blackbox | blackbox-exporter → `https://<SIA_HOST>/health`, `https://<STORE_HOST>/health` | reachability, certificate expiry |

## Alerts: meaning and first steps

| Alert | Severity | Means | First steps |
|---|---|---|---|
| `ServiceDown` | critical | A service has not answered scrapes for 2 min | `$C ps <service>`; `$C logs --since 10m <service>`; restart; if it crash-loops, roll back (DEPLOYMENT) |
| `HighErrorRate` | warning | > 1 % 5xx for 5 min | logs filtered by `"level": "ERROR"`; a dependency down (503) or a bug (500 with traceId); roll back if it started with a release |
| `SlowP95` | warning | p95 > 500 ms for 10 min | CPU per container (`docker stats`), Mongo slow queries (`mongod` log "Slow query"); scale the service (OPERATIONS) |
| `DlqNotEmpty` | warning | An event failed all retries | read the DLQ message (kafka-client), fix the cause, replay it; never delete without understanding it |
| `ConsumerLagHigh` | warning | A consumer is > 1,000 events behind for 5 min | is the consumer running? its logs; scale it; check Mongo/Redis |
| `OutboxBacklog` | critical | Events waited > 5 min to be published | is `outbox-relay-<service>` running and leader (Redis lock)? Kafka reachable? restart the relay; events are kept, nothing is lost |
| `ReplicaSetMemberDown` | critical | A MongoDB member is unhealthy | which member (`rs.status()`); Pi powered and unlocked (LUKS)? DISASTER_RECOVERY A/E |
| `HostMemoryHigh` | warning | > 85 % memory for 5 min | `docker stats` by container; the budget is tight (32 GB); a leak shows as steady growth: restart that service and report it |
| `DiskAbove80` | warning | A filesystem is over 80 % | `du -sh /srv/*`; Kafka trims by retention; old restic snapshots are pruned by `backup.sh`; Prometheus keeps 30 days |
| `HostRebooted` | critical | A machine started < 10 min ago | expected in a patch window; otherwise power: unlock the Pis (LUKS), check the replica set |
| `FailedLoginsHigh` | warning | > 20 failed logins/min for 2 min | password guessing? `$C logs identity-svc` for the source; the edge already limits 5/min per IP; block a single source in nginx |
| `AdminLockedOut` | critical | An admin account locked after 5 failures | call the admin: was it them? If not, treat as an attack on that account (INCIDENT_RESPONSE) |
| `AdminLoginNewIp` | warning | An admin signed in from a new IP | confirm with the admin; audit log A-20 (`auth.admin_login`, `newIp`) |
| `RefreshTokenReuse` | warning | A refresh token was used twice | the session family is already revoked; a stolen token or a buggy client; ask the user, check the audit log |
| `MalwareUploaded` | critical | ClamAV found malware in an upload | the file is quarantined (`/srv/sia-data/quarantine`); who uploaded it (audit `file.quarantined`)? contact the customer |
| `NewExceptionType` | warning | A new kind of unhandled error in a service | find it by type in the logs (traceId); usually a bug: fix or roll back |
| `CertExpiringSoon` | warning | < 14 days left on the public certificate | `$C logs certbot`; DNS and port 80 reachable? run `certbot renew` by hand; reload nginx |
| `SiteUnreachable` | critical | A public name fails HTTPS for 3 min | nginx up? certificate valid? DNS? firewall? |

## Not covered by alerts

"403/404 spikes from one user" (TR-OBS-3) is not alerted: a per-user metric label would grow without bound. Watch for it in the logs (`traceId`, `userId`) when another alert fires; nginx rate limits cap the volume.

## Checking that alerting works

After any change to Alertmanager or SMTP settings, and monthly: stop one non-critical exporter for 3 minutes (`$C stop redis-exporter`) and confirm the email arrives, then start it again.
