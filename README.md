# Pulse Data Engine

Social listening data acquisition platform — modular monolith (Phases 1–2).

Collects publicly accessible data from permitted sources, normalizes and stores mentions, and exposes multi-tenant REST APIs. Later phases add Bluesky, GDELT, Mastodon, YouTube, full queue matrix, and ClickHouse analytics.

**Hard constraints:** public / permitted sources only; no CAPTCHA, paywall, or auth bypass; honor ToS, rate limits, and deletion requests.

## Stack

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic
- PostgreSQL 16, Redis 7, Celery (RSS poll worker)
- Connector SDK + RSS/Atom (`feedparser`, httpx)
- Structured JSON logging, Prometheus `/metrics` stub, Pytest

## Repository layout

```
src/pulse/
  api/                 # Health, metrics, /api/v1 (+ connectors)
  connectors/          # Connector SDK + RSS/Atom
  ingestion/           # Minimal mention/checkpoint store path
  workers/             # Celery tasks + pulse-poll-rss CLI
  db/ models/          # Tenant + checkpoint/mention/feed tables
  config.py logging.py main.py
alembic/               # Migrations
tests/                 # Unit/contract tests with fixtures
docker-compose.yml     # api + worker + postgres + redis
```

## Quick start (Docker Compose)

```bash
cp .env.example .env
docker compose up --build
```

| Service  | URL / port |
|----------|------------|
| API      | http://localhost:8000 |
| OpenAPI  | http://localhost:8000/docs |
| Health   | http://localhost:8000/health |
| Connectors | http://localhost:8000/api/v1/connectors |
| Postgres | localhost:5432 (`pulse`/`pulse`/`pulse`) |
| Redis    | localhost:6379 |
| Worker   | Celery on queue `source.poll` |

API runs `alembic upgrade head` on start.

## RSS / Atom collection (Phase 2)

### Option A — CLI (one feed)

Requires Postgres reachable with migrations applied:

```bash
pip install -e ".[dev]"
alembic upgrade head
pulse-poll-rss https://example.com/feed.xml
```

Exit code is non-zero when the connector fails (no silent empty success).

### Option B — Celery worker

1. Insert rows into `feed_sources` (project-scoped), **or** set `PULSE_RSS_FEEDS` to a comma-separated list of public feed URLs.
2. Start worker:

```bash
celery -A pulse.workers.celery_app.celery_app worker -Q source.poll --loglevel=INFO
# optional beat for the 5-minute schedule:
celery -A pulse.workers.celery_app.celery_app beat --loglevel=INFO
```

Or use `docker compose up` (includes `worker`).

### Connector behavior

- `BaseConnector`: `validate_config`, `search`, `fetch_updates`, `healthcheck`, `close`
- RSS: `If-None-Match` / `If-Modified-Since`, entry parsing, canonical URLs, checkpoints in `connector_checkpoints`
- Mentions upserted into Postgres `mentions` (interim storage before ClickHouse)
- Errors classified (`ConnectorError`); invalid feeds raise parse errors

List connectors: `GET /api/v1/connectors`

## Configuration

`PULSE_*` env vars — see `.env.example`. Phase 2 adds `PULSE_RSS_FEEDS` for env-based poll lists.

## Tests

Fixture-based; no live external API credentials required:

```bash
pip install -e ".[dev]"
pytest -q
```

## Status

- **Phase 1:** foundation (Compose, tenant schema, FastAPI skeleton) — done
- **Phase 2:** Connector SDK + RSS/Atom + checkpoints + minimal poll path — done
- **Not in this branch:** Bluesky, GDELT, full matching/dedupe, ClickHouse (Phases 3+)
