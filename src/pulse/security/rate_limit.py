"""Simple in-process API rate limiter (per client key)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class ApiRateLimiter:
    """Fixed-window style limiter: ``max_requests`` per ``window_seconds``."""

    def __init__(self, *, max_requests: int = 120, window_seconds: float = 60.0) -> None:
        if max_requests < 1 or window_seconds <= 0:
            msg = "max_requests must be >= 1 and window_seconds > 0"
            raise ValueError(msg)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
