"""Add brand matching + L4 cluster scaffold tables.

Revision ID: 20261120_0005
Revises: 20261120_0004
Create Date: 2026-11-20

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261120_0005"
down_revision: Union[str, None] = "20261120_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "slug", name="uq_brands_project_slug"),
    )
    op.create_index("ix_brands_project_id", "brands", ["project_id"])

    op.create_table(
        "brand_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("brand_id", "alias", name="uq_brand_aliases_brand_alias"),
    )
    op.create_index("ix_brand_aliases_brand_id", "brand_aliases", ["brand_id"])

    op.create_table(
        "competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competitor_brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competitor_brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id",
            "brand_id",
            "competitor_brand_id",
            name="uq_competitors_project_brand_competitor",
        ),
    )
    op.create_index("ix_competitors_project_id", "competitors", ["project_id"])
    op.create_index("ix_competitors_brand_id", "competitors", ["brand_id"])
    op.create_index("ix_competitors_competitor_brand_id", "competitors", ["competitor_brand_id"])

    op.create_table(
        "monitoring_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column(
            "ast_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_monitoring_queries_project_id", "monitoring_queries", ["project_id"])
    op.create_index("ix_monitoring_queries_brand_id", "monitoring_queries", ["brand_id"])

    op.create_table(
        "mention_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("mention_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("match_type", sa.String(length=64), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_id"], ["monitoring_queries.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("mention_id", "brand_id", name="uq_mention_matches_mention_brand"),
    )
    op.create_index("ix_mention_matches_mention_id", "mention_matches", ["mention_id"])
    op.create_index("ix_mention_matches_project_id", "mention_matches", ["project_id"])
    op.create_index("ix_mention_matches_brand_id", "mention_matches", ["brand_id"])
    op.create_index("ix_mention_matches_query_id", "mention_matches", ["query_id"])

    op.create_table(
        "event_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cluster_key", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="scaffold"),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("cluster_key"),
    )
    op.create_index("ix_event_clusters_project_id", "event_clusters", ["project_id"])
    op.create_index("ix_event_clusters_cluster_key", "event_clusters", ["cluster_key"], unique=True)

    op.create_table(
        "mention_cluster_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mention_id", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["cluster_id"], ["event_clusters.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("cluster_id", "mention_id", name="uq_cluster_member_cluster_mention"),
    )
    op.create_index("ix_mention_cluster_members_cluster_id", "mention_cluster_members", ["cluster_id"])
    op.create_index("ix_mention_cluster_members_mention_id", "mention_cluster_members", ["mention_id"])


def downgrade() -> None:
    op.drop_table("mention_cluster_members")
    op.drop_index("ix_event_clusters_cluster_key", table_name="event_clusters")
    op.drop_index("ix_event_clusters_project_id", table_name="event_clusters")
    op.drop_table("event_clusters")
    op.drop_index("ix_mention_matches_query_id", table_name="mention_matches")
    op.drop_index("ix_mention_matches_brand_id", table_name="mention_matches")
    op.drop_index("ix_mention_matches_project_id", table_name="mention_matches")
    op.drop_index("ix_mention_matches_mention_id", table_name="mention_matches")
    op.drop_table("mention_matches")
    op.drop_index("ix_monitoring_queries_brand_id", table_name="monitoring_queries")
    op.drop_index("ix_monitoring_queries_project_id", table_name="monitoring_queries")
    op.drop_table("monitoring_queries")
    op.drop_index("ix_competitors_competitor_brand_id", table_name="competitors")
    op.drop_index("ix_competitors_brand_id", table_name="competitors")
    op.drop_index("ix_competitors_project_id", table_name="competitors")
    op.drop_table("competitors")
    op.drop_index("ix_brand_aliases_brand_id", table_name="brand_aliases")
    op.drop_table("brand_aliases")
    op.drop_index("ix_brands_project_id", table_name="brands")
    op.drop_table("brands")
