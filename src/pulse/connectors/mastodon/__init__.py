"""Mastodon per-instance connector (public timelines / instance-local search)."""

from pulse.connectors.mastodon.config import MastodonConnectorConfig
from pulse.connectors.mastodon.connector import MastodonConnector

__all__ = ["MastodonConnector", "MastodonConnectorConfig"]
