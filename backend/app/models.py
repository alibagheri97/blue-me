from __future__ import annotations

import enum
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class UserRole(str, enum.Enum):
    ROOT = "root"
    STORAGE_MANAGER = "storage_manager"
    ACCOUNTING_MANAGER = "accounting_manager"
    SALES_MANAGER = "sales_manager"
    KITCHEN_MANAGER = "kitchen_manager"


class MovementType(str, enum.Enum):
    RECEIVE = "receive"
    ADJUST = "adjust"
    CONSUME = "consume"
    SALE = "sale"
    WASTE = "waste"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class PriceType(str, enum.Enum):
    PURCHASE = "purchase"
    SELLING = "selling"


class OrderStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderType(str, enum.Enum):
    DINE_IN = "dine_in"
    TAKEAWAY = "takeaway"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    ONLINE = "online"
    OTHER = "other"


class ChecklistPhase(str, enum.Enum):
    ENTRY = "entry"
    EXIT = "exit"


class CompensationType(str, enum.Enum):
    SALARY = "salary"
    PROFIT_SHARE = "profit_share"


class PointSource(str, enum.Enum):
    MANUAL = "manual"
    CHECK_IN = "check_in"
    ENTRY_CHECKLIST = "entry_checklist"
    CHECK_OUT = "check_out"
    EXIT_CHECKLIST = "exit_checklist"
    WORK_HOURS = "work_hours"


class PayrollStatus(str, enum.Enum):
    DRAFT = "draft"
    PAID = "paid"


class NeedPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NeedSource(str, enum.Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class PurchaseStatus(str, enum.Enum):
    POSTED = "posted"
    VOIDED = "voided"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    staff_profile: Mapped[StaffMember | None] = relationship(
        back_populates="user", uselist=False
    )


class SystemSetting(TimestampMixin, Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    kitchen_workflow_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    updated_by: Mapped[User | None] = relationship()


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    color: Mapped[str] = mapped_column(String(7), default="#2563eb")
    items: Mapped[list[InventoryItem]] = relationship(back_populates="category")


class InventoryItem(TimestampMixin, Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        Index("ix_inventory_category_active", "category_id", "is_active"),
        Index("ix_inventory_name_sku", "name", "sku"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    unit: Mapped[str] = mapped_column(String(32), default="unit")
    current_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    target_stock_level: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("0")
    )
    auto_reorder_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    last_purchase_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    purchase_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("1")
    )
    purchase_unit: Mapped[str] = mapped_column(String(32), default="عدد")
    purchase_total_price: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    selling_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("1")
    )
    selling_unit: Mapped[str] = mapped_column(String(32), default="عدد")
    selling_total_price: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    category: Mapped[Category | None] = relationship(back_populates="items")
    movements: Mapped[list[StockMovement]] = relationship(back_populates="item")


class PurchaseReceipt(Base):
    __tablename__ = "purchase_receipts"
    __table_args__ = (
        Index("ix_purchase_receipt_date_status", "purchased_at", "status"),
        Index("ix_purchase_receipt_supplier", "supplier_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    supplier_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    purchased_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    discount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    extra_cost: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    status: Mapped[PurchaseStatus] = mapped_column(
        Enum(PurchaseStatus, native_enum=False, length=20),
        default=PurchaseStatus.POSTED,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    voided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    lines: Mapped[list[PurchaseLine]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan"
    )


class PurchaseLine(Base):
    __tablename__ = "purchase_lines"
    __table_args__ = (Index("ix_purchase_line_item_receipt", "inventory_item_id", "receipt_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_receipts.id", ondelete="CASCADE"), index=True
    )
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    item_name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    purchase_unit: Mapped[str] = mapped_column(String(32))
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=1)
    stock_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    stock_unit: Mapped[str] = mapped_column(String(32))
    line_total: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    allocated_cost: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    landed_total: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    receipt: Mapped[PurchaseReceipt] = relationship(back_populates="lines")
    inventory_item: Mapped[InventoryItem] = relationship()


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (Index("ix_movement_item_created", "item_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    movement_type: Mapped[MovementType] = mapped_column(Enum(MovementType, native_enum=False), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    quantity_before: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    quantity_after: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    reason: Mapped[str] = mapped_column(String(500))
    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    item: Mapped[InventoryItem] = relationship(back_populates="movements")


class PriceChangeRequest(Base):
    __tablename__ = "price_change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    price_type: Mapped[PriceType] = mapped_column(
        Enum(PriceType, native_enum=False, length=20),
        default=PriceType.SELLING,
        index=True,
    )
    old_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    requested_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    package_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    package_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    package_total_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, native_enum=False, length=20),
        default=ApprovalStatus.PENDING,
        index=True,
    )
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    item: Mapped[InventoryItem] = relationship()
    requested_by: Mapped[User] = relationship(foreign_keys=[requested_by_id])


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class StaffMember(TimestampMixin, Base):
    __tablename__ = "staff_members"
    __table_args__ = (
        CheckConstraint(
            "pay_rate >= 0 AND (pay_type <> 'PROFIT_SHARE' OR pay_rate <= 100)",
            name="ck_staff_pay_rate",
        ),
        CheckConstraint("point_value >= 0", name="ck_staff_point_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    phone: Mapped[str | None] = mapped_column(
        String(32), unique=True, nullable=True, index=True
    )
    position: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), unique=True, nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pay_type: Mapped[CompensationType] = mapped_column(
        Enum(CompensationType, native_enum=False, length=24),
        default=CompensationType.SALARY,
        index=True,
    )
    pay_rate: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    point_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    user: Mapped[User | None] = relationship(back_populates="staff_profile")
    orders: Mapped[list[Order]] = relationship(back_populates="staff_member")
    attendance_records: Mapped[list[AttendanceRecord]] = relationship(
        back_populates="staff_member", cascade="all, delete-orphan"
    )


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        Index("ix_attendance_staff_check_in", "staff_member_id", "checked_in_at"),
        Index("ix_attendance_open_shift", "staff_member_id", "checked_out_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_member_id: Mapped[int] = mapped_column(
        ForeignKey("staff_members.id"), index=True
    )
    checked_in_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    checked_out_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    checked_in_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    checked_out_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    check_in_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    check_out_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )
    staff_member: Mapped[StaffMember] = relationship(
        back_populates="attendance_records"
    )
    checked_in_by: Mapped[User] = relationship(foreign_keys=[checked_in_by_id])
    checked_out_by: Mapped[User | None] = relationship(
        foreign_keys=[checked_out_by_id]
    )
    checklist_completions: Mapped[list[AttendanceChecklistCompletion]] = relationship(
        back_populates="attendance_record", cascade="all, delete-orphan"
    )
    entry_checklist_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    exit_checklist_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )


class CheckInChecklistItem(TimestampMixin, Base):
    __tablename__ = "check_in_checklist_items"
    __table_args__ = (
        Index(
            "ix_check_in_checklist_user_active_order",
            "user_id",
            "is_active",
            "sort_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phase: Mapped[ChecklistPhase] = mapped_column(
        Enum(ChecklistPhase, native_enum=False, length=16),
        default=ChecklistPhase.ENTRY,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    completions: Mapped[list[AttendanceChecklistCompletion]] = relationship(
        back_populates="checklist_item"
    )


class AttendanceChecklistCompletion(Base):
    __tablename__ = "attendance_checklist_completions"
    __table_args__ = (
        UniqueConstraint(
            "attendance_record_id",
            "checklist_item_id",
            name="uq_attendance_checklist_record_item",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    attendance_record_id: Mapped[int] = mapped_column(
        ForeignKey("attendance_records.id", ondelete="CASCADE"), index=True
    )
    checklist_item_id: Mapped[int] = mapped_column(
        ForeignKey("check_in_checklist_items.id"), index=True
    )
    title_snapshot: Mapped[str] = mapped_column(String(200))
    phase: Mapped[ChecklistPhase] = mapped_column(
        Enum(ChecklistPhase, native_enum=False, length=16),
        default=ChecklistPhase.ENTRY,
        index=True,
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    attendance_record: Mapped[AttendanceRecord] = relationship(
        back_populates="checklist_completions"
    )
    checklist_item: Mapped[CheckInChecklistItem] = relationship(
        back_populates="completions"
    )


class PointPolicy(TimestampMixin, Base):
    __tablename__ = "point_policies"
    __table_args__ = (
        CheckConstraint("check_in_points >= 0", name="ck_point_policy_check_in"),
        CheckConstraint(
            "entry_checklist_points >= 0", name="ck_point_policy_entry_checklist"
        ),
        CheckConstraint("check_out_points >= 0", name="ck_point_policy_check_out"),
        CheckConstraint(
            "exit_checklist_points >= 0", name="ck_point_policy_exit_checklist"
        ),
        CheckConstraint("work_hour_points >= 0", name="ck_point_policy_work_hour"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    check_in_points: Mapped[int] = mapped_column(Integer, default=1)
    entry_checklist_points: Mapped[int] = mapped_column(Integer, default=2)
    check_out_points: Mapped[int] = mapped_column(Integer, default=1)
    exit_checklist_points: Mapped[int] = mapped_column(Integer, default=2)
    work_hour_points: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )


class StaffPointEntry(Base):
    __tablename__ = "staff_point_entries"
    __table_args__ = (
        CheckConstraint("points <> 0", name="ck_staff_point_nonzero"),
        Index("ix_staff_points_staff_created", "staff_member_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_member_id: Mapped[int] = mapped_column(
        ForeignKey("staff_members.id"), index=True
    )
    points: Mapped[int] = mapped_column(Integer)
    source: Mapped[PointSource] = mapped_column(
        Enum(PointSource, native_enum=False, length=24), index=True
    )
    reason: Mapped[str] = mapped_column(String(500))
    attendance_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("attendance_records.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reference_key: Mapped[str | None] = mapped_column(
        String(120), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    staff_member: Mapped[StaffMember] = relationship()
    created_by: Mapped[User | None] = relationship()


class PayrollStatement(Base):
    __tablename__ = "payroll_statements"
    __table_args__ = (
        UniqueConstraint(
            "staff_member_id",
            "period_start",
            "period_end",
            name="uq_payroll_staff_period",
        ),
        CheckConstraint("period_end >= period_start", name="ck_payroll_period"),
        CheckConstraint("pay_rate >= 0", name="ck_payroll_pay_rate"),
        CheckConstraint("base_compensation >= 0", name="ck_payroll_base"),
        CheckConstraint("payable_total >= 0", name="ck_payroll_total"),
        Index("ix_payroll_period_status", "period_start", "period_end", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_member_id: Mapped[int] = mapped_column(
        ForeignKey("staff_members.id"), index=True
    )
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    pay_type: Mapped[CompensationType] = mapped_column(
        Enum(CompensationType, native_enum=False, length=24), index=True
    )
    pay_rate: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    profit_basis: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    base_compensation: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    points_total: Mapped[int] = mapped_column(Integer, default=0)
    point_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    points_adjustment: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    payable_total: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0)
    attendance_count: Mapped[int] = mapped_column(Integer, default=0)
    entry_checklists_completed: Mapped[int] = mapped_column(Integer, default=0)
    exit_checklists_completed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[PayrollStatus] = mapped_column(
        Enum(PayrollStatus, native_enum=False, length=16),
        default=PayrollStatus.DRAFT,
        index=True,
    )
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    paid_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    staff_member: Mapped[StaffMember] = relationship()
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    paid_by: Mapped[User | None] = relationship(foreign_keys=[paid_by_id])


class MenuCategory(TimestampMixin, Base):
    __tablename__ = "menu_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    color: Mapped[str] = mapped_column(String(7), default="#2563eb")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    items: Mapped[list[MenuItem]] = relationship(back_populates="menu_category")


class MenuItem(TimestampMixin, Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(100), default="General", index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("menu_categories.id"), nullable=True, index=True
    )
    selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id"), nullable=True, index=True
    )
    stock_quantity_per_sale: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=1)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    menu_category: Mapped[MenuCategory | None] = relationship(back_populates="items")
    inventory_item: Mapped[InventoryItem | None] = relationship()
    recipe: Mapped[Recipe | None] = relationship(back_populates="menu_item", uselist=False)


class Recipe(TimestampMixin, Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), unique=True)
    yield_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=1)
    preparation_minutes: Mapped[int] = mapped_column(Integer, default=0)
    instructions: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    menu_item: Mapped[MenuItem] = relationship(back_populates="recipe")
    ingredients: Mapped[list[RecipeIngredient]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit: Mapped[str] = mapped_column(String(32))
    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    inventory_item: Mapped[InventoryItem] = relationship()


class TakeawaySupply(TimestampMixin, Base):
    __tablename__ = "takeaway_supplies"
    __table_args__ = (
        UniqueConstraint(
            "inventory_item_id", name="uq_takeaway_supply_inventory_item"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id")
    )
    quantity_per_package: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("1")
    )
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    inventory_item: Mapped[InventoryItem] = relationship()
    created_by: Mapped[User] = relationship()


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_order_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, native_enum=False), default=OrderStatus.CONFIRMED, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(160), default="Guest")
    staff_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_members.id"), nullable=True, index=True
    )
    staff_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_staff_meal: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, native_enum=False),
        default=OrderType.DINE_IN,
        server_default=OrderType.DINE_IN.name,
        index=True,
    )
    takeaway_package_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    takeaway_cost: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), default=Decimal("0"), server_default="0"
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    discount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, native_enum=False))
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    customer: Mapped[Customer | None] = relationship()
    staff_member: Mapped[StaffMember | None] = relationship(back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"))
    name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=0)
    line_cost: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    order: Mapped[Order] = relationship(back_populates="items")
    menu_item: Mapped[MenuItem] = relationship()


class DailyNeed(Base):
    __tablename__ = "daily_needs"
    __table_args__ = (Index("ix_daily_need_date_status", "required_date", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    required_date: Mapped[date] = mapped_column(Date, index=True)
    inventory_item_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_items.id"), nullable=True)
    item_name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit: Mapped[str] = mapped_column(String(32))
    priority: Mapped[NeedPriority] = mapped_column(Enum(NeedPriority, native_enum=False))
    source: Mapped[NeedSource] = mapped_column(
        Enum(NeedSource, native_enum=False, length=20),
        default=NeedSource.MANUAL,
        index=True,
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, native_enum=False, length=20),
        default=ApprovalStatus.PENDING,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity_at_creation: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    reorder_level_at_creation: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    inventory_item: Mapped[InventoryItem | None] = relationship()
    requested_by: Mapped[User] = relationship(foreign_keys=[requested_by_id])


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notification_recipient_unread", "recipient_user_id", "is_read", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(String(500))
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recipient: Mapped[User] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_actor_created", "actor_id", "created_at"),
        Index("ix_audit_category_created", "category", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_username: Mapped[str] = mapped_column(String(80), default="system")
    action: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    summary: Mapped[str] = mapped_column(String(500))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor: Mapped[User | None] = relationship()
