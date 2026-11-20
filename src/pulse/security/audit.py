"""Audit log recorder (process-local + ORM model for persistence)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from pulse.logging import get_logger
from pulse.logging import redact_secrets

logger = get_logger(__name__)


class AuditEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    action: str
    actor_user_id: UUID | None = None
    organization_id: UUID | None = None
    project_id: UUID | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditRecorder:
    """In-memory audit trail for API/tests; mirrors ``audit_logs`` table shape."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(
        self,
        action: str,
        *,
        actor_user_id: UUID | None = None,
        organization_id: UUID | None = None,
        project_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        safe_details = redact_secrets(details or {})
        event = AuditEvent(
            action=action,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            project_id=project_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=safe_details if isinstance(safe_details, dict) else {},
        )
        self._events.append(event)
        logger.info(
            "audit_event",
            extra={
                "action": action,
                "actor_user_id": str(actor_user_id) if actor_user_id else None,
                "organization_id": str(organization_id) if organization_id else None,
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )
        return event

    def list_events(
        self,
        *,
        organization_id: UUID | None = None,
        action: str | None = None,
    ) -> list[AuditEvent]:
        rows = self._events
        if organization_id is not None:
            rows = [e for e in rows if e.organization_id == organization_id]
        if action is not None:
            rows = [e for e in rows if e.action == action]
        return list(rows)


_AUDITOR: AuditRecorder | None = None


def get_audit_recorder() -> AuditRecorder:
    global _AUDITOR
    if _AUDITOR is None:
        _AUDITOR = AuditRecorder()
    return _AUDITOR


def reset_audit_recorder() -> AuditRecorder:
    global _AUDITOR
    _AUDITOR = AuditRecorder()
    return _AUDITOR
