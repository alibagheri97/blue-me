"""staff accounts and non-revenue staff meals

Revision ID: e7c4d10ab832
Revises: a61f8b2c9d44
Create Date: 2026-08-28 01:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e7c4d10ab832"
down_revision: Union[str, Sequence[str], None] = "a61f8b2c9d44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staff_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("position", sa.String(length=120), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_staff_members_created_at"),
        "staff_members",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_members_is_active"),
        "staff_members",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_members_name"), "staff_members", ["name"], unique=False
    )
    op.create_index(
        op.f("ix_staff_members_phone"), "staff_members", ["phone"], unique=True
    )
    op.create_index(
        op.f("ix_staff_members_user_id"),
        "staff_members",
        ["user_id"],
        unique=True,
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO staff_members
                (name, phone, position, user_id, notes, is_active, created_at, updated_at)
            SELECT
                full_name, NULL, NULL, id, 'ایجاد خودکار از حساب کاربری سامانه',
                is_active, created_at, updated_at
            FROM users
            """
        )
    )

    op.add_column("orders", sa.Column("staff_member_id", sa.Integer(), nullable=True))
    op.add_column(
        "orders", sa.Column("staff_name", sa.String(length=160), nullable=True)
    )
    op.add_column(
        "orders",
        sa.Column(
            "is_staff_meal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_foreign_key(
        "fk_orders_staff_member_id",
        "orders",
        "staff_members",
        ["staff_member_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_orders_staff_member_id"),
        "orders",
        ["staff_member_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_orders_is_staff_meal"),
        "orders",
        ["is_staff_meal"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_is_staff_meal"), table_name="orders")
    op.drop_index(op.f("ix_orders_staff_member_id"), table_name="orders")
    op.drop_constraint("fk_orders_staff_member_id", "orders", type_="foreignkey")
    op.drop_column("orders", "is_staff_meal")
    op.drop_column("orders", "staff_name")
    op.drop_column("orders", "staff_member_id")
    op.drop_index(op.f("ix_staff_members_user_id"), table_name="staff_members")
    op.drop_index(op.f("ix_staff_members_phone"), table_name="staff_members")
    op.drop_index(op.f("ix_staff_members_name"), table_name="staff_members")
    op.drop_index(op.f("ix_staff_members_is_active"), table_name="staff_members")
    op.drop_index(op.f("ix_staff_members_created_at"), table_name="staff_members")
    op.drop_table("staff_members")
