# Pulse Data Engine

Social listening data acquisition platform — modular monolith (Phases 1–4).

Collects publicly accessible data from permitted sources, normalizes and stores mentions, and exposes multi-tenant REST APIs. Later phases add brand matching, GDELT, and ClickHouse analytics.

**Hard constraints:** public / permitted sources only; no CAPTCHA, paywall, or auth bypass; honor ToS, rate limits, and deletion requests.

## Stack

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic
- PostgreSQL 16, Redis 7, Celery (bounded jobs), asyncio Jetstream consumer
- Connector SDK + RSS/Atom + Bluesky Jetstream
- Retry / idempotency / dead-letter queue (Phase 4)
- Structured JSON logging, Prometheus `/metrics` stub, Pytest

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Services: **api**, **worker** (all Celery queues), **jetstream** (asyncio), **postgres**, **redis**.

## Workers & queues (Phase 4)

Master-spec queues (wired; later stages are explicit stubs):

| Queue | Role |
|-------|------|
| `source.discovery` | discovery stub |
| `source.poll` | RSS poll (real) |
| `source.fetch` | fetch stub |
| `source.stream` | **refuses** — use `pulse-jetstream` |
| `ingestion.normalize` / `ingestion.dedupe` | Phase 5 stubs |
| `matching.brand` | Phase 5 stub |
| `processing.ai` | Phase 5 stub |
| `analytics.aggregate` | Phase 6 stub |
| `alerts.dispatch` | Phase 7 stub |
| `maintenance.cleanup` | maintenance stub |
| `dead_letter` | DLQ routing + `dead_letters` table |

**Boundary:** Celery = bounded jobs. WebSocket streams (Bluesky Jetstream) = long-running asyncio (`pulse-jetstream` / compose `jetstream`). Enforced in code (`refuse_stream_on_celery`).

Retry: exponential backoff via `PulseTask` / `RetryPolicy`. Idempotency keys in Redis. Exhausted or permanent failures → Postgres `dead_letters` (observable).

```bash
celery -A pulse.workers.celery_app.celery_app worker -Q source.poll,ingestion.normalize,... --loglevel=INFO
GET /api/v1/workers/queues
```

Shared checkpoints: `pulse.checkpoints.CheckpointService` (used by RSS + Jetstream). Advance only after durable processing.

## RSS / Bluesky

```bash
pulse-poll-rss https://example.com/feed.xml
pulse-jetstream --region us-east-1
```

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

## Status

- Phases 1–4 done (foundation, RSS, Jetstream, workers/retry/DLQ)
- **Not here:** brand matching AST, GDELT, ClickHouse
