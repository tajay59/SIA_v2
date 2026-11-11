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

## Not covered by alerts yet (TR-OBS-3 gaps)

Security-event alerts (failed-login spikes, admin login from a new IP, refresh-token reuse, ClamAV detections), certificate expiry < 14 days, and "new unhandled exception type" need metrics the services do not export yet. Until then: the audit log (A-20) and `$C logs identity-svc | grep -E 'TOKEN_REUSE|auth.locked'` weekly, and certbot renews automatically (check `certbot certificates` monthly).

## Checking that alerting works

After any change to Alertmanager or SMTP settings, and monthly: stop one non-critical exporter for 3 minutes (`$C stop redis-exporter`) and confirm the email arrives, then start it again.
