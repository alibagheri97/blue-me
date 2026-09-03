from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit
from app.db import get_db
from app.deps import client_ip, get_current_user, require_roles
from app.models import (
    Notification,
    PayrollStatement,
    PayrollStatus,
    PointSource,
    StaffMember,
    StaffPointEntry,
    User,
    UserRole,
    utcnow,
)
from app.schemas import (
    CompensationContractUpdate,
    ManualPointCreate,
    MyPerformanceRead,
    PayrollCalculationRead,
    PayrollStaffRead,
    PayrollStatementCreate,
    PayrollStatementRead,
    PointPolicyRead,
    PointPolicyUpdate,
    StaffPointEntryRead,
)
from app.services.business_time import business_today
from app.services.payroll import (
    award_points,
    calculate_payroll,
    get_point_policy,
    period_profit,
)


router = APIRouter(prefix="/payroll", tags=["payroll"])
root_only = require_roles(UserRole.ROOT)


def member_or_404(db: Session, staff_member_id: int) -> StaffMember:
    member = db.scalar(
        select(StaffMember)
        .options(selectinload(StaffMember.user))
        .where(StaffMember.id == staff_member_id)
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return member


def validate_period(period_start: date, period_end: date) -> None:
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="Invalid payroll period")
    if (period_end - period_start).days > 366:
        raise HTTPException(status_code=422, detail="Payroll period is too large")


def default_period() -> tuple[date, date]:
    today = business_today()
    return today.replace(day=1), today


def notify_staff(
    db: Session,
    *,
    member: StaffMember,
    kind: str,
    title: str,
    message: str,
    entity_type: str,
    entity_id: int,
) -> None:
    if member.user_id is None:
        return
    db.add(
        Notification(
            recipient_user_id=member.user_id,
            kind=kind,
            title=title,
            message=message,
            entity_type=entity_type,
            entity_id=str(entity_id),
        )
    )


@router.get("/me", response_model=MyPerformanceRead)
def my_performance(
    actor: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> MyPerformanceRead:
    period_start, period_end = default_period()
    member = db.scalar(select(StaffMember).where(StaffMember.user_id == actor.id))
    if member is None:
        return MyPerformanceRead(
            staff_member_id=None,
            eligible=False,
            period_start=period_start,
            period_end=period_end,
            total_points=0,
            positive_points=0,
            negative_points=0,
            worked_minutes=0,
            attendance_count=0,
            entry_checklists_completed=0,
            exit_checklists_completed=0,
        )
    calculation = calculate_payroll(
        db,
        member=member,
        period_start=period_start,
        period_end=period_end,
        shared_profit_basis=0,
    )
    return MyPerformanceRead(
        staff_member_id=member.id,
        eligible=member.is_active,
        period_start=period_start,
        period_end=period_end,
        total_points=calculation.points_total,
        positive_points=calculation.positive_points,
        negative_points=calculation.negative_points,
        worked_minutes=calculation.worked_minutes,
        attendance_count=calculation.attendance_count,
        entry_checklists_completed=calculation.entry_checklists_completed,
        exit_checklists_completed=calculation.exit_checklists_completed,
    )


@router.get("/policy", response_model=PointPolicyRead)
def read_point_policy(
    _: User = Depends(root_only), db: Session = Depends(get_db)
) -> PointPolicyRead:
    policy = get_point_policy(db)
    db.commit()
    db.refresh(policy)
    return PointPolicyRead.model_validate(policy)


@router.patch("/policy", response_model=PointPolicyRead)
def update_point_policy(
    payload: PointPolicyUpdate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> PointPolicyRead:
    policy = get_point_policy(db, lock=True)
    before = {field: getattr(policy, field) for field in payload.model_fields_set}
    for field, value in payload.model_dump().items():
        setattr(policy, field, value)
    policy.updated_by_id = actor.id
    record_audit(
        db,
        actor=actor,
        action="update",
        category="payroll",
        entity_type="point_policy",
        entity_id=policy.id,
        summary="قواعد امتیازدهی خودکار پرسنل ویرایش شد",
        details={"before": before, "after": payload.model_dump()},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(policy)
    return PointPolicyRead.model_validate(policy)


@router.get("/staff", response_model=list[PayrollStaffRead])
def payroll_staff(
    _: User = Depends(root_only), db: Session = Depends(get_db)
) -> list[StaffMember]:
    return list(
        db.scalars(
            select(StaffMember)
            .options(selectinload(StaffMember.user))
            .order_by(StaffMember.is_active.desc(), StaffMember.name)
        )
    )


@router.patch("/staff/{staff_member_id}/compensation", response_model=PayrollStaffRead)
def update_compensation(
    staff_member_id: int,
    payload: CompensationContractUpdate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> StaffMember:
    member = member_or_404(db, staff_member_id)
    before = {
        "pay_type": member.pay_type.value,
        "pay_rate": str(member.pay_rate),
        "point_value": str(member.point_value),
    }
    member.pay_type = payload.pay_type
    member.pay_rate = payload.pay_rate
    member.point_value = payload.point_value
    record_audit(
        db,
        actor=actor,
        action="update",
        category="payroll",
        entity_type="compensation_contract",
        entity_id=member.id,
        summary=f"قرارداد پرداخت {member.name} ویرایش شد",
        details={
            "before": before,
            "after": {
                "pay_type": member.pay_type.value,
                "pay_rate": str(member.pay_rate),
                "point_value": str(member.point_value),
            },
        },
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(member)
    return member


@router.get("/calculations", response_model=list[PayrollCalculationRead])
def payroll_calculations(
    period_start: date | None = None,
    period_end: date | None = None,
    _: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> list[PayrollCalculationRead]:
    default_start, default_end = default_period()
    selected_start = period_start or default_start
    selected_end = period_end or default_end
    validate_period(selected_start, selected_end)
    members = list(
        db.scalars(
            select(StaffMember)
            .options(selectinload(StaffMember.user))
            .order_by(StaffMember.is_active.desc(), StaffMember.name)
        )
    )
    profit = period_profit(db, selected_start, selected_end)
    return [
        calculate_payroll(
            db,
            member=member,
            period_start=selected_start,
            period_end=selected_end,
            shared_profit_basis=profit,
        )
        for member in members
    ]


@router.get("/points", response_model=list[StaffPointEntryRead])
def point_history(
    staff_member_id: int | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    _: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> list[StaffPointEntry]:
    query = select(StaffPointEntry).options(selectinload(StaffPointEntry.created_by))
    if staff_member_id is not None:
        member_or_404(db, staff_member_id)
        query = query.where(StaffPointEntry.staff_member_id == staff_member_id)
    return list(
        db.scalars(query.order_by(StaffPointEntry.created_at.desc()).limit(limit))
    )


@router.post(
    "/points", response_model=StaffPointEntryRead, status_code=status.HTTP_201_CREATED
)
def add_manual_points(
    payload: ManualPointCreate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> StaffPointEntry:
    member = member_or_404(db, payload.staff_member_id)
    entry = award_points(
        db,
        staff_member_id=member.id,
        points=payload.points,
        source=PointSource.MANUAL,
        reason=payload.reason,
        created_by_id=actor.id,
    )
    assert entry is not None
    direction = "تشویقی" if entry.points > 0 else "اصلاحی"
    notify_staff(
        db,
        member=member,
        kind="staff_points",
        title=f"امتیاز {direction} ثبت شد",
        message=f"{entry.points:+d} امتیاز: {entry.reason}",
        entity_type="staff_point",
        entity_id=entry.id,
    )
    record_audit(
        db,
        actor=actor,
        action="create",
        category="payroll",
        entity_type="staff_point",
        entity_id=entry.id,
        summary=f"{entry.points:+d} امتیاز برای {member.name} ثبت شد",
        details={
            "staff_member_id": member.id,
            "points": entry.points,
            "reason": entry.reason,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/statements", response_model=list[PayrollStatementRead])
def list_statements(
    staff_member_id: int | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    _: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> list[PayrollStatement]:
    query = select(PayrollStatement).options(
        selectinload(PayrollStatement.staff_member).selectinload(StaffMember.user)
    )
    if staff_member_id is not None:
        query = query.where(PayrollStatement.staff_member_id == staff_member_id)
    return list(
        db.scalars(query.order_by(PayrollStatement.created_at.desc()).limit(limit))
    )


@router.post(
    "/statements",
    response_model=PayrollStatementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_statement(
    payload: PayrollStatementCreate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> PayrollStatement:
    member = member_or_404(db, payload.staff_member_id)
    duplicate = db.scalar(
        select(PayrollStatement.id).where(
            PayrollStatement.staff_member_id == member.id,
            PayrollStatement.period_start == payload.period_start,
            PayrollStatement.period_end == payload.period_end,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409, detail="A payroll statement already exists for this period"
        )
    calculation = calculate_payroll(
        db,
        member=member,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    statement = PayrollStatement(
        staff_member_id=member.id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        pay_type=member.pay_type,
        pay_rate=member.pay_rate,
        profit_basis=calculation.profit_basis,
        base_compensation=calculation.base_compensation,
        points_total=calculation.points_total,
        point_value=member.point_value,
        points_adjustment=calculation.points_adjustment,
        payable_total=calculation.payable_total,
        worked_minutes=calculation.worked_minutes,
        attendance_count=calculation.attendance_count,
        entry_checklists_completed=calculation.entry_checklists_completed,
        exit_checklists_completed=calculation.exit_checklists_completed,
        status=PayrollStatus.DRAFT,
        created_by_id=actor.id,
    )
    db.add(statement)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create",
        category="payroll",
        entity_type="payroll_statement",
        entity_id=statement.id,
        summary=f"صورت‌حساب {member.name} ثبت شد",
        details={
            "period_start": payload.period_start.isoformat(),
            "period_end": payload.period_end.isoformat(),
            "pay_type": member.pay_type.value,
            "payable_total": str(statement.payable_total),
            "points_total": statement.points_total,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    return db.scalar(
        select(PayrollStatement)
        .options(
            selectinload(PayrollStatement.staff_member).selectinload(StaffMember.user)
        )
        .where(PayrollStatement.id == statement.id)
    )


@router.post("/statements/{statement_id}/pay", response_model=PayrollStatementRead)
def mark_statement_paid(
    statement_id: int,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> PayrollStatement:
    statement = db.scalar(
        select(PayrollStatement)
        .options(
            selectinload(PayrollStatement.staff_member).selectinload(StaffMember.user)
        )
        .where(PayrollStatement.id == statement_id)
        .with_for_update()
    )
    if statement is None:
        raise HTTPException(status_code=404, detail="Payroll statement not found")
    if statement.status == PayrollStatus.PAID:
        raise HTTPException(status_code=409, detail="Payroll statement is already paid")
    statement.status = PayrollStatus.PAID
    statement.paid_by_id = actor.id
    statement.paid_at = utcnow()
    notify_staff(
        db,
        member=statement.staff_member,
        kind="payroll_paid",
        title="تسویه دوره ثبت شد",
        message="صورت‌حساب دوره شما توسط مدیریت به‌عنوان پرداخت‌شده ثبت شد.",
        entity_type="payroll_statement",
        entity_id=statement.id,
    )
    record_audit(
        db,
        actor=actor,
        action="pay",
        category="payroll",
        entity_type="payroll_statement",
        entity_id=statement.id,
        summary=f"صورت‌حساب {statement.staff_member.name} پرداخت شد",
        details={"payable_total": str(statement.payable_total)},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(statement)
    return statement
