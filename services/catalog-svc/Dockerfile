# syntax=docker/dockerfile:1.7
# Build context: the repository root (so packages/py-common is available).
#   docker build -f services/catalog-svc/Dockerfile -t catalog-svc .

FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY packages/py-common packages/py-common
COPY services/catalog-svc services/catalog-svc
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install ./packages/py-common ./services/catalog-svc

FROM python:3.13-slim
# TR-SEC-8: non-root uid 10001, read-only root fs (set in compose), no build tools.
# No pip at runtime: it is never used, and its vendored libs (urllib3, msgpack...) are scanner findings.
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app \
 && mkdir -p /srv/sia-data/incoming /srv/sia-data/public/products && chown -R 10001:10001 /srv/sia-data \
 && python -m pip uninstall -y -q pip \
 && rm -rf /usr/local/lib/python3.13/ensurepip
COPY --from=build /opt/venv /opt/venv
RUN rm -rf /opt/venv/lib/python3.13/site-packages/pip /opt/venv/lib/python3.13/site-packages/pip-*.dist-info /opt/venv/bin/pip*
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2).status==200 else 1)"
CMD ["gunicorn", "catalog_svc.main:build_app()", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "-w", "2", "--access-logfile", "-", "--worker-tmp-dir", "/tmp"]
