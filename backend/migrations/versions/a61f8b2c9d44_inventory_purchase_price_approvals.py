"""support independent purchase and selling price approvals

Revision ID: a61f8b2c9d44
Revises: d2c7a91f4e10
Create Date: 2026-08-26 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a61f8b2c9d44"
down_revision: Union[str, Sequence[str], None] = "d2c7a91f4e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "price_change_requests",
        sa.Column(
            "price_type",
            sa.Enum("PURCHASE", "SELLING", name="pricetype", native_enum=False, length=20),
            nullable=False,
            server_default="SELLING",
        ),
    )
    op.create_index(
        op.f("ix_price_change_requests_price_type"),
        "price_change_requests",
        ["price_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_price_change_requests_price_type"), table_name="price_change_requests")
    op.drop_column("price_change_requests", "price_type")
