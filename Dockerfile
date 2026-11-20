# Pulse Data Engine API image
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PULSE_API_HOST=0.0.0.0 \
    PULSE_API_PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --upgrade pip \
    && pip install ".[dev]" \
    && pip install "psycopg[binary]>=3.2.0"

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PULSE_API_PORT}/health" || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn pulse.main:app --host ${PULSE_API_HOST} --port ${PULSE_API_PORT}"]
