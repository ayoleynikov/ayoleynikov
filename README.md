# Pulse Data Engine

Social listening data acquisition platform — modular monolith (Phases 1–9).

**Hard constraints:** public / permitted sources only; no CAPTCHA, paywall, or auth bypass; honor ToS, rate limits, and deletion requests. **Reddit stays disabled.**

## Quick start

```bash
cp .env.example .env
docker compose up --build
pip install -e ".[dev]" && pytest -q
# With API up:
python scripts/smoke_load.py --base-url http://127.0.0.1:8000
```

Services: **api**, **worker**, **jetstream**, **postgres**, **redis**, **clickhouse**.

## Phase 9 — Security & production readiness

- JWT auth (`/api/v1/auth/token` mint in dev/test only, `/auth/me`) + RBAC roles
- Tenant isolation checks (`/api/v1/tenant/check`) — cross-org denied
- SSRF guards on RSS feed URLs (block private/metadata/localhost)
- Fernet credential encryption + `connector_credentials`
- `audit_logs`, `deletion_requests` + retention policy scaffolding
- API rate limiting + secure CORS (empty allowlist by default)
- DoD checklist: [docs/production-readiness.md](docs/production-readiness.md)

## Connectors (Phases 2–8)

RSS · Bluesky Jetstream · GDELT · Mastodon (instance-local) · YouTube Data API v3. Reddit disabled.

## Usage / monitoring (Phase 7)

`/api/v1/usage`, Prometheus `/metrics`, `/health` + `/ready`, secret-redacting JSON logs.

## Status

Phases 1–9 complete in code + unit tests. See production-readiness doc for which DoD rows still need live Docker verification.
