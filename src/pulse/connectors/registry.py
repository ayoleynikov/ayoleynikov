"""ConnectorRegistry — discover and construct registered connectors."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from pulse.connectors.base import BaseConnector
from pulse.connectors.types import ConnectorCapabilities, ConnectorError, ConnectorErrorKind

# Explicitly disabled sources — not registered, never claimed as available.
DISABLED_CONNECTORS: dict[str, str] = {
    "reddit": "Disabled until commercial permission is obtained.",
}


class ConnectorRegistration(BaseModel):
    """Metadata published for each registered connector."""

    name: str
    version: str
    capabilities: ConnectorCapabilities
    config_schema_name: str
    policies: dict[str, Any] = {}


class ConnectorRegistry:
    """In-process registry of connector implementations."""

    def __init__(self) -> None:
        self._connectors: dict[str, type[BaseConnector]] = {}
        self._policies: dict[str, dict[str, Any]] = {}

    def register(
        self,
        connector_cls: type[BaseConnector],
        *,
        policies: dict[str, Any] | None = None,
    ) -> None:
        name = connector_cls.name
        if not name:
            msg = "connector class must define a non-empty name"
            raise ConnectorError(msg, kind=ConnectorErrorKind.CONFIG)
        if name in DISABLED_CONNECTORS:
            msg = f"connector disabled: {name} ({DISABLED_CONNECTORS[name]})"
            raise ConnectorError(msg, kind=ConnectorErrorKind.UNSUPPORTED)
        if name in self._connectors:
            msg = f"connector already registered: {name}"
            raise ConnectorError(msg, kind=ConnectorErrorKind.CONFIG)
        self._connectors[name] = connector_cls
        self._policies[name] = policies or {
            "public_sources_only": True,
            "respect_rate_limits": True,
            "no_auth_bypass": True,
        }

    def get(self, name: str) -> type[BaseConnector]:
        if name in DISABLED_CONNECTORS:
            msg = f"connector disabled: {name} ({DISABLED_CONNECTORS[name]})"
            raise ConnectorError(msg, kind=ConnectorErrorKind.UNSUPPORTED)
        try:
            return self._connectors[name]
        except KeyError as exc:
            msg = f"unknown connector: {name}"
            raise ConnectorError(msg, kind=ConnectorErrorKind.CONFIG) from exc

    def create(self, name: str, config: BaseModel | dict[str, Any]) -> BaseConnector:
        return self.get(name)(config)

    def list(self) -> list[ConnectorRegistration]:
        result: list[ConnectorRegistration] = []
        for name, cls in sorted(self._connectors.items()):
            result.append(
                ConnectorRegistration(
                    name=name,
                    version=cls.version,
                    capabilities=cls.capabilities,
                    config_schema_name=cls.config_schema.__name__,
                    policies=self._policies.get(name, {}),
                )
            )
        return result

    def health_manifest(self) -> list[dict[str, Any]]:
        """Static health/capability summary (no live probes)."""
        items = [
            {
                "name": reg.name,
                "version": reg.version,
                "capabilities": reg.capabilities.model_dump(),
                "policies": reg.policies,
                "enabled": True,
            }
            for reg in self.list()
        ]
        for name, reason in DISABLED_CONNECTORS.items():
            items.append(
                {
                    "name": name,
                    "version": None,
                    "capabilities": {},
                    "policies": {"disabled": True, "reason": reason},
                    "enabled": False,
                }
            )
        return items


_REGISTRY: ConnectorRegistry | None = None


def get_registry() -> ConnectorRegistry:
    """Return the process-wide registry, registering built-in connectors once."""
    global _REGISTRY
    if _REGISTRY is None:
        registry = ConnectorRegistry()
        # Import locally to avoid circular imports at module load.
        from pulse.connectors.bluesky.connector import BlueskyJetstreamConnector
        from pulse.connectors.gdelt.connector import GDELTConnector
        from pulse.connectors.mastodon.connector import MastodonConnector
        from pulse.connectors.rss.connector import RSSConnector
        from pulse.connectors.youtube.connector import YouTubeConnector

        registry.register(RSSConnector)
        registry.register(BlueskyJetstreamConnector)
        registry.register(GDELTConnector)
        registry.register(
            MastodonConnector,
            policies={
                "public_sources_only": True,
                "respect_rate_limits": True,
                "no_auth_bypass": True,
                "search_scope": "instance_local",
                "federation_wide_search": False,
                "per_instance_config": True,
            },
        )
        registry.register(
            YouTubeConnector,
            policies={
                "public_sources_only": True,
                "respect_rate_limits": True,
                "no_auth_bypass": True,
                "api": "youtube_data_v3",
                "unlimited_access": False,
                "quota_accounting": True,
            },
        )
        _REGISTRY = registry
    return _REGISTRY


def reset_registry() -> None:
    """Clear the singleton (tests only)."""
    global _REGISTRY
    _REGISTRY = None
