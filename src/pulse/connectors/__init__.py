"""Connector SDK — public source connectors for Pulse Data Engine."""

from pulse.connectors.base import BaseConnector
from pulse.connectors.registry import ConnectorRegistry, get_registry
from pulse.connectors.types import (
    CheckpointCursor,
    ConnectorCapabilities,
    ConnectorError,
    ConnectorErrorKind,
    FetchResult,
    HealthStatus,
    NormalizedMention,
    RequestAccounting,
    SearchQuery,
    SearchResult,
)

__all__ = [
    "BaseConnector",
    "CheckpointCursor",
    "ConnectorCapabilities",
    "ConnectorError",
    "ConnectorErrorKind",
    "ConnectorRegistry",
    "FetchResult",
    "HealthStatus",
    "NormalizedMention",
    "RequestAccounting",
    "SearchQuery",
    "SearchResult",
    "get_registry",
]
