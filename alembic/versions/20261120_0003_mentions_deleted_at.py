"""Add mentions.deleted_at for Bluesky delete events.

Revision ID: 20261120_0003
Revises: 20261120_0002
Create Date: 2026-11-20

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261120_0003"
down_revision: Union[str, None] = "20261120_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mentions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mentions_deleted_at", "mentions", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_mentions_deleted_at", table_name="mentions")
    op.drop_column("mentions", "deleted_at")
