# syntax=docker/dockerfile:1.7
# Build context: the repository root (so packages/py-common is available).
#   docker build -f services/notification-svc/Dockerfile -t notification-svc .

FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY packages/py-common packages/py-common
COPY services/notification-svc services/notification-svc
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install ./packages/py-common ./services/notification-svc

FROM python:3.13-slim
# TR-SEC-8: non-root uid 10001, read-only root fs (set in compose), no build tools.
# No pip at runtime: it is never used, and its vendored libs (urllib3, msgpack...) are scanner findings.
# OS security fixes published after the base image was built (e.g. zlib CVE-2026-85091); Trivy blocks HIGH.
RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app \
 && python -m pip uninstall -y -q pip \
 && rm -rf /usr/local/lib/python3.13/ensurepip
COPY --from=build /opt/venv /opt/venv
RUN rm -rf /opt/venv/lib/python3.13/site-packages/pip /opt/venv/lib/python3.13/site-packages/pip-*.dist-info /opt/venv/bin/pip*
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
USER 10001
# A Kafka worker: no HTTP port, no healthcheck (compose sets healthcheck: disable).
CMD ["python", "-m", "notification_svc.consumer"]
