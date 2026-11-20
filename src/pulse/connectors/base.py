"""BaseConnector abstract interface for all Pulse source connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel

from pulse.connectors.accounting import RequestCounter
from pulse.connectors.types import (
    CheckpointCursor,
    ConnectorCapabilities,
    FetchResult,
    HealthStatus,
    SearchQuery,
    SearchResult,
)


class BaseConnector(ABC):
    """Independent public-source connector with typed lifecycle methods.

    Implementations must honor ToS, rate limits, and never claim capabilities
    they do not provide. Failures must raise ``ConnectorError`` — never silent discard.
    """

    name: ClassVar[str]
    version: ClassVar[str]
    capabilities: ClassVar[ConnectorCapabilities]
    config_schema: ClassVar[type[BaseModel]]

    def __init__(self, config: BaseModel | dict[str, Any]) -> None:
        self.config = self.validate_config(config)
        self.accounting = RequestCounter()

    @classmethod
    def validate_config(cls, config: BaseModel | dict[str, Any]) -> BaseModel:
        """Validate and coerce connector configuration against ``config_schema``."""
        if isinstance(config, cls.config_schema):
            return config
        if isinstance(config, BaseModel):
            return cls.config_schema.model_validate(config.model_dump())
        return cls.config_schema.model_validate(config)

    @abstractmethod
    async def search(
        self,
        query: SearchQuery,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> SearchResult:
        """Search the source (may be unsupported — raise ConnectorError)."""

    @abstractmethod
    async def fetch_updates(
        self,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> FetchResult:
        """Fetch incremental updates using the checkpoint cursor."""

    @abstractmethod
    async def healthcheck(self) -> HealthStatus:
        """Probe connector readiness against the configured source."""

    @abstractmethod
    async def close(self) -> None:
        """Release HTTP clients and other resources."""

    def source_key(self) -> str:
        """Stable key used for checkpoint rows (override per connector)."""
        return self.name
