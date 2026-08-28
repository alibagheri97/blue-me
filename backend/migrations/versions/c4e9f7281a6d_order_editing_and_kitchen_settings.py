"""order editing and persistent kitchen workflow settings

Revision ID: c4e9f7281a6d
Revises: b8d7e4a10f23
Create Date: 2026-08-27 00:00:00
"""

from typing import Sequence, Union
from datetime import datetime, UTC

import sqlalchemy as sa
from alembic import op


revision: str = "c4e9f7281a6d"
down_revision: Union[str, Sequence[str], None] = "b8d7e4a10f23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "kitchen_workflow_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_system_settings_created_at"),
        "system_settings",
        ["created_at"],
        unique=False,
    )
    settings = sa.table(
        "system_settings",
        sa.column("id", sa.Integer()),
        sa.column("kitchen_workflow_enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    op.bulk_insert(
        settings,
        [
            {
                "id": 1,
                "kitchen_workflow_enabled": True,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_system_settings_created_at"), table_name="system_settings")
    op.drop_table("system_settings")
