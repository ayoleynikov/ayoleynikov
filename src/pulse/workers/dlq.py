"""Dead-letter queue helpers — persist and observe exhausted failures."""

from __future__ import annotations

import traceback
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse.logging import get_logger
from pulse.models.dead_letter import DeadLetter

logger = get_logger(__name__)


def record_dead_letter(
    session: Session,
    *,
    task_name: str,
    task_id: str | None,
    queue: str | None,
    args: list[Any] | tuple[Any, ...],
    kwargs: dict[str, Any],
    exc: BaseException,
    retries: int,
    idempotency_key: str | None = None,
    tb: str | None = None,
) -> DeadLetter:
    """Insert an open dead-letter row and return it."""
    row = DeadLetter(
        id=uuid4(),
        task_name=task_name,
        task_id=task_id,
        queue=queue,
        idempotency_key=idempotency_key,
        args_json=list(args),
        kwargs_json=dict(kwargs),
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        traceback=tb or "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        retries=retries,
        status="open",
        failed_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    logger.error(
        "dead_letter_recorded",
        extra={
            "task_name": task_name,
            "task_id": task_id,
            "queue": queue,
            "exception_type": row.exception_type,
            "retries": retries,
            "dead_letter_id": str(row.id),
        },
    )
    return row


def list_open_dead_letters(session: Session, *, limit: int = 100) -> list[DeadLetter]:
    stmt = (
        select(DeadLetter)
        .where(DeadLetter.status == "open")
        .order_by(DeadLetter.failed_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt).all())


def resolve_dead_letter(session: Session, dead_letter_id: Any) -> DeadLetter | None:
    row = session.get(DeadLetter, dead_letter_id)
    if row is None:
        return None
    row.status = "resolved"
    session.commit()
    return row
