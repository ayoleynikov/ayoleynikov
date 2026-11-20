# Pulse Data Engine

Social listening data acquisition platform — modular monolith (Phases 1–6).

**Hard constraints:** public / permitted sources only; no CAPTCHA, paywall, or auth bypass; honor ToS, rate limits, and deletion requests.

## Quick start

```bash
cp .env.example .env
docker compose up --build
pip install -e ".[dev]" && pytest -q
```

Services: **api**, **worker**, **jetstream**, **postgres**, **redis**, **clickhouse**.

## Phase 6 — GDELT + ClickHouse

### GDELT DOC 2.0 connector

- Registered as `gdelt` (search + historical + incremental fetch)
- Query / time windows (`startdatetime`/`enddatetime` or `timespan`), pagination via cursors
- Client-side rate limit + retries; empty/HTML responses fail loudly (no fake articles)
- ArtList fields only — full body is **not** invented

```python
from pulse.connectors.gdelt import GDELTConnector
from pulse.connectors.types import SearchQuery
# await GDELTConnector({"query": "Acme", "timespan": "24h"}).search(SearchQuery(limit=25))
```

Celery: `pulse.workers.analytics_tasks.search_gdelt` → queue `source.fetch`

### ClickHouse analytics

Tables (explicit dedup — **do not assume insert uniqueness**):

| Table | Engine | Key idea |
|-------|--------|----------|
| `mention_catalog` | ReplacingMergeTree(version) | Shared global mentions `(source, external_id)` |
| `project_mentions` | ReplacingMergeTree(version) | Tenant link `(project_id, mention_id)` |
| `mention_matches` | ReplacingMergeTree(version) | Per-project brand matches |
| `mention_analytics` | ReplacingMergeTree(version) | Per-project analytics row |
| `event_clusters` | ReplacingMergeTree(version) | Cluster scaffold |
| `hourly_metrics` | SummingMergeTree | Additive counters |

Readers needing exact uniqueness should use `FINAL` / `argMax`. Merges collapse duplicates asynchronously.

Sink after matching: `AnalyticsSink` / Celery `sink_to_clickhouse` on `analytics.aggregate`.

## Status

Phases 1–6 done. **Not here:** usage/cost engine (Phase 7), Mastodon/YouTube (Phase 8).
