"""Deletion request + retention policy scaffolding."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from pulse.security.audit import get_audit_recorder


class DeletionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeletionRequestView(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    project_id: UUID | None = None
    resource_type: str
    resource_id: str | None = None
    reason: str | None = None
    status: DeletionStatus = DeletionStatus.PENDING
    requested_by: UUID | None = None
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    due_at: datetime | None = None
    completed_at: datetime | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class RetentionPolicy(BaseModel):
    """Default retention windows — operators override per tenant later."""

    mentions_days: int = 365
    raw_payload_days: int = 90
    audit_logs_days: int = 730
    usage_records_days: int = 730
    dead_letters_days: int = 180


class DeletionService:
    def __init__(self, retention: RetentionPolicy | None = None) -> None:
        self.retention = retention or RetentionPolicy()
        self._requests: list[DeletionRequestView] = []

    def request_deletion(
        self,
        *,
        organization_id: UUID,
        resource_type: str,
        resource_id: str | None = None,
        project_id: UUID | None = None,
        reason: str | None = None,
        requested_by: UUID | None = None,
        grace_days: int = 7,
    ) -> DeletionRequestView:
        req = DeletionRequestView(
            organization_id=organization_id,
            project_id=project_id,
            resource_type=resource_type,
            resource_id=resource_id,
            reason=reason,
            requested_by=requested_by,
            due_at=datetime.now(UTC) + timedelta(days=grace_days),
        )
        self._requests.append(req)
        get_audit_recorder().record(
            "deletion.requested",
            actor_user_id=requested_by,
            organization_id=organization_id,
            project_id=project_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details={"reason": reason, "due_at": req.due_at.isoformat() if req.due_at else None},
        )
        return req

    def list_requests(
        self,
        *,
        organization_id: UUID | None = None,
        status: DeletionStatus | None = None,
    ) -> list[DeletionRequestView]:
        rows = self._requests
        if organization_id is not None:
            rows = [r for r in rows if r.organization_id == organization_id]
        if status is not None:
            rows = [r for r in rows if r.status == status]
        return list(rows)

    def mark_completed(self, request_id: UUID) -> DeletionRequestView:
        for req in self._requests:
            if req.id == request_id:
                req.status = DeletionStatus.COMPLETED
                req.completed_at = datetime.now(UTC)
                get_audit_recorder().record(
                    "deletion.completed",
                    organization_id=req.organization_id,
                    project_id=req.project_id,
                    resource_type=req.resource_type,
                    resource_id=req.resource_id or str(req.id),
                )
                return req
        msg = f"deletion request not found: {request_id}"
        raise KeyError(msg)

    def retention_cutoff(self, kind: str) -> datetime:
        days = {
            "mentions": self.retention.mentions_days,
            "raw_payload": self.retention.raw_payload_days,
            "audit_logs": self.retention.audit_logs_days,
            "usage_records": self.retention.usage_records_days,
            "dead_letters": self.retention.dead_letters_days,
        }.get(kind)
        if days is None:
            msg = f"unknown retention kind: {kind}"
            raise ValueError(msg)
        return datetime.now(UTC) - timedelta(days=days)


_DELETION: DeletionService | None = None


def get_deletion_service() -> DeletionService:
    global _DELETION
    if _DELETION is None:
        _DELETION = DeletionService()
    return _DELETION


def reset_deletion_service(retention: RetentionPolicy | None = None) -> DeletionService:
    global _DELETION
    _DELETION = DeletionService(retention)
    return _DELETION
