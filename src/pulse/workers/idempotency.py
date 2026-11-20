"""Task idempotency keys (Redis SET NX)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import redis

from pulse.config import Settings, get_settings
from pulse.logging import get_logger

logger = get_logger(__name__)

IDEMPOTENCY_PREFIX = "pulse:idempotency:"
DEFAULT_TTL_SECONDS = 86_400


class IdempotencyStore:
    """Redis-backed idempotency lock + optional result cache."""

    def __init__(self, client: redis.Redis | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = client or redis.Redis.from_url(
            self._settings.redis_url,
            decode_responses=True,
        )

    @staticmethod
    def make_key(task_name: str, *parts: Any) -> str:
        payload = json.dumps([task_name, *[str(p) for p in parts]], sort_keys=False)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{IDEMPOTENCY_PREFIX}{task_name}:{digest}"

    def begin(self, key: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
        """Acquire idempotency lock. Returns True if this is the first execution."""
        acquired = self._client.set(key, json.dumps({"status": "running"}), nx=True, ex=ttl_seconds)
        return bool(acquired)

    def complete(self, key: str, result: dict[str, Any], *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._client.set(
            key,
            json.dumps({"status": "completed", "result": result}),
            ex=ttl_seconds,
        )

    def get_completed(self, key: str) -> dict[str, Any] | None:
        raw = self._client.get(key)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if data.get("status") == "completed" and isinstance(data.get("result"), dict):
            return data["result"]
        return None

    def release(self, key: str) -> None:
        """Drop a failed/running lock so a later retry can re-acquire."""
        self._client.delete(key)


# In-memory fallback for unit tests without Redis.
class InMemoryIdempotencyStore(IdempotencyStore):
    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        # Do not call Redis parent init.
        self._client = None  # type: ignore[assignment]

    def begin(self, key: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
        if key in self._data:
            return False
        self._data[key] = json.dumps({"status": "running"})
        return True

    def complete(self, key: str, result: dict[str, Any], *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._data[key] = json.dumps({"status": "completed", "result": result})

    def get_completed(self, key: str) -> dict[str, Any] | None:
        raw = self._data.get(key)
        if not raw:
            return None
        data = json.loads(raw)
        if data.get("status") == "completed":
            return data.get("result")
        return None

    def release(self, key: str) -> None:
        self._data.pop(key, None)
