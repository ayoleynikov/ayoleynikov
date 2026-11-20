"""ConnectorRegistry — discover and construct registered connectors."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from pulse.connectors.base import BaseConnector
from pulse.connectors.types import ConnectorCapabilities, ConnectorError, ConnectorErrorKind


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
        return [
            {
                "name": reg.name,
                "version": reg.version,
                "capabilities": reg.capabilities.model_dump(),
                "policies": reg.policies,
            }
            for reg in self.list()
        ]


_REGISTRY: ConnectorRegistry | None = None


def get_registry() -> ConnectorRegistry:
    """Return the process-wide registry, registering built-in connectors once."""
    global _REGISTRY
    if _REGISTRY is None:
        registry = ConnectorRegistry()
        # Import locally to avoid circular imports at module load.
        from pulse.connectors.rss.connector import RSSConnector

        registry.register(RSSConnector)
        _REGISTRY = registry
    return _REGISTRY


def reset_registry() -> None:
    """Clear the singleton (tests only)."""
    global _REGISTRY
    _REGISTRY = None
