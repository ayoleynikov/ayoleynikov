"""Encrypt connector credentials at rest (Fernet). Secrets never logged."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from pulse.config import Settings
from pulse.logging import get_logger

logger = get_logger(__name__)


class CredentialCryptoError(Exception):
    """Encryption/decryption failure."""


def _fernet_from_settings(settings: Settings) -> Fernet:
    """Build a Fernet key from ``credentials_encryption_key`` or derive from jwt_secret.

    Derived keys are for local/dev only — production must set an explicit Fernet key.
    """
    configured = settings.credentials_encryption_key
    if configured is not None and configured.get_secret_value().strip():
        key = configured.get_secret_value().strip().encode("utf-8")
        try:
            return Fernet(key)
        except (ValueError, TypeError) as exc:
            raise CredentialCryptoError("invalid PULSE_CREDENTIALS_ENCRYPTION_KEY") from exc

    # Deterministic Fernet-compatible key derived from jwt_secret (dev fallback).
    digest = hashlib.sha256(settings.jwt_secret.get_secret_value().encode("utf-8")).digest()
    derived = base64.urlsafe_b64encode(digest)
    logger.warning(
        "credentials_encryption_using_derived_key",
        extra={"note": "Set PULSE_CREDENTIALS_ENCRYPTION_KEY in production"},
    )
    return Fernet(derived)


def encrypt_secret(plaintext: str | SecretStr, *, settings: Settings) -> str:
    value = plaintext.get_secret_value() if isinstance(plaintext, SecretStr) else plaintext
    if not value:
        raise CredentialCryptoError("cannot encrypt empty secret")
    token = _fernet_from_settings(settings).encrypt(value.encode("utf-8"))
    return token.decode("ascii")


def decrypt_secret(token: str, *, settings: Settings) -> str:
    try:
        return _fernet_from_settings(settings).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise CredentialCryptoError("failed to decrypt credential") from exc


def seal_credential_payload(payload: dict[str, Any], *, settings: Settings) -> str:
    """Encrypt a JSON-serializable credential map (api keys, tokens)."""
    import orjson

    # Never include keys that look like they already hold ciphertext markers.
    raw = orjson.dumps(payload)
    return encrypt_secret(raw.decode("utf-8"), settings=settings)


def open_credential_payload(token: str, *, settings: Settings) -> dict[str, Any]:
    import orjson

    raw = decrypt_secret(token, settings=settings)
    data = orjson.loads(raw)
    if not isinstance(data, dict):
        raise CredentialCryptoError("credential payload must be an object")
    return data
