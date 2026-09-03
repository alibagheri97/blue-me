"""add recoverable order deletion

Revision ID: a6d1e8f42c73
Revises: f2b9c7d4a810
Create Date: 2026-08-29 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a6d1e8f42c73"
down_revision: Union[str, Sequence[str], None] = "f2b9c7d4a810"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column("orders", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("orders", sa.Column("deleted_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_orders_deleted_by_id_users",
        "orders",
        "users",
        ["deleted_by_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_orders_is_deleted"), "orders", ["is_deleted"], unique=False
    )
    op.create_index(
        op.f("ix_orders_deleted_by_id"), "orders", ["deleted_by_id"], unique=False
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_orders_deleted_by_id_users", "orders", type_="foreignkey"
    )
    op.drop_index(op.f("ix_orders_deleted_by_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_is_deleted"), table_name="orders")
    op.drop_column("orders", "deleted_by_id")
    op.drop_column("orders", "deleted_at")
    op.drop_column("orders", "is_deleted")
