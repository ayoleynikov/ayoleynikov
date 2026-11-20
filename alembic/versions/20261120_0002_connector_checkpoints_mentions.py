"""Add connector_checkpoints, mentions, and feed_sources tables.

Revision ID: 20261120_0002
Revises: 20261120_0001
Create Date: 2026-11-20

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261120_0002"
down_revision: Union[str, None] = "20261120_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connector_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("connector", sa.String(length=64), nullable=False),
        sa.Column("source_key", sa.String(length=512), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("etag", sa.String(length=512), nullable=True),
        sa.Column("last_modified", sa.String(length=128), nullable=True),
        sa.Column("cursor_token", sa.Text(), nullable=True),
        sa.Column(
            "cursor_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("connector", "source_key", name="uq_checkpoint_connector_source"),
    )
    op.create_index("ix_connector_checkpoints_connector", "connector_checkpoints", ["connector"])
    op.create_index("ix_connector_checkpoints_project_id", "connector_checkpoints", ["project_id"])

    op.create_table(
        "mentions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("mention_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("author_id", sa.String(length=255), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "engagement",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("source_version", sa.String(length=32), nullable=False, server_default="1"),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("source", "external_id", name="uq_mentions_source_external_id"),
    )
    op.create_index("ix_mentions_mention_id", "mentions", ["mention_id"], unique=True)
    op.create_index("ix_mentions_source", "mentions", ["source"])
    op.create_index("ix_mentions_content_hash", "mentions", ["content_hash"])
    op.create_index("ix_mentions_canonical_url", "mentions", ["canonical_url"])
    op.create_index("ix_mentions_project_id", "mentions", ["project_id"])

    op.create_table(
        "feed_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("feed_url", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "poll_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "feed_url", name="uq_feed_sources_project_url"),
    )
    op.create_index("ix_feed_sources_project_id", "feed_sources", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_feed_sources_project_id", table_name="feed_sources")
    op.drop_table("feed_sources")
    op.drop_index("ix_mentions_project_id", table_name="mentions")
    op.drop_index("ix_mentions_canonical_url", table_name="mentions")
    op.drop_index("ix_mentions_content_hash", table_name="mentions")
    op.drop_index("ix_mentions_source", table_name="mentions")
    op.drop_index("ix_mentions_mention_id", table_name="mentions")
    op.drop_table("mentions")
    op.drop_index("ix_connector_checkpoints_project_id", table_name="connector_checkpoints")
    op.drop_index("ix_connector_checkpoints_connector", table_name="connector_checkpoints")
    op.drop_table("connector_checkpoints")
