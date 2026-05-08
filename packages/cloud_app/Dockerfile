# Solamon cloud-app container.
#
# Built from the repo root so the workspace siblings (profile_loader) are in scope:
#   docker buildx build --platform linux/arm64 \
#       -t <registry>/solamon-cloud-app:vX.Y.Z \
#       -f packages/cloud_app/Dockerfile \
#       --push \
#       .
#
# At runtime the container expects: DATABASE_URL, JWT_SECRET, MQTT_HOST,
# MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, plus the bench-MVP fields
# (BENCH_SITE_SLUG, BENCH_DEVICE_ID, ACUVIM_TOPIC, HTTP_PORT). See
# cloud_app/config.py for the full Settings shape.

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# psql is required by the cloud-bootstrap script's migration step (it does
# `docker compose run --rm app psql ... -f /app/migrations/0001_initial.sql`).
# ca-certificates is needed for asyncio-mqtt TLS to the public broker.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        postgresql-client \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Workspace metadata first for layer-cache friendliness on dep-only changes.
COPY pyproject.toml /app/pyproject.toml
COPY packages/profile_loader/pyproject.toml  /app/packages/profile_loader/pyproject.toml
COPY packages/cloud_app/pyproject.toml       /app/packages/cloud_app/pyproject.toml

# Source.
COPY packages/profile_loader/src /app/packages/profile_loader/src
COPY packages/cloud_app/src      /app/packages/cloud_app/src

# Migrations + the architecture/ tree (catalog YAML + schemas + profiles).
# ProfileLoader validates each YAML against the JSON schemas alongside, so
# we need the whole directory in the container, not just the catalog.
COPY packages/cloud_app/migrations  /app/migrations
COPY architecture                   /app/architecture

# Install both workspace packages. The cloud_app package depends on
# solamon-profile-loader; we install profile_loader first so cloud_app's
# install resolves the local copy without hitting PyPI.
RUN pip install /app/packages/profile_loader \
 && pip install /app/packages/cloud_app

# Default location the seed CLI looks for the catalog when LOGICAL_METRICS_PATH
# isn't set. The seed's _repo_root() helper falls back to a layout-aware path,
# but in the container the file lives at this fixed location.
ENV LOGICAL_METRICS_PATH=/app/architecture/logical_metrics.yaml

EXPOSE 8000
CMD ["python", "-m", "cloud_app"]
