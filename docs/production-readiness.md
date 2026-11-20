# Pulse Data Engine — Production Readiness (Phase 9)

Checklist against the master MVP definition of done. Status reflects **unit/integration tests in CI** vs items that still need **live Docker Compose verification**.

## MVP Definition of Done

| Requirement | Status | Notes |
|-------------|--------|-------|
| Compose up (api, worker, jetstream, postgres, redis, clickhouse) | ⚠️ Needs live Docker | `docker-compose.yml` present; verify with `docker compose up --build` |
| FastAPI | ✅ | `/health`, `/ready`, `/docs`, `/api/v1/*` |
| Migrations | ✅ (unit) / ⚠️ live | Alembic through `20261120_0007`; run `alembic upgrade head` against Compose Postgres |
| Redis | ⚠️ Needs live Docker | Wired in Compose + Celery broker URL |
| Real RSS | ✅ code / ⚠️ live | Connector + SSRF guards; poll against a permitted public feed |
| Real Bluesky public events | ✅ code / ⚠️ live | Jetstream connector + `pulse-jetstream` service |
| Cursor recovery | ✅ | Checkpoint tests + Postgres model |
| Normalize + dedupe + brand match | ✅ | Phase 5 pipeline + tests |
| ClickHouse analytics | ✅ code / ⚠️ live | Schema + sink tests (mocked); need Compose CH for end-to-end |
| REST with real data | ⚠️ Needs live Docker | Routes exist; auth + tenant checks added in Phase 9 |
| Tenant isolation tests | ✅ | Cross-org denied (`tests/test_tenant_isolation.py`) |
| Usage tracked | ✅ | `/api/v1/usage` + fixture pricing |
| Failed tasks observable | ✅ | `dead_letters` + `/api/v1/workers/dead-letters` |
| Tests green | ✅ | Full `pytest -q` on Phase 9 branch |
| Setup docs | ✅ | README + this checklist |
| Reddit disabled | ✅ | `DISABLED_CONNECTORS` |

## Security (Phase 9)

| Control | Status |
|---------|--------|
| JWT create/verify + `/api/v1/auth/*` | ✅ |
| RBAC role hierarchy (viewer→owner) | ✅ |
| Tenant isolation (cross-org deny) | ✅ |
| SSRF blocks (private/metadata/localhost) | ✅ on RSS URL validation |
| Credential encryption (Fernet) | ✅ `connector_credentials` + seal API |
| Audit logs | ✅ table + recorder + `/api/v1/audit` |
| API rate limiting | ✅ middleware (in-process) |
| Secure CORS defaults | ✅ empty allowlist by default |
| Secret redaction in logs | ✅ (Phase 7) |
| Deletion / retention scaffolding | ✅ `deletion_requests` + retention policy |

## Smoke / load

```bash
# With API up:
python scripts/smoke_load.py --base-url http://127.0.0.1:8000 --requests 40

# Optional k6 stub (install k6 separately):
# k6 run -e BASE_URL=http://127.0.0.1:8000 - <<'EOF'
# import http from 'k6/http';
# import { check, sleep } from 'k6';
# export const options = { vus: 5, duration: '30s' };
# export default function () {
#   const res = http.get(`${__ENV.BASE_URL}/health`);
#   check(res, { 'status 200': (r) => r.status === 200 });
#   sleep(0.5);
# }
# EOF
```

## Production env notes

- Set strong `PULSE_JWT_SECRET` and `PULSE_CREDENTIALS_ENCRYPTION_KEY` (Fernet key).
- Set `PULSE_CORS_ALLOW_ORIGINS` explicitly; leave empty to deny browser cross-origin.
- Enable RSS `ssrf_resolve_dns=true` in workers for DNS-rebinding protection.
- Disable `/api/v1/auth/token` mint outside development (`env` not in development/test and `debug=false`).
- Reddit remains disabled until commercial permission.
