from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceRecord,
    MenuItem,
    Notification,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    PointSource,
    StaffMember,
    StaffPointEntry,
    User,
    UserRole,
)
from app.services.business_time import business_today


def linked_member(
    db: Session, role: UserRole = UserRole.ACCOUNTING_MANAGER
) -> StaffMember:
    user = db.scalar(select(User).where(User.role == role))
    assert user is not None
    member = StaffMember(
        name=user.full_name,
        position="همکار تست حقوق",
        user_id=user.id,
        is_active=True,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def test_pay_type_is_exclusive_and_only_root_can_manage_manual_points(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    member = linked_member(db_session)

    configured = client.patch(
        f"/payroll/staff/{member.id}/compensation",
        headers=root_headers,
        json={"pay_type": "profit_share", "pay_rate": 12.5, "point_value": 10000},
    )
    assert configured.status_code == 200, configured.text
    assert configured.json()["pay_type"] == "profit_share"
    assert Decimal(configured.json()["pay_rate"]) == Decimal("12.50")
    assert "salary" not in configured.json()
    assert "profit_share_percent" not in configured.json()

    invalid_share = client.patch(
        f"/payroll/staff/{member.id}/compensation",
        headers=root_headers,
        json={"pay_type": "profit_share", "pay_rate": 101, "point_value": 10000},
    )
    assert invalid_share.status_code == 422
    assert (
        client.patch(
            f"/payroll/staff/{member.id}/compensation",
            headers=accounting_headers,
            json={"pay_type": "salary", "pay_rate": 1, "point_value": 1},
        ).status_code
        == 403
    )

    for points, reason in (
        (10, "تحویل دقیق و مسئولانه شیفت"),
        (-3, "تأخیر در تحویل وظیفه"),
    ):
        response = client.post(
            "/payroll/points",
            headers=root_headers,
            json={"staff_member_id": member.id, "points": points, "reason": reason},
        )
        assert response.status_code == 201, response.text
        assert response.json()["points"] == points
        assert response.json()["source"] == "manual"

    assert (
        client.post(
            "/payroll/points",
            headers=accounting_headers,
            json={"staff_member_id": member.id, "points": 50, "reason": "غیرمجاز"},
        ).status_code
        == 403
    )
    assert client.get("/payroll/points", headers=accounting_headers).status_code == 403
    own = client.get("/payroll/me", headers=accounting_headers)
    assert own.status_code == 200
    assert own.json()["total_points"] == 7
    assert own.json()["positive_points"] == 10
    assert own.json()["negative_points"] == -3
    assert "pay_rate" not in own.json()

    notices = list(
        db_session.scalars(
            select(Notification).where(
                Notification.recipient_user_id == member.user_id,
                Notification.kind == "staff_points",
            )
        )
    )
    assert len(notices) == 2


def test_automatic_points_profit_share_calculation_and_immutable_statement(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    member = linked_member(db_session)
    user = db_session.scalar(
        select(User).where(User.role == UserRole.ACCOUNTING_MANAGER)
    )
    root = db_session.scalar(select(User).where(User.role == UserRole.ROOT))
    assert user is not None and root is not None

    entry_item = client.post(
        "/attendance/checklists",
        headers=root_headers,
        json={"user_id": user.id, "phase": "entry", "title": "آماده‌سازی صندوق"},
    ).json()
    exit_item = client.post(
        "/attendance/checklists",
        headers=root_headers,
        json={"user_id": user.id, "phase": "exit", "title": "تحویل صندوق"},
    ).json()

    checked_in = client.post(
        "/attendance/check-in", headers=accounting_headers, json={}
    )
    assert checked_in.status_code == 201
    record_id = checked_in.json()["current_session"]["id"]
    completed = client.post(
        "/attendance/check-in-checklist",
        headers=accounting_headers,
        json={"checklist_item_ids": [entry_item["id"]]},
    )
    assert completed.status_code == 200
    record = db_session.get(AttendanceRecord, record_id)
    assert record is not None
    record.checked_in_at -= timedelta(minutes=125)
    db_session.commit()
    checked_out = client.post(
        "/attendance/check-out",
        headers=accounting_headers,
        json={"checklist_item_ids": [exit_item["id"]]},
    )
    assert checked_out.status_code == 200, checked_out.text

    entries = list(
        db_session.scalars(
            select(StaffPointEntry)
            .where(StaffPointEntry.staff_member_id == member.id)
            .order_by(StaffPointEntry.id)
        )
    )
    assert [entry.source for entry in entries] == [
        PointSource.CHECK_IN,
        PointSource.ENTRY_CHECKLIST,
        PointSource.CHECK_OUT,
        PointSource.EXIT_CHECKLIST,
        PointSource.WORK_HOURS,
    ]
    assert [entry.points for entry in entries] == [1, 2, 1, 2, 2]

    menu = MenuItem(
        name="محصول تست سود",
        category="تست",
        selling_price=Decimal("100000"),
        is_active=True,
    )
    db_session.add(menu)
    db_session.flush()

    def add_order(
        number: str,
        *,
        total: str,
        cost: str,
        takeaway_cost: str = "0",
        status: OrderStatus = OrderStatus.COMPLETED,
        staff_meal: bool = False,
        deleted: bool = False,
    ) -> None:
        order = Order(
            order_number=number,
            status=status,
            customer_name="مهمان",
            staff_member_id=member.id if staff_meal else None,
            staff_name=member.name if staff_meal else None,
            is_staff_meal=staff_meal,
            takeaway_cost=Decimal(takeaway_cost),
            subtotal=Decimal(total),
            discount=Decimal("0"),
            total=Decimal(total),
            payment_method=PaymentMethod.CARD,
            created_by_id=root.id,
            is_deleted=deleted,
        )
        order.items.append(
            OrderItem(
                menu_item_id=menu.id,
                name=menu.name,
                quantity=1,
                unit_price=Decimal(total),
                line_total=Decimal(total),
                unit_cost=Decimal(cost),
                line_cost=Decimal(cost),
            )
        )
        db_session.add(order)

    add_order("PAY-VALID", total="100000", cost="40000", takeaway_cost="5000")
    add_order("PAY-STAFF", total="900000", cost="1", staff_meal=True)
    add_order("PAY-CANCELLED", total="800000", cost="1", status=OrderStatus.CANCELLED)
    add_order("PAY-DELETED", total="700000", cost="1", deleted=True)
    db_session.commit()

    contract = client.patch(
        f"/payroll/staff/{member.id}/compensation",
        headers=root_headers,
        json={"pay_type": "profit_share", "pay_rate": 10, "point_value": 1000},
    )
    assert contract.status_code == 200
    today = business_today().isoformat()
    calculations = client.get(
        f"/payroll/calculations?period_start={today}&period_end={today}",
        headers=root_headers,
    )
    assert calculations.status_code == 200, calculations.text
    calculation = next(
        item for item in calculations.json() if item["staff_member"]["id"] == member.id
    )
    assert Decimal(calculation["profit_basis"]) == Decimal("55000.00")
    assert Decimal(calculation["base_compensation"]) == Decimal("5500.00")
    assert calculation["points_total"] == 8
    assert Decimal(calculation["points_adjustment"]) == Decimal("8000.00")
    assert Decimal(calculation["payable_total"]) == Decimal("13500.00")
    assert calculation["worked_minutes"] >= 124
    assert calculation["entry_checklists_completed"] == 1
    assert calculation["exit_checklists_completed"] == 1
    assert (
        client.get("/payroll/calculations", headers=accounting_headers).status_code
        == 403
    )

    created = client.post(
        "/payroll/statements",
        headers=root_headers,
        json={"staff_member_id": member.id, "period_start": today, "period_end": today},
    )
    assert created.status_code == 201, created.text
    statement = created.json()
    assert statement["status"] == "draft"
    assert Decimal(statement["payable_total"]) == Decimal("13500.00")
    duplicate = client.post(
        "/payroll/statements",
        headers=root_headers,
        json={"staff_member_id": member.id, "period_start": today, "period_end": today},
    )
    assert duplicate.status_code == 409
    paid = client.post(
        f"/payroll/statements/{statement['id']}/pay", headers=root_headers
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"
    assert paid.json()["paid_at"] is not None
    assert (
        client.post(
            f"/payroll/statements/{statement['id']}/pay", headers=root_headers
        ).status_code
        == 409
    )
