# syntax=docker/dockerfile:1.7

# These manifest-list digests are intentionally pinned so release rebuilds do
# not silently inherit a different operating system or toolchain.
FROM node:24.13.0-bookworm-slim@sha256:4660b1ca8b28d6d1906fd644abe34b2ed81d15434d26d845ef0aced307cf4b6f AS dashboard-build
WORKDIR /src/dashboard

RUN corepack enable && corepack prepare pnpm@10.28.2 --activate
COPY dashboard/package.json dashboard/pnpm-lock.yaml dashboard/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY dashboard/ ./
RUN pnpm run build

FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS python-build
WORKDIR /AstrBot

ENV UV_PROJECT_ENVIRONMENT=/opt/astrbot-venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN python -m pip install --no-cache-dir uv==0.11.19
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY . ./
COPY --from=dashboard-build /src/dashboard/dist ./astrbot/dashboard/dist
RUN uv sync --locked --no-dev

FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS runtime
WORKDIR /AstrBot

ARG VCS_REF=unknown
ARG VERSION=unknown
ARG UV_LOCK_SHA256=unknown

ENV VIRTUAL_ENV=/opt/astrbot-venv \
    PATH="/opt/astrbot-venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        ffmpeg \
        fonts-noto-cjk \
        libavcodec-extra \
        ripgrep \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY --from=python-build /opt/astrbot-venv /opt/astrbot-venv
COPY --from=python-build /AstrBot/astrbot ./astrbot
COPY --from=python-build /AstrBot/main.py ./main.py
COPY --from=python-build /AstrBot/runtime_bootstrap.py ./runtime_bootstrap.py
COPY --from=python-build /AstrBot/pyproject.toml ./pyproject.toml
COPY --from=python-build /AstrBot/README.md ./README.md

LABEL org.opencontainers.image.source="https://github.com/AstrBotDevs/AstrBot" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.version="${VERSION}" \
      org.astrbot.uv-lock-sha256="${UV_LOCK_SHA256}"

EXPOSE 6185

CMD ["python", "main.py"]
