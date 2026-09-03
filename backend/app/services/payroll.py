from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AttendanceRecord,
    CompensationType,
    Order,
    OrderStatus,
    PointPolicy,
    PointSource,
    StaffMember,
    StaffPointEntry,
    utcnow,
)
from app.schemas import PayrollCalculationRead, PayrollStaffRead
from app.services.business_time import day_bounds


POINT_POLICY_ID = 1
MONEY_STEP = Decimal("0.01")


def get_point_policy(db: Session, *, lock: bool = False) -> PointPolicy:
    query = select(PointPolicy).where(PointPolicy.id == POINT_POLICY_ID)
    if lock:
        query = query.with_for_update()
    policy = db.scalar(query)
    if policy is None:
        policy = PointPolicy(id=POINT_POLICY_ID)
        db.add(policy)
        db.flush()
    return policy


def award_points(
    db: Session,
    *,
    staff_member_id: int,
    points: int,
    source: PointSource,
    reason: str,
    created_by_id: int | None,
    attendance_record_id: int | None = None,
    reference_key: str | None = None,
) -> StaffPointEntry | None:
    if points == 0:
        return None
    if reference_key:
        existing = db.scalar(
            select(StaffPointEntry).where(
                StaffPointEntry.reference_key == reference_key
            )
        )
        if existing is not None:
            return existing
    entry = StaffPointEntry(
        staff_member_id=staff_member_id,
        points=points,
        source=source,
        reason=reason,
        attendance_record_id=attendance_record_id,
        created_by_id=created_by_id,
        reference_key=reference_key,
    )
    db.add(entry)
    db.flush()
    return entry


def period_datetimes(period_start: date, period_end: date) -> tuple[datetime, datetime]:
    start, _ = day_bounds(period_start)
    _, end = day_bounds(period_end)
    return start, end


def period_profit(db: Session, period_start: date, period_end: date) -> Decimal:
    start, end = period_datetimes(period_start, period_end)
    orders = list(
        db.scalars(
            select(Order)
            .options(selectinload(Order.items))
            .where(
                Order.created_at.between(start, end),
                Order.status != OrderStatus.CANCELLED,
                Order.is_staff_meal.is_(False),
                Order.is_deleted.is_(False),
            )
        ).unique()
    )
    revenue = sum((Decimal(order.total) for order in orders), Decimal("0"))
    costs = sum(
        (
            sum((Decimal(line.line_cost) for line in order.items), Decimal("0"))
            + Decimal(order.takeaway_cost)
            for order in orders
        ),
        Decimal("0"),
    )
    return max(Decimal("0"), revenue - costs).quantize(
        MONEY_STEP, rounding=ROUND_HALF_UP
    )


def attendance_metrics(
    db: Session,
    *,
    staff_member_id: int,
    period_start: date,
    period_end: date,
) -> tuple[int, int, int, int]:
    start, end = period_datetimes(period_start, period_end)
    records = list(
        db.scalars(
            select(AttendanceRecord).where(
                AttendanceRecord.staff_member_id == staff_member_id,
                AttendanceRecord.checked_in_at <= end,
                or_(
                    AttendanceRecord.checked_out_at.is_(None),
                    AttendanceRecord.checked_out_at >= start,
                ),
            )
        )
    )
    now = utcnow()
    seconds = 0.0
    for record in records:
        overlap_start = max(start, record.checked_in_at)
        overlap_end = min(end, record.checked_out_at or now)
        if overlap_end > overlap_start:
            seconds += (overlap_end - overlap_start).total_seconds()
    attendance_count = sum(
        1 for record in records if start <= record.checked_in_at <= end
    )
    entry_completed = sum(
        1
        for record in records
        if record.entry_checklist_completed_at is not None
        and start <= record.entry_checklist_completed_at <= end
    )
    exit_completed = sum(
        1
        for record in records
        if record.exit_checklist_completed_at is not None
        and start <= record.exit_checklist_completed_at <= end
    )
    return max(0, int(seconds // 60)), attendance_count, entry_completed, exit_completed


def point_metrics(
    db: Session,
    *,
    staff_member_id: int,
    period_start: date,
    period_end: date,
) -> tuple[int, int, int]:
    start, end = period_datetimes(period_start, period_end)
    values = list(
        db.scalars(
            select(StaffPointEntry.points).where(
                StaffPointEntry.staff_member_id == staff_member_id,
                StaffPointEntry.created_at.between(start, end),
            )
        )
    )
    positive = sum(value for value in values if value > 0)
    negative = sum(value for value in values if value < 0)
    return sum(values), positive, negative


def calculate_payroll(
    db: Session,
    *,
    member: StaffMember,
    period_start: date,
    period_end: date,
    shared_profit_basis: Decimal | None = None,
) -> PayrollCalculationRead:
    if period_start > period_end:
        raise ValueError("Invalid payroll period")
    profit_basis = (
        period_profit(db, period_start, period_end)
        if shared_profit_basis is None
        else shared_profit_basis
    )
    pay_rate = Decimal(member.pay_rate)
    if member.pay_type == CompensationType.SALARY:
        base = pay_rate
    else:
        base = profit_basis * pay_rate / Decimal("100")
    base = base.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)
    points_total, positive_points, negative_points = point_metrics(
        db,
        staff_member_id=member.id,
        period_start=period_start,
        period_end=period_end,
    )
    point_value = Decimal(member.point_value)
    points_adjustment = (point_value * points_total).quantize(
        MONEY_STEP, rounding=ROUND_HALF_UP
    )
    payable = max(Decimal("0"), base + points_adjustment).quantize(
        MONEY_STEP, rounding=ROUND_HALF_UP
    )
    worked, attendance_count, entry_completed, exit_completed = attendance_metrics(
        db,
        staff_member_id=member.id,
        period_start=period_start,
        period_end=period_end,
    )
    return PayrollCalculationRead(
        staff_member=PayrollStaffRead.model_validate(member),
        period_start=period_start,
        period_end=period_end,
        profit_basis=profit_basis,
        base_compensation=base,
        points_total=points_total,
        positive_points=positive_points,
        negative_points=negative_points,
        point_value=point_value,
        points_adjustment=points_adjustment,
        payable_total=payable,
        worked_minutes=worked,
        attendance_count=attendance_count,
        entry_checklists_completed=entry_completed,
        exit_checklists_completed=exit_completed,
    )
