# Pulse Data Engine

Social listening data acquisition platform — modular monolith (Phases 1–5).

**Hard constraints:** public / permitted sources only; no CAPTCHA, paywall, or auth bypass; honor ToS, rate limits, and deletion requests.

## Stack

Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL, Redis, Celery, asyncio Jetstream, Connector SDK (RSS + Bluesky), normalize/dedupe/brand matching.

## Quick start

```bash
cp .env.example .env
docker compose up --build
pip install -e ".[dev]" && pytest -q
```

## Phase 5 — normalize, dedupe, brand matching

Pipeline: **validate → normalize → dedupe (L1–L3) → brand match** (AI classify stub).

- **Normalize:** universal Mention fields; UTC; deterministic `mention_id` / content fingerprint; no invented metadata
- **Dedup:** L1 `source+external_id`, L2 canonical URL, L3 content fingerprint; L4 event-cluster **scaffold** (mentions ≠ clusters)
- **Models:** `brands`, `brand_aliases`, `competitors`, `monitoring_queries`, `mention_matches`, `event_clusters`, `mention_cluster_members`
- **Boolean AST:** `AND` / `OR` / `NOT` / `"phrases"` — evaluated in-process; **never** injected into SQL
- **Celery:** `ingestion.normalize`, `ingestion.dedupe`, `matching.brand` (real tasks in `ingestion_tasks`)

```python
from pulse.matching.ast import parse_boolean_query
from pulse.ingestion.pipeline import run_ingestion_pipeline
```

## Workers boundary

Celery = bounded jobs. Jetstream = `pulse-jetstream` asyncio process. `source.stream` Celery task refuses streaming.

## Status

Phases 1–5 done. **Not here:** GDELT, ClickHouse, full AI classification.
