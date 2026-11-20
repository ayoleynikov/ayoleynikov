"""Add usage_records and source_costs tables.

Revision ID: 20261120_0006
Revises: 20261120_0005
Create Date: 2026-11-20

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261120_0006"
down_revision: Union[str, None] = "20261120_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("http_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_downloaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_uploaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("items_collected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_duplicates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_time_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("network_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("ai_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("pricing_label", sa.String(length=128), nullable=True),
        sa.Column(
            "extras",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_usage_records_organization_id", "usage_records", ["organization_id"])
    op.create_index("ix_usage_records_project_id", "usage_records", ["project_id"])
    op.create_index("ix_usage_records_source", "usage_records", ["source"])
    op.create_index("ix_usage_records_operation", "usage_records", ["operation"])
    op.create_index("ix_usage_records_recorded_at", "usage_records", ["recorded_at"])

    op.create_table(
        "source_costs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("cost_component", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False, server_default="per_1"),
        sa.Column("unit_price_usd", sa.Numeric(18, 10), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("pricing_label", sa.String(length=128), nullable=False, server_default="operator"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "source",
            "cost_component",
            "pricing_label",
            name="uq_source_costs_source_component_label",
        ),
    )
    op.create_index("ix_source_costs_source", "source_costs", ["source"])
    op.create_index("ix_source_costs_cost_component", "source_costs", ["cost_component"])


def downgrade() -> None:
    op.drop_index("ix_source_costs_cost_component", table_name="source_costs")
    op.drop_index("ix_source_costs_source", table_name="source_costs")
    op.drop_table("source_costs")
    op.drop_index("ix_usage_records_recorded_at", table_name="usage_records")
    op.drop_index("ix_usage_records_operation", table_name="usage_records")
    op.drop_index("ix_usage_records_source", table_name="usage_records")
    op.drop_index("ix_usage_records_project_id", table_name="usage_records")
    op.drop_index("ix_usage_records_organization_id", table_name="usage_records")
    op.drop_table("usage_records")
