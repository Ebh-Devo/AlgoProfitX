# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.13.7
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ARG VCS_REF=""
ARG SOURCE_URL=""
ARG BUILD_RUN_ID=""
LABEL org.opencontainers.image.title="AlgoProfitX backend" \
      org.opencontainers.image.description="Provider-neutral AlgoProfitX FastAPI runtime" \
      org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.revision="${VCS_REF}"

ENV APP_SOURCE_SHA=${VCS_REF} \
    APP_BUILD_RUN_ID=${BUILD_RUN_ID} \
    APP_SOURCE_REPO="Ebh-Devo/AlgoProfitX" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.lock requirements-production.txt ./
RUN python -m pip install --no-cache-dir --requirement requirements-production.txt

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY --chown=app:app app ./app

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; port=os.getenv('X_ZOHO_CATALYST_LISTEN_PORT') or os.getenv('PORT', '8000'); urllib.request.urlopen('http://127.0.0.1:' + port + '/health/live', timeout=2).read()"]

CMD ["sh", "-c", "exec python -m uvicorn app.runtime:app --host 0.0.0.0 --port \"${X_ZOHO_CATALYST_LISTEN_PORT:-${PORT:-8000}}\" --workers 1 --timeout-graceful-shutdown \"${UVICORN_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS:-30}\" --no-access-log"]
