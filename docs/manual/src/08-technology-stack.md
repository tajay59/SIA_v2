# 8. Technology stack

[← Deployment and operations](07-deployment-operations.md) · [Manual home](README.md) · [Next: Documentation map and glossary →](09-documentation-glossary.md)

Source: [TRD §3](../TRD.md). **Every component uses its latest stable release at project start**, pinned exactly (never `latest`) and reviewed quarterly. The exception is Android, where the minimum stays at **Android 12**.

## 8.1 Backend

| Concern | Choice | Why |
|---|---|---|
| Language | Python | Existing team skills; PDF and image libraries already in use |
| Framework | FastAPI + Pydantic v2 | Async; validation built in; OpenAPI generated automatically |
| App server | Uvicorn (Gunicorn as process manager) | Standard production setup for FastAPI |
| MongoDB access | PyMongo Async API + Beanie | Official async driver; typed models |
| Kafka | aiokafka | Async; idempotent producer |
| Redis | redis-py (asyncio) | |
| Scheduled jobs | APScheduler (one leader replica via a Redis lock) | Quote expiry, reminders, purges |
| PDFs | ReportLab | Carried over from the current system |
| QR / barcodes | segno, python-barcode | |
| Images | Pillow; rembg + onnxruntime-gpu (media-worker only) | Background removal on the GPUs |
| Passwords | argon2-cffi (Argon2id) | Current best practice |
| Tokens | PyJWT (EdDSA) | Services can verify tokens with the public key only |
| Email | aiosmtplib + Jinja2 | CIMH mail server |
| Tests | pytest, pytest-asyncio, testcontainers, Schemathesis | Real MongoDB/Kafka/Redis in tests; API contract tests |
| Quality | Ruff, mypy (strict) | |

## 8.2 Web frontends (SHOP and SIA)

| Concern | Choice |
|---|---|
| Language | TypeScript (`strict: true`) |
| Framework | Vue 3 (Composition API, `<script setup lang="ts">`) |
| UI | **Vuetify 4** (one shared theme package) |
| Routing | Vue Router with **file-based routing** (routes generated from `src/pages/`) |
| State | Pinia |
| Validation | **Zod 4** (shared by forms and API response checks) + vee-validate |
| API client | Generated from OpenAPI (openapi-typescript + openapi-fetch) |
| Build | Vite, Node.js LTS, pnpm workspace |
| Tests | Vitest, Playwright, axe-core |
| Quality | ESLint, Prettier |

## 8.3 Mobile

| Concern | Choice |
|---|---|
| Language / UI | Kotlin, Jetpack Compose, Material 3 |
| Network | Retrofit + OkHttp (types generated from OpenAPI) |
| Offline | Room + WorkManager |
| Scanning | CameraX + ML Kit |
| Token storage | Android Keystore |
| Minimum OS | **Android 12 (API 31)** |

## 8.4 Platform

| Concern | Choice |
|---|---|
| Database | MongoDB Community, 3-member replica set |
| Messaging | Apache Kafka (KRaft) ×3 + Apicurio Registry |
| Cache | Redis (AOF) |
| Edge | nginx + certbot (Let's Encrypt) |
| Containers | Docker Engine + Docker Compose (**Compose only**) |
| Monitoring | Prometheus + Alertmanager + exporters (**no Grafana, Loki or Sentry**) |
| Backups | mongodump / Percona Backup + restic |
| CI/CD | GitHub + GitHub Actions + GHCR |

## 8.5 Deliberately not used

| Not used | Reason |
|---|---|
| Kubernetes / other orchestrators | Decision: Docker Compose only |
| S3 / cloud object storage | Decision: local files |
| Online payments | Business model is quote → accept |
| FedEx / DHL APIs | Tracking numbers entered by hand |
| Grafana, Loki, Sentry | Decision: Prometheus + Alertmanager only |
| Cloud CDN / WAF | Decision: nginx only at the edge |
