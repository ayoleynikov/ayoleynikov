"""Retry policy helpers and transient error classification."""

from __future__ import annotations

from dataclasses import dataclass

from pulse.connectors.types import ConnectorError, ConnectorErrorKind


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Exponential backoff retry policy for bounded Celery jobs."""

    max_retries: int = 5
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 600.0
    multiplier: float = 2.0
    jitter: bool = True

    def delay_for_attempt(self, retries_so_far: int) -> float:
        """Celery countdown for the next retry (retries_so_far is current retry count)."""
        delay = self.base_delay_seconds * (self.multiplier**retries_so_far)
        return float(min(delay, self.max_delay_seconds))


DEFAULT_RETRY_POLICY = RetryPolicy()


class TransientTaskError(Exception):
    """Retryable task failure."""


class PermanentTaskError(Exception):
    """Non-retryable task failure — goes to DLQ immediately (or after exhausted policy)."""


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, TransientTaskError):
        return True
    if isinstance(exc, PermanentTaskError):
        return False
    if isinstance(exc, ConnectorError):
        return bool(exc.retryable) or exc.kind in {
            ConnectorErrorKind.TRANSIENT,
            ConnectorErrorKind.RATE_LIMIT,
        }
    return False
