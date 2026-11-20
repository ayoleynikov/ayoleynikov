"""Secrets must never appear in structured logs."""

from __future__ import annotations

import logging

from pulse.logging import SecretRedactingFilter, redact_secrets


def test_redact_secrets_dict() -> None:
    payload = {
        "user": "alice",
        "password": "super-secret",
        "nested": {"api_key": "k-123", "ok": True},
        "authorization": "Bearer abc",
        "safe": "visible",
    }
    redacted = redact_secrets(payload)
    assert redacted["password"] == "***REDACTED***"
    assert redacted["nested"]["api_key"] == "***REDACTED***"
    assert redacted["authorization"] == "***REDACTED***"
    assert redacted["safe"] == "visible"
    assert redacted["user"] == "alice"


def test_redact_assignment_string() -> None:
    text = "connecting with password=hunter2 and token=abc"
    assert "hunter2" not in redact_secrets(text)
    assert "***REDACTED***" in redact_secrets(text)


def test_filter_on_log_record_extra() -> None:
    record = logging.LogRecord(
        name="pulse.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="login attempt",
        args=(),
        exc_info=None,
    )
    record.jwt_secret = "should-not-leak"  # type: ignore[attr-defined]
    record.postgres_password = "db-pass"  # type: ignore[attr-defined]
    record.tenant = "acme"  # type: ignore[attr-defined]

    assert SecretRedactingFilter().filter(record) is True
    assert record.jwt_secret == "***REDACTED***"  # type: ignore[attr-defined]
    assert record.postgres_password == "***REDACTED***"  # type: ignore[attr-defined]
    assert record.tenant == "acme"  # type: ignore[attr-defined]
