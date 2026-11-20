# Pulse Data Engine

Social listening data acquisition platform — modular monolith foundation (Phase 1).

Collects publicly accessible data from permitted sources, normalizes and stores mentions, and exposes multi-tenant REST APIs. Later phases add connectors (RSS → Bluesky → GDELT → Mastodon → YouTube), workers, and ClickHouse analytics.

**Hard constraints:** public / permitted sources only; no CAPTCHA, paywall, or auth bypass; honor ToS, rate limits, and deletion requests.

## Stack (Phase 1)

- Python 3.12+
- FastAPI + Pydantic v2
- SQLAlchemy 2 + Alembic
- PostgreSQL 16 + Redis 7
- Docker Compose
- Structured JSON logging + Prometheus `/metrics` stub
- Pytest

## Repository layout

```
src/pulse/          # Application package (modular monolith)
  api/              # Health, metrics, /api/v1 stubs
  db/               # Engine, session, declarative base
  models/           # organizations, users, members, projects
  modules/          # Reserved for connectors / ingestion (later)
  config.py         # Pydantic Settings (env-driven)
  logging.py        # JSON logging
  main.py           # FastAPI app factory
alembic/            # Migrations
tests/              # Smoke tests (no live external APIs)
docker-compose.yml  # api + postgres + redis
```

## Quick start (Docker Compose)

Prerequisites: Docker and Docker Compose.

```bash
cp .env.example .env   # optional; compose overrides DB/Redis hosts
docker compose up --build
```

Services:

| Service  | URL / port        |
|----------|-------------------|
| API      | http://localhost:8000 |
| OpenAPI  | http://localhost:8000/docs |
| Health   | http://localhost:8000/health |
| Metrics  | http://localhost:8000/metrics |
| Postgres | localhost:5432 (`pulse` / `pulse` / `pulse`) |
| Redis    | localhost:6379 |

On API start, the container runs `alembic upgrade head`, then serves Uvicorn on `0.0.0.0:8000`.

Stop:

```bash
docker compose down
```

## Local development (without Compose)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Point `PULSE_POSTGRES_*` and `PULSE_REDIS_URL` at running Postgres and Redis, then:

```bash
alembic upgrade head
uvicorn pulse.main:app --reload --host 0.0.0.0 --port 8000
```

## Configuration

All settings use the `PULSE_` prefix (see `.env.example`):

- Postgres, Redis
- ClickHouse + S3 stubs (wired for later phases)
- JWT secret / algorithm (change before any real auth)

## Tests

Smoke tests do **not** call live external APIs and do not require Docker:

```bash
pip install -e ".[dev]"
pytest -q
```

## Phase 1 status

Done: package layout, settings, Compose, core tenant models + Alembic, FastAPI skeleton (`/health`, `/metrics`, `/api/v1` stubs), JSON logging, pytest, README.

**Out of scope here:** connectors, Celery workers, ClickHouse tables, brand matching, ingestion pipeline (Phases 2–9).
