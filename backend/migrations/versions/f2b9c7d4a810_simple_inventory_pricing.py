"""store simple purchase and sale package pricing

Revision ID: f2b9c7d4a810
Revises: d9a6f31c2b40
Create Date: 2026-08-27 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f2b9c7d4a810"
down_revision: Union[str, Sequence[str], None] = "d9a6f31c2b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inventory_items",
        sa.Column(
            "purchase_quantity",
            sa.Numeric(precision=14, scale=3),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "inventory_items",
        sa.Column(
            "purchase_unit",
            sa.String(length=32),
            nullable=False,
            server_default="عدد",
        ),
    )
    op.add_column(
        "inventory_items",
        sa.Column(
            "purchase_total_price",
            sa.Numeric(precision=16, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "inventory_items",
        sa.Column(
            "selling_quantity",
            sa.Numeric(precision=14, scale=3),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "inventory_items",
        sa.Column(
            "selling_unit",
            sa.String(length=32),
            nullable=False,
            server_default="عدد",
        ),
    )
    op.add_column(
        "inventory_items",
        sa.Column(
            "selling_total_price",
            sa.Numeric(precision=16, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE inventory_items
            SET purchase_quantity = 1,
                purchase_unit = unit,
                purchase_total_price = last_purchase_price,
                selling_quantity = 1,
                selling_unit = unit,
                selling_total_price = selling_price
            """
        )
    )

    op.add_column(
        "price_change_requests",
        sa.Column("package_quantity", sa.Numeric(precision=14, scale=3), nullable=True),
    )
    op.add_column(
        "price_change_requests",
        sa.Column("package_unit", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "price_change_requests",
        sa.Column("package_total_price", sa.Numeric(precision=16, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("price_change_requests", "package_total_price")
    op.drop_column("price_change_requests", "package_unit")
    op.drop_column("price_change_requests", "package_quantity")
    op.drop_column("inventory_items", "selling_total_price")
    op.drop_column("inventory_items", "selling_unit")
    op.drop_column("inventory_items", "selling_quantity")
    op.drop_column("inventory_items", "purchase_total_price")
    op.drop_column("inventory_items", "purchase_unit")
    op.drop_column("inventory_items", "purchase_quantity")
