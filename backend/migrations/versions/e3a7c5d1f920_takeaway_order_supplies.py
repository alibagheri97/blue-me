"""add takeaway order mode and packaging supplies

Revision ID: e3a7c5d1f920
Revises: c8e4f1a2b690
Create Date: 2026-09-03 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e3a7c5d1f920"
down_revision: Union[str, Sequence[str], None] = "c8e4f1a2b690"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "order_type",
            sa.Enum(
                "DINE_IN", "TAKEAWAY", name="ordertype", native_enum=False
            ),
            server_default="DINE_IN",
            nullable=False,
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "takeaway_package_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "takeaway_cost",
            sa.Numeric(precision=16, scale=2),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_orders_order_type"), "orders", ["order_type"], unique=False
    )

    op.create_table(
        "takeaway_supplies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), nullable=False),
        sa.Column(
            "quantity_per_package",
            sa.Numeric(precision=14, scale=3),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_takeaway_supply_created_by_users",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"],
            ["inventory_items.id"],
            name="fk_takeaway_supply_inventory_item",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "inventory_item_id", name="uq_takeaway_supply_inventory_item"
        ),
    )
    op.create_index(
        op.f("ix_takeaway_supplies_created_at"),
        "takeaway_supplies",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("takeaway_supplies")
    op.drop_index(op.f("ix_orders_order_type"), table_name="orders")
    op.drop_column("orders", "takeaway_cost")
    op.drop_column("orders", "takeaway_package_count")
    op.drop_column("orders", "order_type")
