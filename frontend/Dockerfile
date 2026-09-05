# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS build
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
WORKDIR /src
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM python:3.13.7-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin app
COPY --from=build --chown=app:app /src/dist ./dist
COPY --chown=app:app server.py ./server.py
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; port=os.getenv('X_ZOHO_CATALYST_LISTEN_PORT') or os.getenv('PORT', '8000'); urllib.request.urlopen('http://127.0.0.1:' + port, timeout=2).read()"]
CMD ["python", "server.py"]
