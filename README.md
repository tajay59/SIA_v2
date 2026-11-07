# CIMH Stores v2

Monorepo for the rebuilt CIMH stores platform. The design lives in `docs/` (PRD, TRD, TAD, BSD,
API contract, APD, Design Brief, Security, Migration, Infrastructure, Test Strategy, Implementation Plan).

| Path | What |
|---|---|
| `services/*` | FastAPI services (one per bounded context). `hello-svc` is the P1 pipeline skeleton |
| `packages/py-common` | Shared Python: EdDSA JWT + JWKS auth, role/ownership dependencies, RFC 9457 errors, outbox + relay, idempotent consumer with retry/DLQ, Redis lock, JSON logs, Prometheus metrics, `create_app()` |
| `packages/event-schemas` | JSON Schema per Kafka event type, extracted from `docs/api/events.asyncapi.yaml` |
| `packages/web-api` | Typed TS clients generated from `docs/api/*.openapi.yaml` (cookie + CSRF aware) |
| `packages/web-ui` | Design tokens, Vuetify 4 theme, status chips, money/date formatters (Design Brief) |
| `web/*` | SHOP and SIA frontends (from P7) |
| `deploy/` | Compose files (dev/staging/prod), Prometheus rules, Alertmanager, deploy + smoke scripts |
| `tests/authz/matrix.yaml` | Who may call every endpoint; drives generated authz tests and the CI gate |
| `tests/transitions/*.yaml` | Status machines; drive generated legal/illegal transition tests |
| `tools/` | Matrix builder/checker, transition and authz case generators, event-schema extractor, dev seed |

## Quick start (Windows or Linux)

```bash
python -m venv .venv && . .venv/Scripts/activate        # Linux: .venv/bin/activate
pip install -e packages/py-common -e services/hello-svc -r requirements-dev.txt
pytest --cov            # unit + generated authz/transition tests, coverage gate 90 %
ruff check . && ruff format --check . && mypy
python tools/authz/check_matrix.py --app hello_svc.main:app

npm install && npm test && npm run typecheck             # web packages

docker compose -f deploy/compose.dev.yml up -d --build   # hello-svc :18000, Prometheus :19090,
                                                         # Alertmanager :19093, Mailpit :18025
docker run --rm --network sia-dev_default -v "$PWD/tools/seed:/seed:ro" cimh/hello-svc:dev \
  python /seed/seed_dev.py --mongo "mongodb://mongo:27017/?replicaSet=rs0" --reset
```

Regenerate from the contract after changing `docs/api/`:

```bash
npm run generate -w @cimh/web-api
python tools/events/extract_schemas.py
python tools/authz/build_matrix.py      # adds new endpoints; never overwrites reviewed rows
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow and rules.
