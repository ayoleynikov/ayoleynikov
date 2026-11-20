"""ConnectorRegistry contract tests."""

from __future__ import annotations

import pytest

from pulse.connectors.registry import ConnectorRegistry, get_registry, reset_registry
from pulse.connectors.rss.connector import RSSConnector
from pulse.connectors.types import ConnectorError


def test_builtin_registry_includes_rss() -> None:
    reset_registry()
    registry = get_registry()
    names = {item.name for item in registry.list()}
    assert "rss" in names
    rss = next(item for item in registry.list() if item.name == "rss")
    assert rss.capabilities.supports_etag is True
    assert rss.capabilities.public_only is True
    assert rss.policies["no_auth_bypass"] is True


def test_registry_rejects_duplicate() -> None:
    registry = ConnectorRegistry()
    registry.register(RSSConnector)
    with pytest.raises(ConnectorError):
        registry.register(RSSConnector)


def test_registry_unknown_connector() -> None:
    registry = ConnectorRegistry()
    with pytest.raises(ConnectorError):
        registry.get("bluesky")
