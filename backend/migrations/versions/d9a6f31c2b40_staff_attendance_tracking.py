"""staff attendance check-in and check-out tracking

Revision ID: d9a6f31c2b40
Revises: c4e9f7281a6d
Create Date: 2026-08-27 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d9a6f31c2b40"
down_revision: Union[str, Sequence[str], None] = "c4e9f7281a6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("staff_member_id", sa.Integer(), nullable=False),
        sa.Column("checked_in_by_id", sa.Integer(), nullable=False),
        sa.Column("checked_out_by_id", sa.Integer(), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(), nullable=False),
        sa.Column("checked_out_at", sa.DateTime(), nullable=True),
        sa.Column("check_in_ip", sa.String(length=64), nullable=True),
        sa.Column("check_out_ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["checked_in_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["checked_out_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["staff_member_id"], ["staff_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attendance_open_shift",
        "attendance_records",
        ["staff_member_id", "checked_out_at"],
        unique=False,
    )
    op.create_index(
        "ix_attendance_staff_check_in",
        "attendance_records",
        ["staff_member_id", "checked_in_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attendance_records_checked_in_at"),
        "attendance_records",
        ["checked_in_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attendance_records_checked_out_at"),
        "attendance_records",
        ["checked_out_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attendance_records_created_at"),
        "attendance_records",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attendance_records_staff_member_id"),
        "attendance_records",
        ["staff_member_id"],
        unique=False,
    )


def downgrade() -> None:
    # MySQL may use one of the composite indexes above to enforce the
    # staff_member_id foreign key. Dropping indexes individually can therefore
    # fail with error 1553. Dropping the table removes its indexes and foreign
    # keys together on every supported database.
    op.drop_table("attendance_records")
