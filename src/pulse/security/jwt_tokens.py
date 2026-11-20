"""JWT create/verify helpers (HS256)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from pydantic import BaseModel, Field

from pulse.config import Settings


class TokenClaims(BaseModel):
    """Normalized claims carried in Pulse access tokens."""

    sub: str
    email: str | None = None
    org_id: str | None = None
    role: str | None = None
    is_superuser: bool = False
    scopes: list[str] = Field(default_factory=list)
    exp: datetime | None = None
    iat: datetime | None = None


class TokenError(Exception):
    """Invalid or expired token."""


def create_access_token(
    *,
    subject: str | UUID,
    settings: Settings,
    email: str | None = None,
    org_id: str | UUID | None = None,
    role: str | None = None,
    is_superuser: bool = False,
    scopes: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
        "iss": "pulse-data-engine",
        "is_superuser": is_superuser,
        "scopes": scopes or [],
    }
    if email:
        payload["email"] = email
    if org_id is not None:
        payload["org_id"] = str(org_id)
    if role:
        payload["role"] = role
    if extra:
        payload.update(extra)
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, *, settings: Settings) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    return TokenClaims.model_validate(payload)
