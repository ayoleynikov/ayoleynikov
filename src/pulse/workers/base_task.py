"""Pulse Celery task base — retry, idempotency, DLQ on exhaustion."""

from __future__ import annotations

from typing import Any, ClassVar

from celery import Task
from celery.exceptions import MaxRetriesExceededError

from pulse.config import get_settings
from pulse.logging import get_logger
from pulse.workers.dlq import record_dead_letter
from pulse.workers.idempotency import IdempotencyStore
from pulse.workers.retry import (
    DEFAULT_RETRY_POLICY,
    PermanentTaskError,
    RetryPolicy,
    TransientTaskError,
    is_retryable,
)

logger = get_logger(__name__)


def _sync_session():
    """Lazy sync Session for DLQ writes from Celery workers."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    settings = get_settings()
    engine = create_engine(settings.database_url_sync, pool_pre_ping=True)
    return sessionmaker(bind=engine)()


class PulseTask(Task):
    """Base task with exponential backoff, idempotency hooks, and DLQ."""

    abstract = True
    retry_policy: ClassVar[RetryPolicy] = DEFAULT_RETRY_POLICY
    idempotency_ttl_seconds: ClassVar[int] = 86_400

    autoretry_for = (TransientTaskError,)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = 5

    def delay_for_retry(self) -> float:
        return self.retry_policy.delay_for_attempt(int(self.request.retries or 0))

    def resolve_idempotency_key(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
        if kwargs.get("idempotency_key"):
            return str(kwargs["idempotency_key"])
        return None

    def on_success(self, retval: Any, task_id: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        key = self.resolve_idempotency_key(args, kwargs)
        if key and isinstance(retval, dict):
            IdempotencyStore().complete(key, retval, ttl_seconds=self.idempotency_ttl_seconds)

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        key = self.resolve_idempotency_key(args, kwargs)
        retries = int(getattr(self.request, "retries", 0) or 0)
        max_retries = int(self.max_retries if self.max_retries is not None else 0)
        exhausted = retries >= max_retries or isinstance(exc, PermanentTaskError)
        if not exhausted and is_retryable(exc):
            _best_effort_idempotency_release(key)
            return

        try:
            session = _sync_session()
            try:
                record_dead_letter(
                    session,
                    task_name=self.name or self.__class__.__name__,
                    task_id=task_id,
                    queue=(getattr(self.request, "delivery_info", None) or {}).get("routing_key"),
                    args=args,
                    kwargs={k: v for k, v in kwargs.items() if not str(k).startswith("_")},
                    exc=exc,
                    retries=retries,
                    idempotency_key=key,
                    tb=str(einfo) if einfo is not None else None,
                )
            finally:
                session.close()
        except Exception:  # noqa: BLE001 — never mask the original failure
            logger.exception("dlq_persist_failed", extra={"task_id": task_id})

        _best_effort_idempotency_release(key)


def _best_effort_idempotency_release(key: str | None) -> None:
    if not key:
        return
    try:
        IdempotencyStore().release(key)
    except Exception:  # noqa: BLE001
        logger.warning("idempotency_release_failed", extra={"key": key})

    def retry_or_dlq(self, exc: BaseException) -> None:
        """Raise retry with backoff, or escalate to permanent failure / DLQ."""
        if isinstance(exc, PermanentTaskError) or not is_retryable(exc):
            raise PermanentTaskError(str(exc)) from (exc if isinstance(exc, BaseException) else None)
        try:
            raise self.retry(
                exc=exc if isinstance(exc, Exception) else TransientTaskError(str(exc)),
                countdown=self.delay_for_retry(),
            )
        except MaxRetriesExceededError as max_exc:
            raise PermanentTaskError(str(exc)) from max_exc
