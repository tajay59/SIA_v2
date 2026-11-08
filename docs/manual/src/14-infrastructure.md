# 14. Infrastructure and environments

[← Data migration](13-data-migration.md) · [Manual home](README.md) · [Next: Testing →](15-testing.md)

Source: [Infrastructure and Environment Plan](../INFRASTRUCTURE.md). Machines, VLAN and firewall, Compose services with resource limits, platform configuration, secrets, backups, environments and first-build checklist.

## 14.1 Purpose

Specifies the **machines, networks, containers and environments** the platform runs on, so DevOps can build, rebuild and scale it the same way every time. Everything here lives as code in `deploy/` (Compose files, configs, scripts); this document explains it.

## 14.2 Machines

![Deployment](images/06-deployment.svg)

| Name | Role | Hardware | OS | Notes |
|---|---|---|---|---|
| `sia-host` | Application host + MongoDB primary + staging | 16 cores · **32 GB RAM (upgrade to 64 GB strongly recommended)** · 2 × 6 GB NVIDIA GPU · 2 × 2 TB NVMe RAID 1 · 1 Gbps NIC | Ubuntu Server LTS (latest) | NVIDIA driver + NVIDIA Container Toolkit; Docker Engine + Compose |
| `sia-pi-a` | MongoDB secondary | Raspberry Pi 5 · 8 GB (16 GB recommended) · 1 TB NVMe (M.2 HAT) · active cooler · 27 W PSU | Ubuntu Server LTS arm64 | LUKS on the NVMe; boots from NVMe |
| `sia-pi-b` | MongoDB secondary + backup runner | Same as Pi A | Same | Runs nightly backups |
| UPS | Power | ≥ 15 min for all three + switch | — | USB/network signal → `nut` shuts machines down cleanly |
| Backup target | Off-site copy | Storage at another CIMH site (≥ 3 TB) | — | restic repository over SFTP/REST |

### 2.1 Base OS setup (all three machines, scripted in `deploy/bootstrap/`)
- Unattended security updates (reboots in the maintenance window); `chrony` time sync (replica set and tokens need correct time).
- SSH: keys only, no root login, `AllowUsers` ops accounts, fail2ban.
- Users: `ops` (sudo), `deploy` (in `docker` group; runs the **self-hosted GitHub Actions runner** service, which may only execute `deploy/scripts/*`; the runner is limited to the `cimh/stores` repository and to the `staging`/`production` environments; build and test jobs run on GitHub-hosted runners, only deploy jobs run here).
- Host firewall: `ufw` default deny inbound (rules in §3.3).
- Docker daemon: `live-restore`, log driver `local` (max-size 50m, max-file 10), userns-remap where compatible.
- Disk: LUKS full-disk on the Pis (TR-SEC-10); key unlock via a TPM-less keyfile on a USB token **or** manual unlock after reboot (decision §11); data on `/srv`.
- Host directories: `/srv/sia-data` (files), `/srv/mongo`, `/srv/kafka/{1,2,3}`, `/srv/redis`, `/srv/prometheus`, `/srv/backup-cache`, all `0750`.

## 14.3 Network

### 3.1 Addressing (dedicated VLAN, TR-SEC-12)
| Host | VLAN IP (to be assigned by CIMH IT) | DNS name |
|---|---|---|
| `sia-host` | `10.x.y.10` | `sia-host.cimh.local` |
| `sia-pi-a` | `10.x.y.11` | `sia-pi-a.cimh.local` |
| `sia-pi-b` | `10.x.y.12` | `sia-pi-b.cimh.local` |

Replica-set members are addressed **by DNS name** (`sia-host:27017`, …) so IPs can change without reconfiguring MongoDB. The host also has an interface (or routed path) reachable from the CIMH LAN/Internet for ports 80/443 only.

### 3.2 Public names and TLS
| Name | Points to | Certificate |
|---|---|---|
| `store.cimh.edu.bb` | `sia-host` 443 | Let's Encrypt (certbot, HTTP-01, auto-renew) |
| `sia.cimh.edu.bb` | `sia-host` 443 | Let's Encrypt |
| `staging-store.cimh.edu.bb`, `staging-sia.cimh.edu.bb` | `sia-host` 443 (separate server blocks) | Let's Encrypt; **access limited to the CIMH LAN** (nginx `allow`/`deny`) |

Internal TLS (MongoDB replication, Kafka, Redis): a small **private CA** (`deploy/pki/`, step-ca or openssl scripts) issues certificates for `sia-host`, `sia-pi-a`, `sia-pi-b` and service clients; 1-year validity, renewal reminder alert at 30 days.

### 3.3 Firewall rules

![Networks](images/07-networks.svg)
| From | To | Port | Purpose |
|---|---|---|---|
| Internet / LAN | sia-host | 80, 443 | nginx (80 only redirects + ACME) |
| Ops workstations (LAN) | all three | 22 | SSH |
| sia-host ↔ sia-pi-a ↔ sia-pi-b | each other | 27017 | MongoDB replication (TLS + keyfile) |
| sia-host | sia-pi-a, sia-pi-b | 9100 | Prometheus node-exporter scrape |
| sia-pi-b | Backup target | 22 / 8000 | restic (SFTP or REST) |
| sia-host | CIMH mail server | 587 | SMTP submission (TLS) |
| sia-host | Internet | 443 | Image pulls (GHCR), OS updates, Let's Encrypt, HIBP range API |
| GitHub (outbound only) | — | — | The **self-hosted GitHub Actions runner** on sia-host connects **out** to GitHub over 443; no inbound port is opened for CI |
| *everything else* | — | — | **deny** |

Kafka (9092/9093), Redis (6379), Prometheus (9090), Alertmanager (9093) and all service ports are **only on Docker networks**, never published.

## 14.4 Compose layout

```
deploy/
  compose.prod.yml          # sia-host production (project: sia-prod)
  compose.staging.yml       # sia-host staging (project: sia-staging)
  compose.dev.yml           # developer laptops
  compose.pi.yml            # sia-pi-a / sia-pi-b (project: sia-db-a / sia-db-b; env selects role)
  env/                      # non-secret settings per environment (*.env)
  secrets/                  # NOT in git; created by bootstrap from the password manager
  nginx/                    # nginx.conf, sites/, snippets/ (security headers, rate limits, X-Accel)
  mongo/                    # mongod.conf, init-replset.js, roles.js (custom per-service roles)
  kafka/                    # server.properties template, topics.yaml, acls.yaml
  redis/                    # redis.conf, users.acl
  prometheus/               # prometheus.yml, rules/*.yml, alertmanager.yml
  pki/                      # private CA scripts
  scripts/                  # deploy.sh, migrate.sh, backup.sh, restore.sh, rotate-secret.sh
  bootstrap/                # host setup (ansible playbook or shell)
```

### 4.1 Production services (`compose.prod.yml` on `sia-host`)

Every service: `restart: unless-stopped`, `read_only: true` (+ `tmpfs: /tmp`), `user: 10001`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `healthcheck` on `/health/ready`, logging `local` (TR-SEC-8).

| Service | Image | Replicas | CPUs | mem_limit | Networks | Volumes / notes |
|---|---|---|---|---|---|---|
| nginx | `nginx` (pinned) | 1 | 1.0 | 256 MB | edge, app | certs, `/srv/sia-data/public` (ro), `/srv/sia-data/protected` (ro, internal location), SPA builds |
| certbot | `certbot/certbot` | 1 (cron loop) | 0.1 | 64 MB | edge | certs |
| identity-svc | `ghcr.io/cimh/identity-svc@sha256:…` | 2 | 0.5 | 256 MB | app, data | — |
| catalog-svc | `…/catalog-svc` | 2 | 0.5 | 256 MB | app, data | — |
| inventory-svc | `…/inventory-svc` | 2 | 0.5 | 256 MB | app, data | — |
| order-svc | `…/order-svc` | 2 | 0.5 | 256 MB | app, data | — |
| document-svc | `…/document-svc` | 2 | 1.0 | 384 MB | app, data | `/srv/sia-data/protected` (rw) |
| notification-svc | `…/notification-svc` | 2 | 0.25 | 256 MB | data | SMTP egress |
| outbox-relay-* | `…/outbox-relay` (one per service) | 1 each (6) | 0.1 | 64 MB | data | leader lock in Redis |
| media-worker | `…/media-worker` | 2 (GPU 0, GPU 1) | 2.0 | 1 GB | data | `/srv/sia-data/public` (rw); `deploy.resources.reservations.devices` GPU |
| clamav | `clamav/clamav` | 1 | 1.0 | 1.5 GB | data | signature volume; `freshclam` daily |
| kafka1–3 | `apache/kafka` (KRaft) | 3 | 1.0 each | 1.5 GB each (heap 1 GB) | data | `/srv/kafka/n` |
| apicurio | `apicurio/apicurio-registry` | 1 | 0.5 | 512 MB | data | stores schemas in Kafka (`kafkasql`) |
| redis | `redis` | 1 | 0.5 | 512 MB (`maxmemory 384mb`, `allkeys-lru` off → `noeviction` for revocations) | data | `/srv/redis` (AOF) |
| mongo1 | `mongo` | 1 | 4.0 | 8 GB (`wiredTigerCacheSizeGB: 6`) | data | `/srv/mongo`; port 27017 bound to the VLAN IP only |
| prometheus | `prom/prometheus` | 1 | 0.5 | 1.5 GB | data, app | `/srv/prometheus` (retention 30 d) |
| alertmanager | `prom/alertmanager` | 1 | 0.1 | 128 MB | data | SMTP to CIMH mail |
| exporters | node, mongodb, kafka, redis | 1 each | 0.1 | 64 MB each | data | node-exporter uses host network/pid read-only |
| **Total limits** | | | | **≈ 22.9 GB** + OS/Docker ≈ 2 GB = **≈ 25 GB** | | matches TRD §6.3 |

### 4.2 Docker networks
| Network | Driver / options | Members |
|---|---|---|
| `edge` | bridge | nginx, certbot; ports 80/443 published |
| `app` | bridge, `internal: true` | nginx, HTTP services, prometheus |
| `data` | bridge, `internal: true` | services, relays, workers, mongo1, kafka, redis, clamav, apicurio, prometheus, exporters |

mongo1 additionally publishes `10.x.y.10:27017` (VLAN interface only) for replication with the Pis.

### 4.3 Staging (`compose.staging.yml`, project `sia-staging`, same host)
1 replica per service; 1 Kafka broker; single-node replica set (its own `mongo-staging`, port not published); no media-worker GPU (CPU fallback); ClamAV is a mock unless uploads are being tested (then its own small instance); memory ≈ 4–6 GB total. **Started on demand** (`docker compose -p sia-staging up -d`) and stopped otherwise (TRD §6.3). Data: anonymised copy of production (script masks names, emails, phones, addresses).

### 4.4 Pis (`compose.pi.yml`)
| Service | Limits | Notes |
|---|---|---|
| mongo (mongo2 / mongo3) | 6 GB, `wiredTigerCacheSizeGB: 3` | arm64 image; port 27017 on VLAN IP; data on LUKS NVMe |
| node-exporter | 64 MB | |
| backup (Pi B only) | 512 MB | `mongodump --readPreference=secondary` + restic; cron 02:00 |

## 14.5 Platform configuration

### 5.1 MongoDB replica set
```js
// deploy/mongo/init-replset.js (run once on sia-host)
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "sia-host.cimh.local:27017",  priority: 10 },
    { _id: 1, host: "sia-pi-a.cimh.local:27017", priority: 1 },
    { _id: 2, host: "sia-pi-b.cimh.local:27017", priority: 1 }
  ],
  settings: { electionTimeoutMillis: 10000 }
})
```
- `mongod.conf`: `net.tls.mode: requireTLS` (private CA), `security.authorization: enabled`, `security.clusterAuthMode: x509` (or keyfile), `replication.replSetName: rs0`.
- Users and custom roles from `deploy/mongo/roles.js`: `svc_identity`, `svc_catalog`, `svc_inventory`, `svc_order` (collection-scoped, BSD §3.1), `svc_backup` (`backup`), `svc_migrate` (temporary), `admin_ops`.
- Connection string (services): `mongodb://svc_x:<secret>@sia-host.cimh.local,sia-pi-a.cimh.local,sia-pi-b.cimh.local/inventory?replicaSet=rs0&tls=true&w=majority&retryWrites=true&maxPoolSize=50`.

### 5.2 Kafka (KRaft, 3 brokers)
- Combined controller+broker nodes, `KAFKA_PROCESS_ROLES=broker,controller`, cluster id generated once.
- Listeners: `SASL_SSL` internal on the `data` network only; SCRAM-SHA-512 principals per service (TR-SEC-7).
- Defaults: `default.replication.factor=3`, `min.insync.replicas=2`, `auto.create.topics.enable=false`, `log.retention.hours=168`.
- `topics.yaml` (TAD §5.3 partitions/retention, compaction for `identity.user.events`, `catalog.product.events`) and `acls.yaml` (producer = owning service only; consumer groups per service), applied by an idempotent `kafka-setup` job on deploy.

### 5.3 Redis
- `appendonly yes`, `appendfsync everysec`, `maxmemory 384mb`, `maxmemory-policy noeviction` (revocation data must not be evicted).
- ACL users per service (`users.acl`), `default` user disabled; key prefixes per service (`id:`, `ord:` …) enforced by ACL patterns.

### 5.4 nginx
- Sites: `store`, `sia`, `staging-*`; snippets: `security-headers.conf` (CSP, HSTS, etc.), `rate-limits.conf` (TRD TR-SEC-5), `api-upstreams.conf` (Docker DNS `resolver 127.0.0.11 valid=10s`), `protected-files.conf` (`location /_protected/ { internal; alias /srv/sia-data/protected/; }`).
- Caching: hashed SPA assets `immutable` 1 y; `index.html` no-cache; `/media/products/` 30 d.

### 5.5 ClamAV
`clamd` container on `data`; document-svc streams uploads via `INSTREAM`; `freshclam` daily; alert if signatures older than 48 h. Uploads fail closed (503) while clamd is down. Staging-lite runs without ClamAV (`SCAN_ENABLED=false`, not enough memory on the shared box).

## 14.6 Secrets and configuration

| Kind | Mechanism |
|---|---|
| Secrets (passwords, keys, tokens) | Docker **secrets** (files under `deploy/secrets/`, `0400`, owned by root), mounted at `/run/secrets/*`; services read `*_FILE` env vars |
| Non-secret config | `deploy/env/<env>.env` committed (URLs, feature flags, limits) |
| Source of record | CIMH password manager (vault entry per secret), restored by `bootstrap` |
| Rotation | `deploy/scripts/rotate-secret.sh <name>` (writes new secret, rolling restart, verifies health); schedule in SECURITY §7 |

## 14.7 Backups and restore

| What | How | When | Retention |
|---|---|---|---|
| MongoDB | `mongodump --oplog` from **Pi B (secondary)** → restic | Nightly 02:00 | 30 daily + 12 monthly |
| Files `/srv/sia-data` | restic from sia-host (incremental) | Nightly 02:30 | Same |
| Configs `deploy/` + secrets | Git (configs); encrypted secrets export → restic | On change + nightly | Same |
| Restore test | `deploy/scripts/restore.sh` into staging; checks counts and opens sample files | **Quarterly** (logged) | — |

Alerts: backup age > 26 h; restic check failure; repository size growth > 20 %/week.

## 14.8 Monitoring endpoints
Prometheus scrapes: services `/metrics`, node-exporters (host, Pis), mongodb-exporter (replica set health, lag), kafka-exporter (consumer lag), redis-exporter, nginx stub_status (via exporter), clamav (signature age via a small textfile exporter). Alert rules: TRD TR-OBS-3 + SECURITY §9. Prometheus UI reachable only from the CIMH LAN through nginx (`/ops/prometheus`, admin basic-auth + IP allow-list).

## 14.9 Environments

| | Local | CI | Staging | Production |
|---|---|---|---|---|
| Where | Developer machine | GitHub Actions runners | sia-host (`sia-staging`) | sia-host + Pis |
| Compose | `compose.dev.yml` | testcontainers | `compose.staging.yml` | `compose.prod.yml` + `compose.pi.yml` |
| MongoDB | single-node RS | per-test container | single-node RS | 3-member RS |
| Kafka | 1 broker, no SASL | container | 1 broker, SASL | 3 brokers, SASL+ACL |
| Data | seed script (fake) | fixtures | anonymised prod copy | live |
| TLS | self-signed | — | Let's Encrypt (LAN only) | Let's Encrypt |
| Email | Mailpit (captures) | mock | Mailpit | CIMH mail server |
| GPU | optional | none | none (CPU) | 2 GPUs |
| Deploy | manual | — | auto on merge to `main` (self-hosted runner) | manual approval (GitHub environment), run by the **self-hosted runner** |

## 14.10 Provisioning checklist (first build)

1. CIMH IT: VLAN, three IPs, DNS (`*.cimh.local`, public `store`/`sia`), firewall rules §3.3, UPS wiring.
2. Install OS on all three; run `bootstrap` (users, SSH, ufw, Docker, chrony, unattended upgrades, fail2ban; LUKS on Pis).
3. Host: NVIDIA driver + Container Toolkit; verify `docker run --gpus all nvidia/cuda… nvidia-smi`.
4. Create private CA; issue MongoDB/Kafka/Redis certs; load secrets from the password manager into `deploy/secrets/`.
5. Start Pis (`compose.pi.yml`), then mongo1; run `init-replset.js` and `roles.js`; check `rs.status()` (1 primary, 2 secondaries).
6. Start Kafka, run `kafka-setup` (topics + ACLs); start Redis, Apicurio, ClamAV.
7. Start services and nginx; obtain Let's Encrypt certs; smoke test `/health/ready` everywhere.
8. Prometheus/Alertmanager up; send a test alert email.
9. Configure backups on Pi B; run the first backup and a restore into staging.
10. Hand over to the migration (Migration Plan DR-1).

## 14.11 Scaling, capacity and maintenance

| Topic | Plan |
|---|---|
| Scale a service | `docker compose -p sia-prod up -d --scale order-svc=4` (check memory budget first) |
| Memory headroom | At 32 GB there is **no headroom** for extra replicas; the 64 GB upgrade doubles service capacity |
| Disk | Alert at 80 %; Kafka and Prometheus retention are the main levers; files grow ~1.5 TB/year at full scale, so plan disk expansion at 60 % |
| Patching | Monthly window (2nd Tuesday 18:00): OS updates, image rebuilds; Pis first, then a primary step-down (`rs.stepDown()`), patch host, step back |
| Certificates | Let's Encrypt auto-renew (alert < 14 d); private CA renew yearly (alert < 30 d) |
| Kafka/Mongo upgrades | Rolling, one node at a time, health-checked |

## 14.12 Disaster recovery

| Scenario | Effect | Recovery |
|---|---|---|
| One Pi fails | None for users (majority intact) | Replace/re-image; rejoin RS (initial sync) |
| Host fails | Platform down; data safe on Pis | Repair or rebuild host from `bootstrap` + `deploy/`; restore `/srv/sia-data` from restic; mongo1 rejoins and catches up; **RTO 4 h** |
| Host + Pis lost | Total loss | New hardware; restore MongoDB dump + files from the other CIMH site; **RPO 24 h, RTO 4 h (+ hardware)** |
| Ransomware / corruption | Data unusable | Restore from restic (append-only, so it can't be encrypted by the attacker) to the last good snapshot |

Detailed steps go in the Backup and Disaster Recovery Plan (Documentation Index #23).

## 14.12a Decisions
- Pis unlock LUKS **manually after a reboot** (ops enters the passphrase over SSH via `dropbear-initramfs`). **Confirmed.** Consequence: after a power cut, ops must unlock both Pis; with only the host up, the replica set has **no majority, so no primary and no writes at all** (the platform is effectively down) until at least one Pi is unlocked, so this is in the Operations Run Book and a reboot alert pages ops.
- Staging has its own small ClamAV only while testing uploads; otherwise uploads in staging use a ClamAV mock.

## 14.13 Open questions

| # | Question | Outcome |
|---|---|---|
| 1 | VLAN id, IP range and DNS zone | **Resolved:** CIMH IT provides them before deployment (provisioning checklist step 1 is a gate). |
| 2 | How does CI reach the host? | **Resolved:** **self-hosted GitHub Actions runner** on sia-host (outbound-only; deploy jobs only). |
| 3 | Pi LUKS unlock after reboot? | **Resolved:** manual passphrase (§12a). |
| 4 | Will the host be upgraded to **64 GB** before go-live? | **Open: undecided.** The plan works at 32 GB with the limits in §4.1 and no spare replicas; decide by migration rehearsal DR-2, after load tests show real usage. P3 input (Testing chapter, phase checks): one catalog-svc container saturates its 0.5 CPU at ~145 req/s, so the full browse target needs ~6 replicas (+1 GB) or more CPU per replica. |

## 14.14 Implementation status (P1 code, 2026-11-07)

Everything in §4–§7 and §10 steps 4–9 exists as code in `deploy/`; only the hardware and network steps (1–3) are left.

| Piece | File(s) |
|---|---|
| Private CA, server/client certs (PKCS#8 for Kafka; CA keyUsage + leaf AKI for Python 3.13 strict verification) | `deploy/pki/make-certs.sh` |
| All Docker secrets, incl. connection URLs as secrets (`MONGO_URL_FILE`, `REDIS_URL_FILE`) | `deploy/scripts/make-secrets.sh` |
| Replica set: TLS required, keyfile, SCRAM-SHA-256; init and per-service roles | `deploy/mongo/mongod.conf`, `init-replset.js`, `roles.js` |
| Redis ACL per service (key patterns from the code), default user off | `deploy/redis/redis.conf`, `render-acl.sh` |
| Kafka ×3 KRaft: CLIENT = SASL_SSL/SCRAM-SHA-512, INTERNAL and CONTROLLER = mTLS, StandardAuthorizer, no ACL = deny | `compose.prod.yml`, `deploy/kafka/setup.sh` |
| Pis and nightly backup (mongodump `--oplog` from the secondary → restic, manifest of counts) | `compose.pi.yml`, `deploy/backup/` |
| Restore with count verification against the manifest | `deploy/backup/restore.sh` |
| First build, steps 4–8 | `deploy/scripts/provision.sh` |
| catalog-svc, its relay and consumer; per-service `service_secret_<name>` files (each caller reads only its own); `/srv/sia-data/{incoming,public/products,protected}` owned by 10001; media-worker (CPU image; GPU/rembg variant built on sia-host) | `compose.prod.yml`, `make-secrets.sh`, `provision.sh` |

**Implementation notes.** The first Kafka SCRAM user can't be added through the official image's start script, so `kafka-setup` connects over the mTLS INTERNAL listener as the broker certificate (a super user) and creates every SCRAM user, topic and ACL. The Kafka image writes its config at start, so `/opt/kafka/config` is a tmpfs owned by uid 1000 and `LOG_DIR=/tmp/kafka-logs`; the root filesystem stays read-only. Compose (non-swarm) mounts secret files with the host owner and mode, so `provision.sh` gives each file to the uid that reads it; mongod refuses a keyfile it doesn't own. The localhost exception allows only `createUser`, so `roles.js` creates root first; `provision.sh` passes the user passwords to it on stdin.

**Rehearsal.** `tools/infra/rehearsal/run.sh` runs §10 steps 4–9 on one Docker host with the real files (`extends` from `compose.prod.yml`) and checks 26 assertions: 1 primary + 2 secondaries, failover to a Pi and fail-back to sia-host (priority 10), TLS required, per-service Mongo/Redis/Kafka permissions (allowed and denied), identity-svc → outbox relay → Kafka over SASL_SSL, backup from a secondary and a verified restore. CI runs it on every push to `main` (job `rehearsal`).

**MongoDB and the Linux kernel.** MongoDB 8.0.21–8.0.29 refuses to start on kernel 6.19+ (tcmalloc/rseq, SERVER-121912/SERVER-125742); 8.0.0–8.0.20 crashes there. All images are pinned to **mongo 8.0.30**, which runs on kernel ≤ 6.18 or ≥ 7.0.14 (not 6.19–7.0.13). Host OS kernels must be in those ranges; check before every kernel upgrade (bootstrap pins the kernel package).
