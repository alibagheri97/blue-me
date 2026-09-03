from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit
from app.db import get_db
from app.deps import client_ip, get_authenticated_user, require_roles
from app.models import (
    AttendanceChecklistCompletion,
    AttendanceRecord,
    ChecklistPhase,
    CheckInChecklistItem,
    Notification,
    PointSource,
    StaffMember,
    User,
    UserRole,
    utcnow,
)
from app.schemas import (
    AttendanceChecklistCompletionRead,
    AttendanceOverviewRead,
    AttendanceRecordRead,
    AttendanceStaffRead,
    AttendanceStatusRead,
    ChecklistCompletionRequest,
    CheckInChecklistItemCreate,
    CheckInChecklistItemRead,
    CheckInChecklistItemUpdate,
    CheckInRequest,
    CheckOutRequest,
)
from app.services.business_time import business_today, day_bounds
from app.services.payroll import award_points, get_point_policy

router = APIRouter(prefix="/attendance", tags=["attendance"])
root_only = require_roles(UserRole.ROOT)
role_positions = {
    UserRole.ROOT: "مدیر کل",
    UserRole.STORAGE_MANAGER: "مدیر انبار",
    UserRole.ACCOUNTING_MANAGER: "مدیر حسابداری",
    UserRole.SALES_MANAGER: "مدیر فروش",
    UserRole.KITCHEN_MANAGER: "مدیر آشپزخانه",
}


def attendance_query():
    return select(AttendanceRecord).options(
        selectinload(AttendanceRecord.staff_member),
        selectinload(AttendanceRecord.checklist_completions),
    )


def active_checklist_items(
    db: Session,
    user_id: int,
    *,
    phase: ChecklistPhase = ChecklistPhase.ENTRY,
    lock: bool = False,
):
    query = (
        select(CheckInChecklistItem)
        .where(
            CheckInChecklistItem.user_id == user_id,
            CheckInChecklistItem.is_active.is_(True),
            CheckInChecklistItem.phase == phase,
        )
        .order_by(CheckInChecklistItem.sort_order, CheckInChecklistItem.id)
    )
    if lock:
        query = query.with_for_update()
    return list(db.scalars(query))


def checklist_item_or_404(db: Session, item_id: int) -> CheckInChecklistItem:
    item = db.get(CheckInChecklistItem, item_id)
    if item is None or not item.is_active:
        raise HTTPException(status_code=404, detail="Check-in checklist item not found")
    return item


def ensure_checklist_staff(db: Session, user: User) -> StaffMember:
    member = db.scalar(select(StaffMember).where(StaffMember.user_id == user.id))
    if member is None:
        member = StaffMember(
            name=user.full_name,
            position=role_positions[user.role],
            user_id=user.id,
            is_active=True,
            notes="ایجاد خودکار برای چک‌لیست ثبت ورود",
        )
        db.add(member)
        db.flush()
    if not member.is_active:
        raise HTTPException(status_code=409, detail="Staff profile is inactive")
    return member


def duplicate_checklist_title(
    db: Session,
    *,
    user_id: int,
    phase: ChecklistPhase,
    title: str,
    exclude_id: int | None = None,
) -> bool:
    query = select(CheckInChecklistItem.id).where(
        CheckInChecklistItem.user_id == user_id,
        CheckInChecklistItem.is_active.is_(True),
        CheckInChecklistItem.phase == phase,
        func.lower(CheckInChecklistItem.title) == title.lower(),
    )
    if exclude_id is not None:
        query = query.where(CheckInChecklistItem.id != exclude_id)
    return db.scalar(query.limit(1)) is not None


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
        checklist_completions=[
            AttendanceChecklistCompletionRead.model_validate(completion)
            for completion in sorted(
                record.checklist_completions,
                key=lambda completion: completion.id,
            )
        ],
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
    event_copy = {
        "check_in": (
            "attendance_check_in",
            "ورود پرسنل ثبت شد",
            f"{member.name} ورود خود را ثبت کرد.",
        ),
        "entry_checklist": (
            "attendance_entry_checklist",
            "چک‌لیست شروع کار تکمیل شد",
            f"{member.name} همه موارد پس از ورود را تأیید کرد.",
        ),
        "check_out": (
            "attendance_check_out",
            "خروج پرسنل ثبت شد",
            f"{member.name} خروج خود را ثبت کرد.",
        ),
    }
    kind, title, message = event_copy[event]
    for root in roots:
        db.add(
            Notification(
                recipient_user_id=root.id,
                kind=kind,
                title=title,
                message=message,
                entity_type="attendance",
                entity_id=str(record.id),
            )
        )


def attendance_status(db: Session, actor: User) -> AttendanceStatusRead:
    checklist_items = active_checklist_items(
        db, actor.id, phase=ChecklistPhase.ENTRY
    )
    checkout_items = active_checklist_items(
        db, actor.id, phase=ChecklistPhase.EXIT
    )
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
            checklist_required=bool(checklist_items),
            checklist_items=[
                CheckInChecklistItemRead.model_validate(item)
                for item in checklist_items
            ],
            entry_allowed=not checklist_items,
            entry_checklist_completed=not checklist_items,
            checkout_checklist_required=False,
            checkout_checklist_items=[
                CheckInChecklistItemRead.model_validate(item)
                for item in checkout_items
            ],
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
    entry_completed = not checklist_items or (
        current is not None and current.entry_checklist_completed_at is not None
    )
    return AttendanceStatusRead(
        eligible=member.is_active,
        is_checked_in=current is not None,
        staff_member=AttendanceStaffRead.model_validate(member),
        current_session=serialize_record(current, now=now) if current else None,
        last_session=serialize_record(last, now=now) if last else None,
        worked_minutes_today=minutes_in_period(
            today_records, start=today_start, end=today_end, now=now
        ),
        checklist_required=bool(checklist_items),
        checklist_items=[
            CheckInChecklistItemRead.model_validate(item) for item in checklist_items
        ],
        entry_allowed=entry_completed,
        entry_checklist_completed=entry_completed,
        checkout_checklist_required=current is not None and bool(checkout_items),
        checkout_checklist_items=[
            CheckInChecklistItemRead.model_validate(item) for item in checkout_items
        ],
    )


@router.get("/checklists", response_model=list[CheckInChecklistItemRead])
def list_checklists(
    user_id: int,
    phase: ChecklistPhase | None = None,
    include_inactive: bool = False,
    _: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> list[CheckInChecklistItem]:
    query = select(CheckInChecklistItem).where(
        CheckInChecklistItem.user_id == user_id
    )
    if not include_inactive:
        query = query.where(CheckInChecklistItem.is_active.is_(True))
    if phase is not None:
        query = query.where(CheckInChecklistItem.phase == phase)
    return list(
        db.scalars(
            query.order_by(CheckInChecklistItem.sort_order, CheckInChecklistItem.id)
        )
    )


@router.post(
    "/checklists",
    response_model=CheckInChecklistItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_checklist_item(
    payload: CheckInChecklistItemCreate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> CheckInChecklistItem:
    target = db.get(User, payload.user_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Checklist user not found")
    member = ensure_checklist_staff(db, target)
    if duplicate_checklist_title(
        db, user_id=target.id, phase=payload.phase, title=payload.title
    ):
        raise HTTPException(status_code=409, detail="Checklist item already exists")
    sort_order = payload.sort_order
    if sort_order is None:
        sort_order = (
            db.scalar(
                select(func.max(CheckInChecklistItem.sort_order)).where(
                    CheckInChecklistItem.user_id == target.id,
                    CheckInChecklistItem.is_active.is_(True),
                    CheckInChecklistItem.phase == payload.phase,
                )
            )
            or 0
        ) + 10
    item = CheckInChecklistItem(
        user_id=target.id,
        title=payload.title,
        description=payload.description,
        phase=payload.phase,
        sort_order=sort_order,
        created_by_id=actor.id,
    )
    db.add(item)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create",
        category="attendance",
        entity_type="check_in_checklist_item",
        entity_id=item.id,
        summary=f"مورد چک‌لیست {payload.phase.value} برای {target.full_name} اضافه شد",
        details={
            "user_id": target.id,
            "staff_member_id": member.id,
            "title": item.title,
            "phase": item.phase.value,
            "sort_order": item.sort_order,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(item)
    return item


@router.patch(
    "/checklists/{item_id}", response_model=CheckInChecklistItemRead
)
def update_checklist_item(
    item_id: int,
    payload: CheckInChecklistItemUpdate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> CheckInChecklistItem:
    item = checklist_item_or_404(db, item_id)
    before = {
        "title": item.title,
        "description": item.description,
        "sort_order": item.sort_order,
        "phase": item.phase.value,
    }
    target_phase = payload.phase or item.phase
    target_title = payload.title if payload.title is not None else item.title
    if "title" in payload.model_fields_set or "phase" in payload.model_fields_set:
        if duplicate_checklist_title(
            db,
            user_id=item.user_id,
            phase=target_phase,
            title=target_title,
            exclude_id=item.id,
        ):
            raise HTTPException(status_code=409, detail="Checklist item already exists")
    if "title" in payload.model_fields_set:
        assert payload.title is not None
        item.title = payload.title
    if "description" in payload.model_fields_set:
        item.description = payload.description
    if "sort_order" in payload.model_fields_set:
        assert payload.sort_order is not None
        item.sort_order = payload.sort_order
    if "phase" in payload.model_fields_set:
        assert payload.phase is not None
        item.phase = payload.phase
    record_audit(
        db,
        actor=actor,
        action="update",
        category="attendance",
        entity_type="check_in_checklist_item",
        entity_id=item.id,
        summary="مورد چک‌لیست حضور ویرایش شد",
        details={
            "user_id": item.user_id,
            "before": before,
            "after": {
                "title": item.title,
                "description": item.description,
                "sort_order": item.sort_order,
                "phase": item.phase.value,
            },
        },
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(item)
    return item


@router.delete("/checklists/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_checklist_item(
    item_id: int,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> None:
    item = checklist_item_or_404(db, item_id)
    item.is_active = False
    record_audit(
        db,
        actor=actor,
        action="delete",
        category="attendance",
        entity_type="check_in_checklist_item",
        entity_id=item.id,
        summary="مورد چک‌لیست حضور حذف شد",
        details={
            "user_id": item.user_id,
            "title": item.title,
            "phase": item.phase.value,
        },
        ip_address=client_ip(request),
    )
    db.commit()


@router.get("/me", response_model=AttendanceStatusRead)
def my_attendance_status(
    actor: User = Depends(get_authenticated_user), db: Session = Depends(get_db)
) -> AttendanceStatusRead:
    return attendance_status(db, actor)


@router.post(
    "/check-in", response_model=AttendanceStatusRead, status_code=status.HTTP_201_CREATED
)
def check_in(
    request: Request,
    _: CheckInRequest = Body(default_factory=CheckInRequest),
    actor: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> AttendanceStatusRead:
    member = linked_staff_member(db, actor, lock=True)
    if not member.is_active:
        raise HTTPException(status_code=409, detail="Your staff profile is inactive")
    if open_session(db, member.id) is not None:
        raise HTTPException(status_code=409, detail="You are already checked in")
    checklist_items = active_checklist_items(
        db, actor.id, phase=ChecklistPhase.ENTRY, lock=True
    )
    now = utcnow()
    record = AttendanceRecord(
        staff_member_id=member.id,
        checked_in_by_id=actor.id,
        checked_in_at=now,
        check_in_ip=client_ip(request),
        entry_checklist_completed_at=None if checklist_items else now,
    )
    db.add(record)
    db.flush()
    policy = get_point_policy(db)
    award_points(
        db,
        staff_member_id=member.id,
        points=policy.check_in_points,
        source=PointSource.CHECK_IN,
        reason="ثبت منظم ورود به شیفت",
        created_by_id=actor.id,
        attendance_record_id=record.id,
        reference_key=f"attendance:{record.id}:check_in",
    )
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
            "entry_checklist_required": bool(checklist_items),
            "awarded_points": policy.check_in_points,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    return attendance_status(db, actor)


@router.post("/check-in-checklist", response_model=AttendanceStatusRead)
def complete_check_in_checklist(
    payload: ChecklistCompletionRequest,
    request: Request,
    actor: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> AttendanceStatusRead:
    member = linked_staff_member(db, actor, lock=True)
    record = open_session(db, member.id)
    if record is None:
        raise HTTPException(status_code=409, detail="Check in before completing the checklist")
    if record.entry_checklist_completed_at is not None:
        raise HTTPException(status_code=409, detail="Entry checklist is already completed")
    checklist_items = active_checklist_items(
        db, actor.id, phase=ChecklistPhase.ENTRY, lock=True
    )
    required_ids = {item.id for item in checklist_items}
    submitted_ids = set(payload.checklist_item_ids)
    if submitted_ids != required_ids:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CHECKLIST_INCOMPLETE",
                "message": "All required entry checklist items must be completed",
                "missing_items": [
                    item.title for item in checklist_items if item.id not in submitted_ids
                ],
            },
        )
    now = utcnow()
    for item in checklist_items:
        db.add(
            AttendanceChecklistCompletion(
                attendance_record=record,
                checklist_item_id=item.id,
                title_snapshot=item.title,
                phase=ChecklistPhase.ENTRY,
                completed_at=now,
            )
        )
    record.entry_checklist_completed_at = now
    policy = get_point_policy(db)
    award_points(
        db,
        staff_member_id=member.id,
        points=policy.entry_checklist_points,
        source=PointSource.ENTRY_CHECKLIST,
        reason="تکمیل کامل چک‌لیست شروع کار",
        created_by_id=actor.id,
        attendance_record_id=record.id,
        reference_key=f"attendance:{record.id}:entry_checklist",
    )
    notify_roots(db, record=record, member=member, event="entry_checklist")
    record_audit(
        db,
        actor=actor,
        action="complete_entry_checklist",
        category="attendance",
        entity_type="attendance_record",
        entity_id=record.id,
        summary=f"چک‌لیست شروع کار {member.name} تکمیل شد",
        details={
            "staff_member_id": member.id,
            "completed_at": now.isoformat(),
            "checklist_items": [item.title for item in checklist_items],
            "awarded_points": policy.entry_checklist_points,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    return attendance_status(db, actor)


@router.post("/check-out", response_model=AttendanceStatusRead)
def check_out(
    request: Request,
    payload: CheckOutRequest = Body(default_factory=CheckOutRequest),
    actor: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> AttendanceStatusRead:
    member = linked_staff_member(db, actor, lock=True)
    record = open_session(db, member.id)
    if record is None:
        raise HTTPException(status_code=409, detail="You are not checked in")
    checklist_items = active_checklist_items(
        db, actor.id, phase=ChecklistPhase.EXIT, lock=True
    )
    required_ids = {item.id for item in checklist_items}
    submitted_ids = set(payload.checklist_item_ids)
    if submitted_ids != required_ids:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CHECKOUT_CHECKLIST_INCOMPLETE",
                "message": "All required checkout checklist items must be completed",
                "missing_items": [
                    item.title for item in checklist_items if item.id not in submitted_ids
                ],
            },
        )
    now = utcnow()
    for item in checklist_items:
        db.add(
            AttendanceChecklistCompletion(
                attendance_record=record,
                checklist_item_id=item.id,
                title_snapshot=item.title,
                phase=ChecklistPhase.EXIT,
                completed_at=now,
            )
        )
    record.exit_checklist_completed_at = now if checklist_items else None
    record.checked_out_at = now
    record.checked_out_by_id = actor.id
    record.check_out_ip = client_ip(request)
    duration_minutes = max(
        0, int((now - record.checked_in_at).total_seconds() // 60)
    )
    policy = get_point_policy(db)
    award_points(
        db,
        staff_member_id=member.id,
        points=policy.check_out_points,
        source=PointSource.CHECK_OUT,
        reason="ثبت منظم خروج از شیفت",
        created_by_id=actor.id,
        attendance_record_id=record.id,
        reference_key=f"attendance:{record.id}:check_out",
    )
    if checklist_items:
        award_points(
            db,
            staff_member_id=member.id,
            points=policy.exit_checklist_points,
            source=PointSource.EXIT_CHECKLIST,
            reason="تکمیل کامل چک‌لیست پایان کار",
            created_by_id=actor.id,
            attendance_record_id=record.id,
            reference_key=f"attendance:{record.id}:exit_checklist",
        )
    completed_hours = duration_minutes // 60
    award_points(
        db,
        staff_member_id=member.id,
        points=completed_hours * policy.work_hour_points,
        source=PointSource.WORK_HOURS,
        reason=f"{completed_hours} ساعت کامل حضور ثبت‌شده",
        created_by_id=actor.id,
        attendance_record_id=record.id,
        reference_key=f"attendance:{record.id}:work_hours",
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
            "checkout_checklist_items": [item.title for item in checklist_items],
            "awarded_points": {
                "check_out": policy.check_out_points,
                "exit_checklist": (
                    policy.exit_checklist_points if checklist_items else 0
                ),
                "work_hours": completed_hours * policy.work_hour_points,
            },
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
