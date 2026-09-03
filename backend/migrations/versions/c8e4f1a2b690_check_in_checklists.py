"""add per-user mandatory check-in checklists

Revision ID: c8e4f1a2b690
Revises: a6d1e8f42c73
Create Date: 2026-08-29 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c8e4f1a2b690"
down_revision: Union[str, Sequence[str], None] = "a6d1e8f42c73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "check_in_checklist_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_check_in_checklist_created_by_users",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_check_in_checklist_user_users",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_check_in_checklist_user_active_order",
        "check_in_checklist_items",
        ["user_id", "is_active", "sort_order"],
        unique=False,
    )
    op.create_index(
        op.f("ix_check_in_checklist_items_created_at"),
        "check_in_checklist_items",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_check_in_checklist_items_is_active"),
        "check_in_checklist_items",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_check_in_checklist_items_user_id"),
        "check_in_checklist_items",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "attendance_checklist_completions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attendance_record_id", sa.Integer(), nullable=False),
        sa.Column("checklist_item_id", sa.Integer(), nullable=False),
        sa.Column("title_snapshot", sa.String(length=200), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attendance_record_id"],
            ["attendance_records.id"],
            name="fk_attendance_checklist_record_attendance",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["checklist_item_id"],
            ["check_in_checklist_items.id"],
            name="fk_attendance_checklist_item_checklist",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attendance_record_id",
            "checklist_item_id",
            name="uq_attendance_checklist_record_item",
        ),
    )
    op.create_index(
        op.f("ix_attendance_checklist_completions_attendance_record_id"),
        "attendance_checklist_completions",
        ["attendance_record_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attendance_checklist_completions_checklist_item_id"),
        "attendance_checklist_completions",
        ["checklist_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attendance_checklist_completions_completed_at"),
        "attendance_checklist_completions",
        ["completed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("attendance_checklist_completions")
    op.drop_table("check_in_checklist_items")
