FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SOLAMON_CONFIG=/etc/solamon/bootstrap.yaml

WORKDIR /app

COPY packages/edge_agent/pyproject.toml /tmp/edge_agent/pyproject.toml
COPY packages/edge_agent/src /tmp/edge_agent/src

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir /tmp/edge_agent

CMD ["python", "-m", "edge_agent"]
