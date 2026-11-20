"""Simple token-bucket style rate limiter for connector HTTP calls."""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Async rate limiter: at most ``rate`` requests per ``per_seconds`` window."""

    def __init__(self, *, rate: float, per_seconds: float = 1.0) -> None:
        if rate <= 0 or per_seconds <= 0:
            msg = "rate and per_seconds must be positive"
            raise ValueError(msg)
        self._interval = per_seconds / rate
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_allowed = now + self._interval
