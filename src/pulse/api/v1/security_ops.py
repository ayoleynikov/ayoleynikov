"""Security operations API: tenant check, audit, deletion, credentials seal."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr

from pulse.config import Settings
from pulse.models.membership import OrganizationRole
from pulse.security.audit import AuditEvent, get_audit_recorder
from pulse.security.credentials import encrypt_secret, seal_credential_payload
from pulse.security.deletion import DeletionRequestView, DeletionStatus, get_deletion_service
from pulse.security.deps import CurrentPrincipal, get_current_principal, require_org_role
from pulse.security.rbac import ForbiddenError
from pulse.security.tenant import get_tenant_context

router = APIRouter(tags=["security"])


class TenantCheckRequest(BaseModel):
    organization_id: UUID
    project_id: UUID | None = None
    project_organization_id: UUID | None = None
    minimum_role: OrganizationRole = OrganizationRole.VIEWER


class TenantCheckResponse(BaseModel):
    allowed: bool
    role: str | None = None
    detail: str | None = None


class DeletionCreateRequest(BaseModel):
    organization_id: UUID
    resource_type: str
    resource_id: str | None = None
    project_id: UUID | None = None
    reason: str | None = None
    grace_days: int = Field(default=7, ge=0, le=365)


class SealCredentialRequest(BaseModel):
    organization_id: UUID
    connector: str
    secret: SecretStr | None = None
    payload: dict[str, Any] | None = None
    label: str = "default"


class SealCredentialResponse(BaseModel):
    organization_id: UUID
    connector: str
    label: str
    ciphertext: str
    note: str = "Store ciphertext in connector_credentials; plaintext is never returned again."


@router.post("/tenant/check", response_model=TenantCheckResponse)
async def tenant_check(
    body: TenantCheckRequest,
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
) -> TenantCheckResponse:
    """Verify the caller may access an org/project — cross-org denied."""
    ctx = get_tenant_context()
    try:
        if body.project_id is not None:
            membership = ctx.assert_project_access(
                user_id=principal.user_id,
                organization_id=body.organization_id,
                project_id=body.project_id,
                minimum_role=body.minimum_role,
                is_superuser=principal.is_superuser,
                project_org_id=body.project_organization_id,
            )
        else:
            membership = ctx.assert_org_access(
                user_id=principal.user_id,
                organization_id=body.organization_id,
                minimum_role=body.minimum_role,
                is_superuser=principal.is_superuser,
            )
        return TenantCheckResponse(allowed=True, role=membership.role.value)
    except ForbiddenError as exc:
        get_audit_recorder().record(
            "tenant.access_denied",
            actor_user_id=principal.user_id,
            organization_id=body.organization_id,
            project_id=body.project_id,
            details={"reason": str(exc)},
        )
        return TenantCheckResponse(allowed=False, detail=str(exc))


@router.get("/audit", response_model=list[AuditEvent])
async def list_audit(
    principal: Annotated[
        CurrentPrincipal, Depends(require_org_role(OrganizationRole.ADMIN))
    ],
    organization_id: UUID | None = None,
) -> list[AuditEvent]:
    org = organization_id or principal.org_id
    return get_audit_recorder().list_events(organization_id=org)


@router.post("/deletion-requests", response_model=DeletionRequestView)
async def create_deletion_request(
    body: DeletionCreateRequest,
    principal: Annotated[
        CurrentPrincipal, Depends(require_org_role(OrganizationRole.ADMIN))
    ],
) -> DeletionRequestView:
    if principal.org_id and body.organization_id != principal.org_id and not principal.is_superuser:
        raise HTTPException(status_code=403, detail="cross-org deletion denied")
    return get_deletion_service().request_deletion(
        organization_id=body.organization_id,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        project_id=body.project_id,
        reason=body.reason,
        requested_by=principal.user_id,
        grace_days=body.grace_days,
    )


@router.get("/deletion-requests", response_model=list[DeletionRequestView])
async def list_deletion_requests(
    principal: Annotated[
        CurrentPrincipal, Depends(require_org_role(OrganizationRole.ADMIN))
    ],
    status: DeletionStatus | None = None,
) -> list[DeletionRequestView]:
    return get_deletion_service().list_requests(
        organization_id=principal.org_id,
        status=status,
    )


@router.post("/credentials/seal", response_model=SealCredentialResponse)
async def seal_credential(
    body: SealCredentialRequest,
    request: Request,
    principal: Annotated[
        CurrentPrincipal, Depends(require_org_role(OrganizationRole.ADMIN))
    ],
) -> SealCredentialResponse:
    settings: Settings = request.app.state.settings
    if principal.org_id and body.organization_id != principal.org_id and not principal.is_superuser:
        raise HTTPException(status_code=403, detail="cross-org credential seal denied")
    if body.payload is not None:
        ciphertext = seal_credential_payload(body.payload, settings=settings)
    elif body.secret is not None:
        ciphertext = encrypt_secret(body.secret, settings=settings)
    else:
        raise HTTPException(status_code=400, detail="secret or payload required")
    get_audit_recorder().record(
        "credentials.sealed",
        actor_user_id=principal.user_id,
        organization_id=body.organization_id,
        resource_type="connector_credential",
        resource_id=body.connector,
        details={"label": body.label},
    )
    return SealCredentialResponse(
        organization_id=body.organization_id,
        connector=body.connector,
        label=body.label,
        ciphertext=ciphertext,
    )
