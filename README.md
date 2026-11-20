# Pulse Data Engine

Social listening data acquisition platform — modular monolith (Phases 1–7).

**Hard constraints:** public / permitted sources only; no CAPTCHA, paywall, or auth bypass; honor ToS, rate limits, and deletion requests.

## Quick start

```bash
cp .env.example .env
docker compose up --build
pip install -e ".[dev]" && pytest -q
```

Services: **api**, **worker**, **jetstream**, **postgres**, **redis**, **clickhouse**.

## Phase 7 — Usage, cost, monitoring

### Usage metrics

Tracked per operation: HTTP requests, bytes, items collected / accepted / rejected / duplicates, worker time, retries, storage, network, AI tokens (stub-friendly).

- Postgres: `usage_records`, `source_costs`
- In-process recorder + REST under `/api/v1/usage`
- Bridge from connector `RequestAccounting` via `UsageRecorder.record_from_accounting`

### Configurable pricing

Prices live in `source_costs` / `PricingCatalog`. **Fixture prices are synthetic** (`pricing_label=fixture`) for tests/demos only — never treated as verified vendor API list prices.

```bash
# Load fixture catalog (local/demo)
curl -X POST http://localhost:8000/api/v1/usage/pricing/fixture

# Record usage + cost rollups
curl -X POST http://localhost:8000/api/v1/usage/records -H 'content-type: application/json' \
  -d '{"source":"gdelt","operation":"search","http_requests":2,"items_accepted":100}'
curl 'http://localhost:8000/api/v1/usage/costs?group_by=source'
```

Rollups: cost per **source / project / org**, **per 1k mentions**, and **per AI analysis**.

### Prometheus + health

`/metrics` exposes connector_*, ingestion_*, queue_*, checkpoint_lag, usage/cost, AI token series. `/health` (liveness) and `/ready` (readiness). Structured JSON logs redact password/secret/token/api_key/authorization fields.

## Earlier phases

- **6:** GDELT DOC 2.0 + ClickHouse analytics (shared `mention_catalog`, project-scoped `project_mentions`)
- **5:** Normalize, dedupe, brand matching
- **4:** Celery queues, retry, DLQ
- **3:** Bluesky Jetstream v2
- **2:** Connector SDK + RSS/Atom
- **1:** Foundation (FastAPI, Postgres, Docker)

## Status

Phases 1–7 done. **Not here:** Mastodon/YouTube (Phase 8), security audit / load test (Phase 9).
