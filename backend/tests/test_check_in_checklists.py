from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceChecklistCompletion,
    AttendanceRecord,
    AuditLog,
    CheckInChecklistItem,
    StaffMember,
    User,
    UserRole,
)


def user_id(db: Session, role: UserRole) -> int:
    value = db.scalar(select(User.id).where(User.role == role))
    assert value is not None
    return value


def create_item(
    client: TestClient,
    headers: dict[str, str],
    *,
    target_user_id: int,
    title: str,
    description: str | None = None,
    phase: str = "entry",
) -> dict:
    response = client.post(
        "/attendance/checklists",
        headers=headers,
        json={
            "user_id": target_user_id,
            "title": title,
            "description": description,
            "phase": phase,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_root_manages_separate_checklists_for_each_user(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    storage_headers: dict[str, str],
):
    accounting_id = user_id(db_session, UserRole.ACCOUNTING_MANAGER)
    kitchen_id = user_id(db_session, UserRole.KITCHEN_MANAGER)
    first = create_item(
        client,
        root_headers,
        target_user_id=accounting_id,
        title="کنترل موجودی صندوق",
        description="وجه نقد و دستگاه کارت‌خوان بررسی شود",
    )
    second = create_item(
        client,
        root_headers,
        target_user_id=accounting_id,
        title="بررسی رول چاپگر",
    )
    kitchen = create_item(
        client,
        root_headers,
        target_user_id=kitchen_id,
        title="کنترل نظافت خط پخت",
    )
    checkout = create_item(
        client,
        root_headers,
        target_user_id=accounting_id,
        title="تحویل کامل صندوق",
        phase="exit",
    )

    accounting_items = client.get(
        f"/attendance/checklists?user_id={accounting_id}&phase=entry", headers=root_headers
    )
    assert accounting_items.status_code == 200
    assert [item["id"] for item in accounting_items.json()] == [
        first["id"],
        second["id"],
    ]
    kitchen_items = client.get(
        f"/attendance/checklists?user_id={kitchen_id}", headers=root_headers
    )
    assert [item["id"] for item in kitchen_items.json()] == [kitchen["id"]]
    checkout_items = client.get(
        f"/attendance/checklists?user_id={accounting_id}&phase=exit",
        headers=root_headers,
    )
    assert [item["id"] for item in checkout_items.json()] == [checkout["id"]]
    assert (
        client.get(
            f"/attendance/checklists?user_id={accounting_id}",
            headers=storage_headers,
        ).status_code
        == 403
    )

    updated = client.patch(
        f"/attendance/checklists/{first['id']}",
        headers=root_headers,
        json={"title": "کنترل کامل صندوق", "sort_order": 25},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "کنترل کامل صندوق"
    deleted = client.delete(
        f"/attendance/checklists/{second['id']}", headers=root_headers
    )
    assert deleted.status_code == 204
    active_items = client.get(
        f"/attendance/checklists?user_id={accounting_id}&phase=entry", headers=root_headers
    ).json()
    assert [item["id"] for item in active_items] == [first["id"]]
    all_items = client.get(
        f"/attendance/checklists?user_id={accounting_id}&phase=entry&include_inactive=true",
        headers=root_headers,
    ).json()
    assert {item["id"] for item in all_items} == {first["id"], second["id"]}

    linked_users = set(
        db_session.scalars(
            select(StaffMember.user_id).where(
                StaffMember.user_id.in_([accounting_id, kitchen_id])
            )
        )
    )
    assert linked_users == {accounting_id, kitchen_id}
    actions = list(
        db_session.scalars(
            select(AuditLog.action)
            .where(AuditLog.entity_type == "check_in_checklist_item")
            .order_by(AuditLog.id)
        )
    )
    assert actions == ["create", "create", "create", "create", "update", "delete"]


def test_checklist_blocks_system_until_every_item_is_completed_and_saves_history(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    accounting_id = user_id(db_session, UserRole.ACCOUNTING_MANAGER)
    first = create_item(
        client,
        root_headers,
        target_user_id=accounting_id,
        title="شمارش صندوق",
    )
    second = create_item(
        client,
        root_headers,
        target_user_id=accounting_id,
        title="روشن بودن چاپگر",
    )
    exit_item = create_item(
        client,
        root_headers,
        target_user_id=accounting_id,
        title="تحویل صندوق پایان شیفت",
        phase="exit",
    )

    assert client.get("/auth/me", headers=accounting_headers).status_code == 200
    status = client.get("/attendance/me", headers=accounting_headers)
    assert status.status_code == 200
    assert status.json()["checklist_required"] is True
    assert status.json()["entry_allowed"] is False
    assert [item["id"] for item in status.json()["checklist_items"]] == [
        first["id"],
        second["id"],
    ]
    assert status.json()["checkout_checklist_required"] is False
    assert [item["id"] for item in status.json()["checkout_checklist_items"]] == [
        exit_item["id"]
    ]

    blocked = client.get("/dashboard", headers=accounting_headers)
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "CHECK_IN_REQUIRED"
    checked_in = client.post("/attendance/check-in", headers=accounting_headers, json={})
    assert checked_in.status_code == 201, checked_in.text
    assert checked_in.json()["is_checked_in"] is True
    assert checked_in.json()["entry_allowed"] is False
    assert checked_in.json()["entry_checklist_completed"] is False
    assert checked_in.json()["checkout_checklist_required"] is True
    assert checked_in.json()["current_session"]["checklist_completions"] == []
    still_blocked = client.get("/dashboard", headers=accounting_headers)
    assert still_blocked.status_code == 403
    assert still_blocked.json()["detail"]["code"] == "ENTRY_CHECKLIST_REQUIRED"

    incomplete = client.post(
        "/attendance/check-in-checklist",
        headers=accounting_headers,
        json={"checklist_item_ids": [first["id"]]},
    )
    assert incomplete.status_code == 409
    assert incomplete.json()["detail"]["code"] == "CHECKLIST_INCOMPLETE"
    assert incomplete.json()["detail"]["missing_items"] == [second["title"]]
    assert db_session.scalar(select(func.count()).select_from(AttendanceRecord)) == 1

    completed = client.post(
        "/attendance/check-in-checklist",
        headers=accounting_headers,
        json={"checklist_item_ids": [first["id"], second["id"]]},
    )
    assert completed.status_code == 200, completed.text
    current = completed.json()["current_session"]
    assert completed.json()["entry_allowed"] is True
    assert completed.json()["entry_checklist_completed"] is True
    assert [
        completion["title_snapshot"]
        for completion in current["checklist_completions"]
    ] == [first["title"], second["title"]]
    assert client.get("/dashboard", headers=accounting_headers).status_code == 200
    assert (
        db_session.scalar(
            select(func.count()).select_from(AttendanceChecklistCompletion)
        )
        == 2
    )

    client.patch(
        f"/attendance/checklists/{first['id']}",
        headers=root_headers,
        json={"title": "شمارش و ثبت صندوق"},
    )
    client.delete(
        f"/attendance/checklists/{second['id']}", headers=root_headers
    )
    overview = client.get("/attendance", headers=root_headers)
    assert overview.status_code == 200
    saved = overview.json()["items"][0]["checklist_completions"]
    assert [item["title_snapshot"] for item in saved] == [
        "شمارش صندوق",
        "روشن بودن چاپگر",
    ]

    checkout_blocked = client.post(
        "/attendance/check-out", headers=accounting_headers, json={}
    )
    assert checkout_blocked.status_code == 409
    assert checkout_blocked.json()["detail"]["code"] == "CHECKOUT_CHECKLIST_INCOMPLETE"
    checked_out = client.post(
        "/attendance/check-out",
        headers=accounting_headers,
        json={"checklist_item_ids": [exit_item["id"]]},
    )
    assert checked_out.status_code == 200
    assert checked_out.json()["entry_allowed"] is False
    assert client.get("/dashboard", headers=accounting_headers).status_code == 403
    next_status = client.get("/attendance/me", headers=accounting_headers).json()
    assert [item["title"] for item in next_status["checklist_items"]] == [
        "شمارش و ثبت صندوق"
    ]
    overview_after = client.get("/attendance", headers=root_headers).json()
    saved_completions = overview_after["items"][0]["checklist_completions"]
    assert [item["phase"] for item in saved_completions] == ["entry", "entry", "exit"]

    database_item = db_session.get(CheckInChecklistItem, second["id"])
    assert database_item is not None
    assert database_item.is_active is False
