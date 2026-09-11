"""Record system waste and temporary attendance separately.

Revision ID: b7f2e9d4c601
Revises: a6d1c4e8f209
"""

import sqlalchemy as sa
from alembic import op

revision = "b7f2e9d4c601"
down_revision = "a6d1c4e8f209"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("is_system_waste", sa.Boolean(), nullable=False, server_default="0"))
    op.create_index("ix_orders_is_system_waste", "orders", ["is_system_waste"])
    op.add_column("attendance_records", sa.Column("is_temporary", sa.Boolean(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("attendance_records", "is_temporary")
    op.drop_index("ix_orders_is_system_waste", table_name="orders")
    op.drop_column("orders", "is_system_waste")
