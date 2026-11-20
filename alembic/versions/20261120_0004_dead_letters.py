"""Add dead_letters table for exhausted Celery task failures.

Revision ID: 20261120_0004
Revises: 20261120_0003
Create Date: 2026-11-20

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261120_0004"
down_revision: Union[str, None] = "20261120_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dead_letters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("task_name", sa.String(length=255), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        sa.Column("queue", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column(
            "args_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "kwargs_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("exception_type", sa.String(length=255), nullable=False),
        sa.Column("exception_message", sa.Text(), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
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
    )
    op.create_index("ix_dead_letters_task_name", "dead_letters", ["task_name"])
    op.create_index("ix_dead_letters_task_id", "dead_letters", ["task_id"])
    op.create_index("ix_dead_letters_queue", "dead_letters", ["queue"])
    op.create_index("ix_dead_letters_idempotency_key", "dead_letters", ["idempotency_key"])
    op.create_index("ix_dead_letters_status", "dead_letters", ["status"])


def downgrade() -> None:
    op.drop_index("ix_dead_letters_status", table_name="dead_letters")
    op.drop_index("ix_dead_letters_idempotency_key", table_name="dead_letters")
    op.drop_index("ix_dead_letters_queue", table_name="dead_letters")
    op.drop_index("ix_dead_letters_task_id", table_name="dead_letters")
    op.drop_index("ix_dead_letters_task_name", table_name="dead_letters")
    op.drop_table("dead_letters")
