"""add staff payroll, points, and two-phase attendance checklists

Revision ID: f4b8d6e2a731
Revises: e3a7c5d1f920
Create Date: 2026-09-03 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f4b8d6e2a731"
down_revision: Union[str, Sequence[str], None] = "e3a7c5d1f920"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "staff_members",
        sa.Column(
            "pay_type",
            sa.Enum(
                "SALARY",
                "PROFIT_SHARE",
                name="compensationtype",
                native_enum=False,
                length=24,
            ),
            server_default="SALARY",
            nullable=False,
        ),
    )
    op.add_column(
        "staff_members",
        sa.Column(
            "pay_rate",
            sa.Numeric(precision=16, scale=2),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "staff_members",
        sa.Column(
            "point_value",
            sa.Numeric(precision=14, scale=2),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_staff_members_pay_type"), "staff_members", ["pay_type"], unique=False
    )
    op.create_check_constraint(
        "ck_staff_pay_rate",
        "staff_members",
        "pay_rate >= 0 AND (pay_type <> 'PROFIT_SHARE' OR pay_rate <= 100)",
    )
    op.create_check_constraint(
        "ck_staff_point_value", "staff_members", "point_value >= 0"
    )

    op.add_column(
        "attendance_records",
        sa.Column("entry_checklist_completed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "attendance_records",
        sa.Column("exit_checklist_completed_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        "UPDATE attendance_records SET entry_checklist_completed_at = checked_in_at"
    )

    op.add_column(
        "check_in_checklist_items",
        sa.Column(
            "phase",
            sa.Enum(
                "ENTRY", "EXIT", name="checklistphase", native_enum=False, length=16
            ),
            server_default="ENTRY",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_check_in_checklist_items_phase"),
        "check_in_checklist_items",
        ["phase"],
        unique=False,
    )
    op.add_column(
        "attendance_checklist_completions",
        sa.Column(
            "phase",
            sa.Enum(
                "ENTRY", "EXIT", name="checklistphase", native_enum=False, length=16
            ),
            server_default="ENTRY",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_attendance_checklist_completions_phase"),
        "attendance_checklist_completions",
        ["phase"],
        unique=False,
    )

    op.create_table(
        "point_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("check_in_points", sa.Integer(), nullable=False),
        sa.Column("entry_checklist_points", sa.Integer(), nullable=False),
        sa.Column("check_out_points", sa.Integer(), nullable=False),
        sa.Column("exit_checklist_points", sa.Integer(), nullable=False),
        sa.Column("work_hour_points", sa.Integer(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("check_in_points >= 0", name="ck_point_policy_check_in"),
        sa.CheckConstraint(
            "entry_checklist_points >= 0", name="ck_point_policy_entry_checklist"
        ),
        sa.CheckConstraint("check_out_points >= 0", name="ck_point_policy_check_out"),
        sa.CheckConstraint(
            "exit_checklist_points >= 0", name="ck_point_policy_exit_checklist"
        ),
        sa.CheckConstraint("work_hour_points >= 0", name="ck_point_policy_work_hour"),
        sa.ForeignKeyConstraint(
            ["updated_by_id"], ["users.id"], name="fk_point_policy_updated_by"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_point_policies_created_at"),
        "point_policies",
        ["created_at"],
        unique=False,
    )
    op.execute(
        "INSERT INTO point_policies "
        "(id, check_in_points, entry_checklist_points, check_out_points, "
        "exit_checklist_points, work_hour_points, updated_by_id, created_at, updated_at) "
        "VALUES (1, 1, 2, 1, 2, 1, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )

    op.create_table(
        "staff_point_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("staff_member_id", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "MANUAL",
                "CHECK_IN",
                "ENTRY_CHECKLIST",
                "CHECK_OUT",
                "EXIT_CHECKLIST",
                "WORK_HOURS",
                name="pointsource",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("attendance_record_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("reference_key", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("points <> 0", name="ck_staff_point_nonzero"),
        sa.ForeignKeyConstraint(
            ["attendance_record_id"],
            ["attendance_records.id"],
            name="fk_staff_point_attendance",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_staff_point_created_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["staff_member_id"], ["staff_members.id"], name="fk_staff_point_staff"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_key", name="uq_staff_point_reference_key"),
    )
    op.create_index(
        op.f("ix_staff_point_entries_attendance_record_id"),
        "staff_point_entries",
        ["attendance_record_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_point_entries_created_at"),
        "staff_point_entries",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_point_entries_source"),
        "staff_point_entries",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_point_entries_staff_member_id"),
        "staff_point_entries",
        ["staff_member_id"],
        unique=False,
    )
    op.create_index(
        "ix_staff_points_staff_created",
        "staff_point_entries",
        ["staff_member_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "payroll_statements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("staff_member_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "pay_type",
            sa.Enum(
                "SALARY",
                "PROFIT_SHARE",
                name="compensationtype",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("pay_rate", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("profit_basis", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column(
            "base_compensation", sa.Numeric(precision=16, scale=2), nullable=False
        ),
        sa.Column("points_total", sa.Integer(), nullable=False),
        sa.Column("point_value", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "points_adjustment", sa.Numeric(precision=16, scale=2), nullable=False
        ),
        sa.Column("payable_total", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("worked_minutes", sa.Integer(), nullable=False),
        sa.Column("attendance_count", sa.Integer(), nullable=False),
        sa.Column("entry_checklists_completed", sa.Integer(), nullable=False),
        sa.Column("exit_checklists_completed", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT", "PAID", name="payrollstatus", native_enum=False, length=16
            ),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("paid_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("period_end >= period_start", name="ck_payroll_period"),
        sa.CheckConstraint("pay_rate >= 0", name="ck_payroll_pay_rate"),
        sa.CheckConstraint("base_compensation >= 0", name="ck_payroll_base"),
        sa.CheckConstraint("payable_total >= 0", name="ck_payroll_total"),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name="fk_payroll_created_by"
        ),
        sa.ForeignKeyConstraint(
            ["paid_by_id"], ["users.id"], name="fk_payroll_paid_by"
        ),
        sa.ForeignKeyConstraint(
            ["staff_member_id"], ["staff_members.id"], name="fk_payroll_staff"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "staff_member_id",
            "period_start",
            "period_end",
            name="uq_payroll_staff_period",
        ),
    )
    op.create_index(
        op.f("ix_payroll_statements_created_at"),
        "payroll_statements",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payroll_statements_pay_type"),
        "payroll_statements",
        ["pay_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payroll_statements_period_end"),
        "payroll_statements",
        ["period_end"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payroll_statements_period_start"),
        "payroll_statements",
        ["period_start"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payroll_statements_staff_member_id"),
        "payroll_statements",
        ["staff_member_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payroll_statements_status"),
        "payroll_statements",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_payroll_period_status",
        "payroll_statements",
        ["period_start", "period_end", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("payroll_statements")
    op.drop_table("staff_point_entries")
    op.drop_table("point_policies")
    op.drop_index(
        op.f("ix_attendance_checklist_completions_phase"),
        table_name="attendance_checklist_completions",
    )
    op.drop_column("attendance_checklist_completions", "phase")
    op.drop_index(
        op.f("ix_check_in_checklist_items_phase"), table_name="check_in_checklist_items"
    )
    op.drop_column("check_in_checklist_items", "phase")
    op.drop_column("attendance_records", "exit_checklist_completed_at")
    op.drop_column("attendance_records", "entry_checklist_completed_at")
    op.drop_constraint("ck_staff_point_value", "staff_members", type_="check")
    op.drop_constraint("ck_staff_pay_rate", "staff_members", type_="check")
    op.drop_index(op.f("ix_staff_members_pay_type"), table_name="staff_members")
    op.drop_column("staff_members", "point_value")
    op.drop_column("staff_members", "pay_rate")
    op.drop_column("staff_members", "pay_type")
