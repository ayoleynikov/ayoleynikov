# Pulse Data Engine

Social listening data acquisition platform — modular monolith (Phases 1–3).

Collects publicly accessible data from permitted sources, normalizes and stores mentions, and exposes multi-tenant REST APIs. Later phases add GDELT, full queue matrix, matching, and ClickHouse analytics.

**Hard constraints:** public / permitted sources only; no CAPTCHA, paywall, or auth bypass; honor ToS, rate limits, and deletion requests.

## Stack

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic
- PostgreSQL 16, Redis 7, Celery (RSS), asyncio Jetstream consumer
- Connector SDK + RSS/Atom + Bluesky Jetstream (`feedparser`, httpx, websockets)
- Structured JSON logging, Prometheus `/metrics` stub, Pytest

## Repository layout

```
src/pulse/
  api/                 # Health, metrics, /api/v1 (+ connectors)
  connectors/          # SDK + rss/ + bluesky/
  ingestion/           # Mention/checkpoint store path
  workers/             # Celery, pulse-poll-rss, pulse-jetstream
  db/ models/          # Tenant + checkpoint/mention/feed tables
alembic/ tests/
docker-compose.yml     # api + worker + jetstream + postgres + redis
```

## Quick start (Docker Compose)

```bash
cp .env.example .env
docker compose up --build
```

| Service    | Notes |
|------------|--------|
| API        | http://localhost:8000 — migrations on start |
| Worker     | Celery `source.poll` (RSS) |
| Jetstream  | `pulse-jetstream` long-running Bluesky consumer |
| Postgres   | localhost:5432 (`pulse`/`pulse`/`pulse`) |
| Redis      | localhost:6379 |

## RSS / Atom (Phase 2)

```bash
pulse-poll-rss https://example.com/feed.xml
# or set PULSE_RSS_FEEDS / feed_sources + Celery worker
```

## Bluesky Jetstream (Phase 3)

Long-running asyncio process; public firehose only (no auth bypass).

```bash
alembic upgrade head
pulse-jetstream
# prefer a region:
pulse-jetstream --region us-east-1
# or explicit endpoints:
pulse-jetstream --endpoint wss://jetstream1.us-east.bsky.network/subscribe
```

Behavior:

- Parses legacy `/subscribe` JSON and Jetstream v2 `subscribeEvents` message frames
- Create/update posts → upsert `mentions`; delete ops → soft-delete (`deleted_at`)
- Cursor saved in `connector_checkpoints` **only after** durable store succeeds
- Regional endpoint failover + exponential reconnect backoff
- Registered as connector `bluesky` with `streaming` capability

Compose service: `jetstream` (depends on healthy API/migrations).

## Configuration

See `.env.example` (`PULSE_RSS_FEEDS`, `PULSE_BLUESKY_REGION`, Postgres/Redis/JWT stubs).

## Tests

Fixture-based (mocked HTTP / WebSocket); no live credentials required:

```bash
pip install -e ".[dev]"
pytest -q
```

## Status

- **Phase 1:** foundation — done
- **Phase 2:** Connector SDK + RSS/Atom — done
- **Phase 3:** Bluesky Jetstream v2 consumer — done
- **Not here:** GDELT, full Phase 4 queue matrix, brand matching, ClickHouse
