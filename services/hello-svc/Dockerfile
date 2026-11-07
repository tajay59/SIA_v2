# syntax=docker/dockerfile:1.7
# Build context: the v2/ repository root (so packages/py-common is available).
#   docker build -f services/hello-svc/Dockerfile -t hello-svc .

FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY packages/py-common packages/py-common
COPY services/hello-svc services/hello-svc
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install ./packages/py-common ./services/hello-svc

FROM python:3.13-slim
# TR-SEC-8: non-root uid 10001, read-only root fs (set in compose), no build tools.
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2).status==200 else 1)"
CMD ["gunicorn", "hello_svc.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "-w", "2", "--access-logfile", "-", "--worker-tmp-dir", "/tmp"]
