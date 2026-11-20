"""ClickHouse HTTP client adapter (clickhouse-connect)."""

from __future__ import annotations

from typing import Any, Sequence

from pulse.clickhouse.schema import DDL_STATEMENTS, ensure_database_sql
from pulse.config import Settings, get_settings
from pulse.logging import get_logger

logger = get_logger(__name__)

_CLIENT: ClickHouseClient | None = None


class ClickHouseClient:
    """Thin wrapper around clickhouse-connect for Pulse analytics tables."""

    def __init__(self, settings: Settings | None = None, *, client: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    def connect(self) -> Any:
        if self._client is not None:
            return self._client
        import clickhouse_connect

        self._client = clickhouse_connect.get_client(
            host=self.settings.clickhouse_host,
            port=self.settings.clickhouse_port,
            username=self.settings.clickhouse_user,
            password=self.settings.clickhouse_password.get_secret_value(),
            database=self.settings.clickhouse_db,
        )
        return self._client

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            self._client.close()
            self._client = None

    def ping(self) -> bool:
        client = self.connect()
        result = client.query("SELECT 1")
        return bool(result.result_rows)

    def ensure_schema(self) -> None:
        """Create database + analytics tables (idempotent)."""
        client = self.connect()
        # Create DB using a client without database binding when needed.
        import clickhouse_connect

        admin = clickhouse_connect.get_client(
            host=self.settings.clickhouse_host,
            port=self.settings.clickhouse_port,
            username=self.settings.clickhouse_user,
            password=self.settings.clickhouse_password.get_secret_value(),
        )
        try:
            admin.command(ensure_database_sql(self.settings.clickhouse_db))
        finally:
            admin.close()
        for ddl in DDL_STATEMENTS:
            client.command(ddl)
        logger.info("clickhouse_schema_ready", extra={"database": self.settings.clickhouse_db})

    def insert(self, table: str, rows: Sequence[dict[str, Any]], column_names: list[str]) -> int:
        if not rows:
            return 0
        client = self.connect()
        data = [[row.get(col) for col in column_names] for row in rows]
        client.insert(table, data, column_names=column_names)
        return len(rows)

    def query(self, sql: str, parameters: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
        client = self.connect()
        result = client.query(sql, parameters=parameters or {})
        return list(result.result_rows)


class InMemoryClickHouseClient(ClickHouseClient):
    """Test double — stores rows in memory; no network."""

    def __init__(self) -> None:
        super().__init__(client=object())
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self._owns_client = False

    def connect(self) -> Any:
        return self._client

    def close(self) -> None:
        return None

    def ping(self) -> bool:
        return True

    def ensure_schema(self) -> None:
        for name in (
            "mention_catalog",
            "project_mentions",
            "mention_matches",
            "mention_analytics",
            "event_clusters",
            "hourly_metrics",
        ):
            self.tables.setdefault(name, [])

    def insert(self, table: str, rows: Sequence[dict[str, Any]], column_names: list[str]) -> int:
        self.tables.setdefault(table, [])
        for row in rows:
            self.tables[table].append({col: row.get(col) for col in column_names})
        return len(rows)

    def query(self, sql: str, parameters: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
        return []


def get_clickhouse_client(settings: Settings | None = None) -> ClickHouseClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = ClickHouseClient(settings)
    return _CLIENT


def reset_clickhouse_client() -> None:
    global _CLIENT
    if _CLIENT is not None:
        _CLIENT.close()
    _CLIENT = None
