from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit
from app.db import get_db
from app.deps import client_ip, get_current_user, require_roles
from app.models import (
    AttendanceRecord,
    Notification,
    StaffMember,
    User,
    UserRole,
    utcnow,
)
from app.schemas import (
    AttendanceOverviewRead,
    AttendanceRecordRead,
    AttendanceStaffRead,
    AttendanceStatusRead,
)
from app.services.business_time import business_today, day_bounds

router = APIRouter(prefix="/attendance", tags=["attendance"])
root_only = require_roles(UserRole.ROOT)


def attendance_query():
    return select(AttendanceRecord).options(
        selectinload(AttendanceRecord.staff_member)
    )


def serialize_record(
    record: AttendanceRecord, *, now: datetime | None = None
) -> AttendanceRecordRead:
    effective_end = record.checked_out_at or now or utcnow()
    duration = max(
        0, int((effective_end - record.checked_in_at).total_seconds() // 60)
    )
    return AttendanceRecordRead(
        id=record.id,
        staff_member_id=record.staff_member_id,
        checked_in_by_id=record.checked_in_by_id,
        checked_out_by_id=record.checked_out_by_id,
        checked_in_at=record.checked_in_at,
        checked_out_at=record.checked_out_at,
        duration_minutes=duration,
        is_open=record.checked_out_at is None,
        staff_member=AttendanceStaffRead.model_validate(record.staff_member),
    )


def minutes_in_period(
    records: list[AttendanceRecord],
    *,
    start: datetime,
    end: datetime,
    now: datetime,
) -> int:
    total_seconds = 0.0
    for record in records:
        overlap_start = max(record.checked_in_at, start)
        overlap_end = min(record.checked_out_at or now, end)
        if overlap_end > overlap_start:
            total_seconds += (overlap_end - overlap_start).total_seconds()
    return max(0, int(total_seconds // 60))


def linked_staff_member(
    db: Session, actor: User, *, lock: bool = False
) -> StaffMember:
    query = select(StaffMember).where(StaffMember.user_id == actor.id)
    if lock:
        query = query.with_for_update()
    member = db.scalar(query)
    if member is None:
        raise HTTPException(
            status_code=409,
            detail="Your login is not linked to a staff profile",
        )
    return member


def open_session(db: Session, staff_member_id: int) -> AttendanceRecord | None:
    return db.scalar(
        attendance_query()
        .where(
            AttendanceRecord.staff_member_id == staff_member_id,
            AttendanceRecord.checked_out_at.is_(None),
        )
        .order_by(AttendanceRecord.checked_in_at.desc())
        .limit(1)
    )


def notify_roots(
    db: Session,
    *,
    record: AttendanceRecord,
    member: StaffMember,
    event: str,
) -> None:
    roots = db.scalars(
        select(User).where(User.role == UserRole.ROOT, User.is_active.is_(True))
    )
    is_check_in = event == "check_in"
    for root in roots:
        db.add(
            Notification(
                recipient_user_id=root.id,
                kind=(
                    "attendance_check_in" if is_check_in else "attendance_check_out"
                ),
                title=(
                    "ورود پرسنل ثبت شد" if is_check_in else "خروج پرسنل ثبت شد"
                ),
                message=(
                    f"{member.name} ورود خود را ثبت کرد."
                    if is_check_in
                    else f"{member.name} خروج خود را ثبت کرد."
                ),
                entity_type="attendance",
                entity_id=str(record.id),
            )
        )


def attendance_status(db: Session, actor: User) -> AttendanceStatusRead:
    member = db.scalar(
        select(StaffMember)
        .options(selectinload(StaffMember.user))
        .where(StaffMember.user_id == actor.id)
    )
    if member is None:
        return AttendanceStatusRead(
            eligible=False,
            is_checked_in=False,
            staff_member=None,
            current_session=None,
            last_session=None,
            worked_minutes_today=0,
        )
    current = open_session(db, member.id)
    last = db.scalar(
        attendance_query()
        .where(AttendanceRecord.staff_member_id == member.id)
        .order_by(AttendanceRecord.checked_in_at.desc())
        .limit(1)
    )
    today_start, today_end = day_bounds(business_today())
    today_records = list(
        db.scalars(
            attendance_query().where(
                AttendanceRecord.staff_member_id == member.id,
                AttendanceRecord.checked_in_at <= today_end,
                or_(
                    AttendanceRecord.checked_out_at.is_(None),
                    AttendanceRecord.checked_out_at >= today_start,
                ),
            )
        ).unique()
    )
    now = utcnow()
    return AttendanceStatusRead(
        eligible=member.is_active,
        is_checked_in=current is not None,
        staff_member=AttendanceStaffRead.model_validate(member),
        current_session=serialize_record(current, now=now) if current else None,
        last_session=serialize_record(last, now=now) if last else None,
        worked_minutes_today=minutes_in_period(
            today_records, start=today_start, end=today_end, now=now
        ),
    )


@router.get("/me", response_model=AttendanceStatusRead)
def my_attendance_status(
    actor: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AttendanceStatusRead:
    return attendance_status(db, actor)


@router.post(
    "/check-in", response_model=AttendanceStatusRead, status_code=status.HTTP_201_CREATED
)
def check_in(
    request: Request,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AttendanceStatusRead:
    member = linked_staff_member(db, actor, lock=True)
    if not member.is_active:
        raise HTTPException(status_code=409, detail="Your staff profile is inactive")
    if open_session(db, member.id) is not None:
        raise HTTPException(status_code=409, detail="You are already checked in")
    now = utcnow()
    record = AttendanceRecord(
        staff_member_id=member.id,
        checked_in_by_id=actor.id,
        checked_in_at=now,
        check_in_ip=client_ip(request),
    )
    db.add(record)
    db.flush()
    notify_roots(db, record=record, member=member, event="check_in")
    record_audit(
        db,
        actor=actor,
        action="check_in",
        category="attendance",
        entity_type="attendance_record",
        entity_id=record.id,
        summary=f"ورود {member.name} ثبت شد",
        details={
            "staff_member_id": member.id,
            "checked_in_at": now.isoformat(),
        },
        ip_address=client_ip(request),
    )
    db.commit()
    return attendance_status(db, actor)


@router.post("/check-out", response_model=AttendanceStatusRead)
def check_out(
    request: Request,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AttendanceStatusRead:
    member = linked_staff_member(db, actor, lock=True)
    record = open_session(db, member.id)
    if record is None:
        raise HTTPException(status_code=409, detail="You are not checked in")
    now = utcnow()
    record.checked_out_at = now
    record.checked_out_by_id = actor.id
    record.check_out_ip = client_ip(request)
    duration_minutes = max(
        0, int((now - record.checked_in_at).total_seconds() // 60)
    )
    notify_roots(db, record=record, member=member, event="check_out")
    record_audit(
        db,
        actor=actor,
        action="check_out",
        category="attendance",
        entity_type="attendance_record",
        entity_id=record.id,
        summary=f"خروج {member.name} ثبت شد",
        details={
            "staff_member_id": member.id,
            "checked_in_at": record.checked_in_at.isoformat(),
            "checked_out_at": now.isoformat(),
            "duration_minutes": duration_minutes,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    return attendance_status(db, actor)


@router.get("", response_model=AttendanceOverviewRead)
def attendance_overview(
    date_from: date | None = None,
    date_to: date | None = None,
    staff_member_id: int | None = None,
    limit: int = Query(default=500, ge=1, le=1000),
    _: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> AttendanceOverviewRead:
    today = business_today()
    selected_to = date_to or today
    selected_from = date_from or selected_to - timedelta(days=29)
    if selected_from > selected_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    if (selected_to - selected_from).days > 366:
        raise HTTPException(status_code=422, detail="Attendance range is too large")
    start, _ = day_bounds(selected_from)
    _, end = day_bounds(selected_to)
    query = attendance_query().where(
        AttendanceRecord.checked_in_at <= end,
        or_(
            AttendanceRecord.checked_out_at.is_(None),
            AttendanceRecord.checked_out_at >= start,
        ),
    )
    if staff_member_id is not None:
        query = query.where(AttendanceRecord.staff_member_id == staff_member_id)
    records = list(
        db.scalars(
            query.order_by(AttendanceRecord.checked_in_at.desc()).limit(limit)
        ).unique()
    )
    today_start, today_end = day_bounds(today)
    today_records = list(
        db.scalars(
            attendance_query().where(
                AttendanceRecord.checked_in_at <= today_end,
                or_(
                    AttendanceRecord.checked_out_at.is_(None),
                    AttendanceRecord.checked_out_at >= today_start,
                ),
            )
        ).unique()
    )
    now = utcnow()
    return AttendanceOverviewRead(
        date_from=selected_from,
        date_to=selected_to,
        present_count=db.scalar(
            select(func.count())
            .select_from(AttendanceRecord)
            .where(AttendanceRecord.checked_out_at.is_(None))
        )
        or 0,
        check_ins_today=sum(
            1
            for record in today_records
            if today_start <= record.checked_in_at <= today_end
        ),
        completed_today=sum(
            1
            for record in today_records
            if record.checked_out_at is not None
            and today_start <= record.checked_out_at <= today_end
        ),
        worked_minutes_today=minutes_in_period(
            today_records, start=today_start, end=today_end, now=now
        ),
        items=[serialize_record(record, now=now) for record in records],
    )
