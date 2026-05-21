# Bravo V6.0 — Python runtime image
# Builds the container that runs every Bravo daemon on the VPS.
#
# Single base image, switched between services via `command:` in
# docker-compose.yml. This keeps image builds cached across services.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=America/Toronto

# System deps:
#   - libpq-dev for direct Postgres connections (asyncpg for LISTEN/NOTIFY later)
#   - curl for healthchecks
#   - build-essential for any package that needs to compile (Presidio pulls one)
#   - ca-certificates + tzdata so TLS + timezone work correctly
RUN apt-get update && apt-get install --no-install-recommends -y \
        build-essential \
        libpq-dev \
        curl \
        ca-certificates \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user — Bravo never runs as root in prod.
RUN useradd --create-home --shell /bin/bash --uid 10001 bravo
WORKDIR /app

# Dependency layer first so code changes don't bust the pip cache.
COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# Application code (respects .dockerignore — see infra/.dockerignore).
COPY --chown=bravo:bravo . /app

# Pre-create runtime dirs Bravo writes to.
RUN mkdir -p /app/tmp /app/logs /app/data \
 && chown -R bravo:bravo /app/tmp /app/logs /app/data

USER bravo

# Default healthcheck: `scripts/core/self_audit.py` prints health score.
# (self_audit moved into scripts/core/ during the 2026-05 reorg.)
# Override per-service in docker-compose.yml when a different probe fits better.
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python scripts/core/self_audit.py --health-only 2>/dev/null || exit 1

# No CMD — docker-compose.yml names the daemon per service. This prevents
# accidental "run everything as one blob" which defeats observability.
