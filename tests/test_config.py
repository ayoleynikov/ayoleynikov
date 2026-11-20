"""Settings and model import smoke tests."""

from __future__ import annotations

from pulse.config import Settings
from pulse.db.base import Base
from pulse.models import (
    ConnectorCheckpoint,
    FeedSource,
    Mention,
    Organization,
    OrganizationMember,
    Project,
    User,
)


def test_settings_database_url() -> None:
    settings = Settings(
        postgres_host="db.example",
        postgres_port=5433,
        postgres_user="u",
        postgres_password="p",
        postgres_db="pulse",
    )
    assert settings.database_url.startswith("postgresql+asyncpg://u:p@db.example:5433/pulse")
    assert settings.database_url_sync.startswith("postgresql+psycopg://u:p@db.example:5433/pulse")


def test_core_models_registered() -> None:
    table_names = set(Base.metadata.tables.keys())
    assert table_names >= {
        "organizations",
        "users",
        "organization_members",
        "projects",
        "connector_checkpoints",
        "mentions",
        "feed_sources",
    }
    assert Organization.__tablename__ == "organizations"
    assert User.__tablename__ == "users"
    assert OrganizationMember.__tablename__ == "organization_members"
    assert Project.__tablename__ == "projects"


def test_app_factory_boots() -> None:
    from pulse.main import create_app

    app = create_app(Settings(env="test", jwt_secret="x" * 32))
    assert app.title == "Pulse Data Engine"
