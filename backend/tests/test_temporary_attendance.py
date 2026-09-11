from datetime import timedelta

from sqlalchemy import select

from app.models import AttendanceChecklistCompletion, AttendanceRecord, AuditLog, Notification, StaffPointEntry, User, UserRole
from app.services.business_time import business_today
from app.services.payroll import attendance_metrics


def test_temporary_visit_bypasses_checklists_without_points_or_payroll_hours(
    client, db_session, root_headers, accounting_headers,
):
    actor = db_session.scalar(select(User).where(User.role == UserRole.ACCOUNTING_MANAGER))
    for phase in ("entry", "exit"):
        assert client.post("/attendance/checklists", headers=root_headers, json={
            "user_id": actor.id, "phase": phase, "title": f"وظیفه {phase}",
        }).status_code == 201
    assert client.get("/orders", headers=accounting_headers).status_code == 403
    entered = client.post("/attendance/check-in", headers=accounting_headers, json={"is_temporary": True})
    assert entered.status_code == 201, entered.text
    data = entered.json()
    assert data["entry_allowed"] and not data["checkout_checklist_required"]
    assert data["current_session"]["is_temporary"]
    record_id = data["current_session"]["id"]
    record = db_session.get(AttendanceRecord, record_id)
    record.checked_in_at -= timedelta(hours=3)
    db_session.commit()
    assert client.get("/orders", headers=accounting_headers).status_code == 200
    assert client.get("/users", headers=accounting_headers).status_code == 403
    assert client.post("/attendance/check-in", headers=accounting_headers, json={}).status_code == 409
    assert client.post("/attendance/check-in-checklist", headers=accounting_headers, json={"checklist_item_ids": []}).status_code == 409
    exited = client.post("/attendance/check-out", headers=accounting_headers, json={})
    assert exited.status_code == 200, exited.text
    assert not exited.json()["entry_allowed"]
    assert not exited.json()["is_checked_in"]
    assert exited.json()["worked_minutes_today"] == 0
    assert exited.json()["last_session"]["is_temporary"]
    assert exited.json()["last_session"]["duration_minutes"] >= 180
    assert db_session.scalar(select(StaffPointEntry).where(StaffPointEntry.attendance_record_id == record_id)) is None
    assert db_session.scalar(select(AttendanceChecklistCompletion).where(AttendanceChecklistCompletion.attendance_record_id == record_id)) is None
    assert attendance_metrics(db_session, staff_member_id=record.staff_member_id, period_start=business_today() - timedelta(days=1), period_end=business_today()) == (0, 0, 0, 0)
    notices = list(db_session.scalars(select(Notification).where(Notification.entity_type == "attendance", Notification.entity_id == str(record_id))))
    assert len(notices) == 2 and all("موقت" in notice.title for notice in notices)
    audits = list(db_session.scalars(select(AuditLog).where(AuditLog.category == "attendance", AuditLog.entity_type == "attendance_record", AuditLog.entity_id == str(record_id))))
    assert len(audits) == 2 and all("موقت" in entry.summary for entry in audits)
    assert client.post("/attendance/check-out", headers=accounting_headers, json={}).status_code == 409
    regular = client.post("/attendance/check-in", headers=accounting_headers, json={})
    assert regular.status_code == 201 and not regular.json()["current_session"]["is_temporary"]
    assert not regular.json()["entry_allowed"]
    assert db_session.scalar(select(StaffPointEntry)) is not None
