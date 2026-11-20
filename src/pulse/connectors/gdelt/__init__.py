"""GDELT DOC 2.0 connector package."""

from pulse.connectors.gdelt.config import GDELTConnectorConfig
from pulse.connectors.gdelt.connector import GDELTConnector

__all__ = ["GDELTConnector", "GDELTConnectorConfig"]
