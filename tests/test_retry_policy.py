"""Retry policy and error classification tests."""

from __future__ import annotations

import pytest

from pulse.connectors.types import ConnectorError, ConnectorErrorKind
from pulse.workers.retry import (
    PermanentTaskError,
    RetryPolicy,
    TransientTaskError,
    is_retryable,
)


def test_exponential_backoff_caps() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, multiplier=2.0, max_delay_seconds=10.0)
    assert policy.delay_for_attempt(0) == 1.0
    assert policy.delay_for_attempt(1) == 2.0
    assert policy.delay_for_attempt(2) == 4.0
    assert policy.delay_for_attempt(3) == 8.0
    assert policy.delay_for_attempt(4) == 10.0
    assert policy.delay_for_attempt(10) == 10.0


def test_is_retryable_classification() -> None:
    assert is_retryable(TransientTaskError("x")) is True
    assert is_retryable(PermanentTaskError("x")) is False
    assert is_retryable(
        ConnectorError("boom", kind=ConnectorErrorKind.TRANSIENT, retryable=True)
    )
    assert (
        is_retryable(ConnectorError("nope", kind=ConnectorErrorKind.CONFIG, retryable=False))
        is False
    )


def test_idempotency_store_begin_complete_replay() -> None:
    from pulse.workers.idempotency import InMemoryIdempotencyStore

    store = InMemoryIdempotencyStore()
    key = store.make_key("demo", "a", "b")
    assert store.begin(key) is True
    assert store.begin(key) is False
    store.complete(key, {"status": "ok", "n": 1})
    assert store.get_completed(key) == {"status": "ok", "n": 1}
    store.release(key)
    assert store.begin(key) is True
