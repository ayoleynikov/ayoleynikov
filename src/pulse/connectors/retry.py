"""Retry helpers with error classification awareness."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pulse.connectors.types import ConnectorError, ConnectorErrorKind

T = TypeVar("T")


async def with_retries(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.5,
    on_retry: Callable[[], None] | None = None,
) -> T:
    """Retry transient ``ConnectorError``s with exponential backoff."""
    if max_attempts < 1:
        msg = "max_attempts must be >= 1"
        raise ValueError(msg)

    attempt = 0
    while True:
        attempt += 1
        try:
            return await operation()
        except ConnectorError as exc:
            if not exc.retryable or attempt >= max_attempts:
                raise
            if on_retry is not None:
                on_retry()
            delay = base_delay_seconds * (2 ** (attempt - 1))
            await asyncio.sleep(delay)


def classify_http_status(status_code: int, body_preview: str = "") -> ConnectorError:
    """Map HTTP status codes to classified connector errors."""
    if status_code == 304:
        return ConnectorError(
            "not modified",
            kind=ConnectorErrorKind.NOT_MODIFIED,
            retryable=False,
            status_code=status_code,
        )
    if status_code in {401, 403}:
        return ConnectorError(
            f"auth/forbidden ({status_code}): {body_preview[:200]}",
            kind=ConnectorErrorKind.AUTH,
            retryable=False,
            status_code=status_code,
        )
    if status_code == 429:
        return ConnectorError(
            "rate limited",
            kind=ConnectorErrorKind.RATE_LIMIT,
            retryable=True,
            status_code=status_code,
        )
    if 500 <= status_code < 600:
        return ConnectorError(
            f"upstream error ({status_code})",
            kind=ConnectorErrorKind.TRANSIENT,
            retryable=True,
            status_code=status_code,
        )
    if 400 <= status_code < 500:
        return ConnectorError(
            f"client error ({status_code}): {body_preview[:200]}",
            kind=ConnectorErrorKind.PERMANENT,
            retryable=False,
            status_code=status_code,
        )
    return ConnectorError(
        f"unexpected status ({status_code})",
        kind=ConnectorErrorKind.TRANSIENT,
        retryable=True,
        status_code=status_code,
    )
