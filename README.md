# Pulse Data Engine

Social listening data acquisition platform — modular monolith (Phases 1–8).

**Hard constraints:** public / permitted sources only; no CAPTCHA, paywall, or auth bypass; honor ToS, rate limits, and deletion requests. **Reddit stays disabled.**

## Quick start

```bash
cp .env.example .env
docker compose up --build
pip install -e ".[dev]" && pytest -q
```

Services: **api**, **worker**, **jetstream**, **postgres**, **redis**, **clickhouse**.

## Phase 8 — Mastodon + YouTube

### Mastodon (per-instance)

- Configured against a single `instance_url` — **search is instance-local, never federation-wide**
- Public / hashtag timelines without a token; `/api/v2/search` when `access_token` is set
- Per-instance rate limiting; optional SSE public streaming (`stream_public`)
- Health via `/api/v1/instance`

```python
from pulse.connectors.mastodon import MastodonConnector
# MastodonConnector({"instance_url": "https://mastodon.social", "hashtag": "opensource"})
```

### YouTube (Data API v3 only)

- Official YouTube Data API — search, video metadata, comments where permitted
- Pagination via `pageToken`; **quota ledger** charges units per method (search.list=100, …)
- Refuses work when the configured daily budget would be exceeded — never assumes unlimited access
- Requires `api_key` (never logged); tests use mocked fixtures

```python
from pulse.connectors.youtube import YouTubeConnector
# YouTubeConnector({"api_key": "...", "default_query": "brand", "daily_quota_units": 10000})
```

Set `PULSE`-style secrets in `.env` for local runs; unit tests do not need live credentials.

## Phase 7 — Usage, cost, monitoring

`/api/v1/usage`, configurable (non-vendor) pricing, Prometheus series, secret-redacting logs, `/ready`.

## Earlier phases

- **6:** GDELT + ClickHouse · **5:** normalize/dedupe/match · **4:** workers/DLQ · **3:** Bluesky · **2:** RSS SDK · **1:** foundation

## Status

Phases 1–8 done. **Not here:** security audit / load test (Phase 9). Reddit remains disabled.
