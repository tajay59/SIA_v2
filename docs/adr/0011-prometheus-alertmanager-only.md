# ADR-0011: Monitoring with Prometheus + Alertmanager only

- Status: Accepted (2026-11-06)
- Related: TRD (observability), TAD §10, MONITORING run book

## Context
Memory on the host is the tightest resource (29.5–31.5 GB of 32 GB). Monitoring must catch outages, errors, slowness, backlogs and certificate expiry and email someone, without a second stack to run.

## Options
1. **Prometheus + Grafana + Loki + Sentry**: dashboards, logs and error tracking; 2–3 GB more RAM and four more things to patch.
2. **Prometheus + Alertmanager only**; logs via `docker logs` (local driver with rotation).
3. **External SaaS monitoring**: sends operational data off-site; recurring cost.

## Decision
Option 2. Prometheus scrapes every service plus the node, mongodb, kafka, redis and blackbox exporters; Alertmanager emails through Gmail SMTP. Rules are unit-tested with promtool in CI. No Grafana, Loki or Sentry.

## Consequences
- No dashboards: queries use Prometheus's own UI (`/ops/prometheus/`).
- Exceptions are counted (`unhandled_exceptions_total`) and alerted, not grouped as Sentry would; details come from container logs.
- Alertmanager can't expand environment variables, so `render-config.sh` renders its config.
