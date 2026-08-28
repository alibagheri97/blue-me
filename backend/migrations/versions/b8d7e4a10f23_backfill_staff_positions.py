"""backfill staff positions from linked user roles

Revision ID: b8d7e4a10f23
Revises: e7c4d10ab832
Create Date: 2026-08-28 01:35:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b8d7e4a10f23"
down_revision: Union[str, Sequence[str], None] = "e7c4d10ab832"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("role", sa.String()),
    )
    staff_members = sa.table(
        "staff_members",
        sa.column("user_id", sa.Integer()),
        sa.column("position", sa.String()),
    )
    role_positions = {
        "root": "مدیر کل",
        "storage_manager": "مدیر انبار",
        "accounting_manager": "مدیر حسابداری",
        "sales_manager": "مدیر فروش",
        "kitchen_manager": "مدیر آشپزخانه",
    }
    for role, position in role_positions.items():
        linked_user_ids = sa.select(users.c.id).where(users.c.role == role)
        connection.execute(
            staff_members.update()
            .where(
                staff_members.c.position.is_(None),
                staff_members.c.user_id.in_(linked_user_ids),
            )
            .values(position=position)
        )


def downgrade() -> None:
    # This migration only fills previously empty labels. A downgrade deliberately
    # preserves those harmless labels instead of erasing possible later edits.
    pass
