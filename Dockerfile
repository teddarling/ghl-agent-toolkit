# Stage 1: build the React dashboard.
FROM node:24-alpine AS web-build
WORKDIR /build/web
# corepack reads the pinned pnpm version from package.json's packageManager field.
COPY web/package.json web/pnpm-lock.yaml ./
RUN corepack enable pnpm && pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

# Stage 2: the Python server, with the built dashboard served at /.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /usr/local/bin/
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY src/ src/
RUN uv sync --frozen --no-dev
COPY server/ server/
COPY --from=web-build /build/web/dist web/dist
ENV GHL_SERVE_WEB_DIST=/app/web/dist
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
