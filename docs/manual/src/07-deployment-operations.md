# 7. Deployment and operations

[← Security](06-security.md) · [Manual home](README.md) · [Next: Technology stack →](08-technology-stack.md)

Source: [TAD §9–10](../TAD.md), [TRD §6–8](../TRD.md).

## 7.1 Machines

![Deployment](images/06-deployment.svg)

| Machine | Specification | Runs |
|---|---|---|
| **Main host** | 16 cores · **32 GB RAM** · 2 × 6 GB GPU · 2 × 2 TB NVMe (RAID 1) · Ubuntu Server LTS · NVIDIA Container Toolkit | nginx, all services, media-worker (GPU), Kafka ×3, Apicurio, Redis, **mongo1 (primary)**, Prometheus + Alertmanager, staging, file volume |
| **Raspberry Pi 5 A** | 8 GB (16 GB recommended) · 1 TB NVMe SSD · active cooling · Ubuntu Server arm64 | **mongo2** (secondary, priority 1) |
| **Raspberry Pi 5 B** | Same as A | **mongo3** (secondary, priority 1) + backup job |
| **UPS** | ≥ 15 min for all three machines | Clean shutdown on power loss |

**Replica set behaviour:**
- Any single member can fail and writes continue (the other two still form a majority).
- If the host fails, a Pi becomes primary. The data is safe, but the services also run on the host, so the platform is down until the host is restored.
- When the host comes back, it takes over as primary automatically (priority 10).
- MongoDB requires a **Pi 5** (a Pi 4 can't run current versions), and the database must be on an SSD, never an SD card.

## 7.2 Memory budget (main host)

| Component | RAM |
|---|---|
| OS + Docker | 2 GB |
| MongoDB primary (6 GB cache) | 8 GB |
| Kafka ×3 | 5 GB |
| Redis, Apicurio, nginx | 2 GB |
| Services (6 × 2 replicas) | 3 GB |
| media-worker | 2 GB |
| Prometheus, Alertmanager, exporters | 2 GB |
| ClamAV | 1–1.5 GB |
| **Production subtotal** | **25–25.5 GB** |
| Staging (reduced, on demand) | 4–6 GB |
| **Total** | **29.5–31.5 GB of 32 GB**: a 64 GB upgrade is strongly recommended |

Every container has a `mem_limit`. Staging is stopped during busy periods and load tests. If memory stays above 85%, upgrade the host to 64 GB.

**GPUs:** one media-worker replica is pinned to each GPU. If a GPU is unavailable, the worker falls back to the CPU.

## 7.3 Networks and firewall

![Networks](images/07-networks.svg)

| Network | Members |
|---|---|
| `edge` | nginx only (ports 80/443 published) |
| `app` | nginx + services |
| `data` (internal) | services, MongoDB, Kafka, Redis |

MongoDB port 27017 is reachable only from the host and the Pis' fixed IPs (ufw/nftables). The Pis must be on the same LAN, with latency under 2 ms.

## 7.4 Compose projects

| Host | Project | Contents |
|---|---|---|
| Main host | `sia-prod` | Everything in §7.1 for the host |
| Main host | `sia-staging` | 1 replica per service, 1 Kafka broker, single-node replica set; anonymised data |
| Pi A | `sia-db-a` | mongo2, node-exporter |
| Pi B | `sia-db-b` | mongo3, node-exporter, backup job |

**Scaling:** `docker compose up -d --scale order-svc=4`. nginx finds the new replicas through Docker DNS. Kafka consumers can scale up to the number of partitions in a topic.

## 7.5 Environments and CI/CD

| Environment | Where | Data |
|---|---|---|
| Local | Developer machine (`compose.dev.yml`) | Seeded test data |
| CI | GitHub Actions | Temporary containers created per test run |
| Staging | Main host, separate Compose project | Anonymised copy of production |
| Production | Main host + 2 Pis | Live |

**CI:** lint → type-check → unit → integration (testcontainers) → contract (Schemathesis) → security scans → images tagged with the git SHA → GHCR.

**Release:**
1. Run database migrations once.
2. Update services one at a time with `docker compose up -d --no-deps <svc>`, waiting for each to pass `/health/ready` before the next.
3. **Rollback:** redeploy the previous SHA. Migrations must allow this: add new fields first, and remove old ones only in a later release.

## 7.6 Monitoring and alerts

| Concern | Tool |
|---|---|
| Metrics | **Prometheus** (built-in web UI) scraping each service's `/metrics` + node, MongoDB, Kafka and Redis exporters |
| Alerts | **Alertmanager** → email via the CIMH mail server |
| Logs | JSON to stdout; Docker `local` log driver with rotation; `docker compose logs <svc> \| jq`; follow one request by its `traceId` |
| Health | `/health/live`, `/health/ready` on every service; Docker healthchecks |

**Alert rules:**
- a new unhandled exception type
- error rate > 1%
- p95 latency above target
- a message in a DLQ
- consumer lag > 1,000
- outbox backlog older than 1 min
- a replica set member down, or a Pi becoming primary
- disk > 80%
- memory > 85%
- a TLS certificate expiring within 14 days

## 7.7 Backups and recovery

| Item | Value |
|---|---|
| MongoDB | Nightly `mongodump` (or Percona Backup) taken **from Pi B (a secondary)** |
| Files | `/srv/sia-data` backed up nightly with restic |
| Destination | Encrypted restic repository at **another CIMH site** |
| Targets | RPO ≤ 24 h · RTO ≤ 4 h |
| Testing | Full restore tested every quarter |

## 7.8 Transition from the legacy Flask app

![Legacy transition](images/22-legacy-transition.svg)

**Staged testing, single data cut-over.** v2 is tested on staging route group by route group, but production data moves **once**, in a ~45-minute maintenance window: freeze legacy → final dump → migrate (M01–M09) → verify → go/no-go → switch all `/api/*` routes, the new SHOP/SIA and the mobile app together. Legacy stays read-only for 30 days (rollback allowed within 48 h). Full runbook: [Chapter 13](13-data-migration.md) and the [Data Migration Plan](../MIGRATION_PLAN.md).
## Run books (P9)

Five operating documents, written in P9 from the built platform (source: `docs/runbooks/`):

| Run book | Covers |
|---|---|
| Deployment and release | PR → `main` → signed images → `deploy.sh prod <service> <digest>` with automatic rollback; release checklist; web and mobile builds; edge and certificates |
| Operations | Daily, weekly and monthly checks; common tasks (restart, scale, logs, alert email); secrets rotation; measured capacity per service |
| Backup and disaster recovery | Nightly `mongodump --oplog` + files into restic (30 daily, 12 monthly); scenarios from one Pi lost to total loss, ransomware and power cuts (manual LUKS unlock); RPO 24 h, RTO 4 h; test log |
| Monitoring and alerting | What Prometheus scrapes; every alert with its meaning and first steps; the TR-OBS-3 alerts still missing |
| Incident response | Classify, contain, investigate, recover, notify (Data Protection Act 2019), blameless post-mortem template |
