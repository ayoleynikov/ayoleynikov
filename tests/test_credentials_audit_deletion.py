"""Credential encryption, audit logs, deletion/retention scaffolding."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from pulse.config import Settings
from pulse.main import create_app
from pulse.models.membership import OrganizationRole
from pulse.security.audit import reset_audit_recorder
from pulse.security.credentials import decrypt_secret, encrypt_secret, seal_credential_payload
from pulse.security.deletion import reset_deletion_service
from pulse.security.jwt_tokens import create_access_token


def test_encrypt_decrypt_roundtrip() -> None:
    settings = Settings(env="test", jwt_secret="unit-test-secret-key-32chars!!")
    token = encrypt_secret("super-secret-api-key", settings=settings)
    assert "super-secret" not in token
    assert decrypt_secret(token, settings=settings) == "super-secret-api-key"
    sealed = seal_credential_payload({"api_key": "k", "token": "t"}, settings=settings)
    # ciphertext only
    assert "api_key" not in sealed or sealed.startswith("gAAAA")


def test_deletion_and_audit_api() -> None:
    reset_audit_recorder()
    reset_deletion_service()
    settings = Settings(env="test", jwt_secret="x" * 32, api_rate_limit_enabled=False)
    org = uuid4()
    user = uuid4()
    token = create_access_token(
        subject=user,
        settings=settings,
        org_id=org,
        role=OrganizationRole.ADMIN.value,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/api/v1/deletion-requests",
            headers=headers,
            json={
                "organization_id": str(org),
                "resource_type": "mention",
                "resource_id": "abc",
                "reason": "user request",
            },
        )
        assert created.status_code == 200
        assert created.json()["status"] == "pending"

        listed = client.get("/api/v1/deletion-requests", headers=headers)
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        sealed = client.post(
            "/api/v1/credentials/seal",
            headers=headers,
            json={
                "organization_id": str(org),
                "connector": "youtube",
                "secret": "yt-key-not-for-logs",
            },
        )
        assert sealed.status_code == 200
        assert "yt-key" not in sealed.json()["ciphertext"]

        audit = client.get("/api/v1/audit", headers=headers)
        assert audit.status_code == 200
        actions = {e["action"] for e in audit.json()}
        assert "deletion.requested" in actions
        assert "credentials.sealed" in actions
