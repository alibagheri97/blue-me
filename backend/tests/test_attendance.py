from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceRecord,
    AuditLog,
    Notification,
    StaffMember,
    User,
    UserRole,
)
from app.services.business_time import business_today, day_bounds


def linked_staff(db: Session, role: UserRole, *, active: bool = True) -> StaffMember:
    user = db.scalar(select(User).where(User.role == role))
    assert user is not None
    member = StaffMember(
        name=user.full_name,
        position="پرسنل تست حضور",
        user_id=user.id,
        is_active=active,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def test_staff_check_in_and_check_out_are_saved_notified_and_audited(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    member = linked_staff(db_session, UserRole.ACCOUNTING_MANAGER)

    initial = client.get("/attendance/me", headers=accounting_headers)
    assert initial.status_code == 200
    assert initial.json()["eligible"] is True
    assert initial.json()["is_checked_in"] is False
    assert initial.json()["staff_member"]["id"] == member.id

    checked_in = client.post("/attendance/check-in", headers=accounting_headers)
    assert checked_in.status_code == 201, checked_in.text
    status_data = checked_in.json()
    assert status_data["is_checked_in"] is True
    assert status_data["current_session"]["is_open"] is True
    record_id = status_data["current_session"]["id"]

    duplicate = client.post("/attendance/check-in", headers=accounting_headers)
    assert duplicate.status_code == 409
    assert db_session.scalar(select(AttendanceRecord).where(AttendanceRecord.id == record_id))

    root_notifications = client.get("/notifications", headers=root_headers)
    assert root_notifications.status_code == 200
    attendance_notification = next(
        item
        for item in root_notifications.json()["items"]
        if item["entity_type"] == "attendance"
    )
    assert attendance_notification["kind"] == "attendance_check_in"
    assert member.name in attendance_notification["message"]

    overview = client.get("/attendance", headers=root_headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["present_count"] == 1
    assert overview.json()["check_ins_today"] == 1
    assert overview.json()["items"][0]["staff_member"]["id"] == member.id
    assert client.get("/attendance", headers=accounting_headers).status_code == 403

    record = db_session.get(AttendanceRecord, record_id)
    assert record is not None
    record.checked_in_at -= timedelta(minutes=95)
    db_session.commit()

    checked_out = client.post("/attendance/check-out", headers=accounting_headers)
    assert checked_out.status_code == 200, checked_out.text
    checkout_data = checked_out.json()
    assert checkout_data["is_checked_in"] is False
    assert checkout_data["current_session"] is None
    assert checkout_data["last_session"]["is_open"] is False
    db_session.refresh(record)
    expected_duration = max(
        0,
        int((record.checked_out_at - record.checked_in_at).total_seconds() // 60),
    )
    assert checkout_data["last_session"]["duration_minutes"] == expected_duration
    assert expected_duration >= 94
    today_start, _ = day_bounds(business_today())
    expected_today = max(
        0,
        int(
            (
                record.checked_out_at - max(record.checked_in_at, today_start)
            ).total_seconds()
            // 60
        ),
    )
    assert checkout_data["worked_minutes_today"] == expected_today
    assert client.post("/attendance/check-out", headers=accounting_headers).status_code == 409

    overview_after = client.get("/attendance", headers=root_headers).json()
    assert overview_after["present_count"] == 0
    assert overview_after["completed_today"] == 1
    assert overview_after["worked_minutes_today"] == expected_today
    notifications = list(
        db_session.scalars(
            select(Notification)
            .where(Notification.entity_type == "attendance")
            .order_by(Notification.id)
        )
    )
    assert [item.kind for item in notifications] == [
        "attendance_check_in",
        "attendance_check_out",
    ]
    audits = list(
        db_session.scalars(
            select(AuditLog)
            .where(
                AuditLog.category == "attendance",
                AuditLog.entity_id == str(record_id),
            )
            .order_by(AuditLog.id)
        )
    )
    assert [item.action for item in audits] == ["check_in", "check_out"]
    assert audits[1].details["duration_minutes"] >= 95


def test_unlinked_or_inactive_staff_cannot_check_in(
    client: TestClient,
    db_session: Session,
    accounting_headers: dict[str, str],
    storage_headers: dict[str, str],
):
    unlinked = client.get("/attendance/me", headers=storage_headers)
    assert unlinked.status_code == 200
    assert unlinked.json() == {
        "eligible": False,
        "is_checked_in": False,
        "staff_member": None,
        "current_session": None,
        "last_session": None,
        "worked_minutes_today": 0,
        "checklist_required": False,
        "checklist_items": [],
        "entry_allowed": True,
        "entry_checklist_completed": True,
        "checkout_checklist_required": False,
        "checkout_checklist_items": [],
    }
    assert client.post("/attendance/check-in", headers=storage_headers).status_code == 409

    linked_staff(db_session, UserRole.ACCOUNTING_MANAGER, active=False)
    inactive = client.get("/attendance/me", headers=accounting_headers)
    assert inactive.status_code == 200
    assert inactive.json()["eligible"] is False
    assert client.post("/attendance/check-in", headers=accounting_headers).status_code == 409
