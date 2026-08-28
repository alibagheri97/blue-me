from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Category,
    InventoryItem,
    MenuCategory,
    MenuItem,
    MovementType,
    OrderStatus,
    StockMovement,
)


def seed_direct_menu(db: Session) -> tuple[InventoryItem, MenuItem]:
    category = Category(name="مواد تست ویرایش", color="#2563eb")
    menu_category = MenuCategory(name="منوی تست ویرایش", color="#2563eb")
    db.add_all([category, menu_category])
    db.flush()
    inventory = InventoryItem(
        sku="ORDER-EDIT-STOCK",
        name="موجودی تست سفارش",
        category_id=category.id,
        unit="عدد",
        current_quantity=Decimal("10"),
        average_cost=Decimal("20"),
        last_purchase_price=Decimal("20"),
        reorder_level=Decimal("1"),
    )
    db.add(inventory)
    db.flush()
    menu = MenuItem(
        name="محصول تست ویرایش",
        category="منوی تست ویرایش",
        category_id=menu_category.id,
        selling_price=Decimal("100"),
        inventory_item_id=inventory.id,
        stock_quantity_per_sale=Decimal("1"),
        is_active=True,
    )
    db.add(menu)
    db.commit()
    return inventory, menu


def test_root_can_disable_kitchen_workflow_and_orders_complete_immediately(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    inventory, menu = seed_direct_menu(db_session)
    initial = client.get("/settings", headers=accounting_headers)
    assert initial.status_code == 200
    assert initial.json()["kitchen_workflow_enabled"] is True
    forbidden = client.patch(
        "/settings",
        headers=accounting_headers,
        json={"kitchen_workflow_enabled": False},
    )
    assert forbidden.status_code == 403

    queued = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu.id, "quantity": 1}]},
    )
    assert queued.status_code == 201, queued.text
    assert queued.json()["status"] == OrderStatus.CONFIRMED.value

    disabled = client.patch(
        "/settings",
        headers=root_headers,
        json={"kitchen_workflow_enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["kitchen_workflow_enabled"] is False
    assert client.get(
        f"/orders/{queued.json()['id']}", headers=accounting_headers
    ).json()["status"] == OrderStatus.COMPLETED.value

    direct = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu.id, "quantity": 2}]},
    )
    assert direct.status_code == 201, direct.text
    assert direct.json()["status"] == OrderStatus.COMPLETED.value
    db_session.refresh(inventory)
    assert Decimal(inventory.current_quantity) == Decimal("7.000")
    dashboard = client.get("/dashboard", headers=root_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["kitchen_workflow_enabled"] is False
    assert dashboard.json()["orders_in_kitchen"] == 0

    settings_audit = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.entity_type == "system_settings")
        .order_by(AuditLog.id.desc())
    )
    assert settings_audit is not None
    assert settings_audit.details["active_orders_completed"] == 1


def test_accounting_can_edit_order_with_reversible_inventory_deltas(
    client: TestClient,
    db_session: Session,
    accounting_headers: dict[str, str],
    kitchen_headers: dict[str, str],
):
    inventory, menu = seed_direct_menu(db_session)
    created = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu.id, "quantity": 2}]},
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    db_session.refresh(inventory)
    assert Decimal(inventory.current_quantity) == Decimal("8.000")

    forbidden = client.patch(
        f"/orders/{order_id}",
        headers=kitchen_headers,
        json={"items": [{"menu_item_id": menu.id, "quantity": 3}]},
    )
    assert forbidden.status_code == 403

    expanded = client.patch(
        f"/orders/{order_id}",
        headers=accounting_headers,
        json={
            "items": [
                {
                    "menu_item_id": menu.id,
                    "quantity": 4,
                    "notes": "بدون سس",
                }
            ],
            "discount": 10,
            "payment_method": "cash",
            "notes": "ویرایش صندوق",
        },
    )
    assert expanded.status_code == 200, expanded.text
    expanded_order = expanded.json()
    assert expanded_order["items"][0]["quantity"] == 4
    assert expanded_order["items"][0]["notes"] == "بدون سس"
    assert Decimal(expanded_order["subtotal"]) == Decimal("400.00")
    assert Decimal(expanded_order["discount"]) == Decimal("10.00")
    assert Decimal(expanded_order["total"]) == Decimal("390.00")
    assert expanded_order["payment_method"] == "cash"
    assert expanded_order["status"] == "confirmed"
    db_session.refresh(inventory)
    assert Decimal(inventory.current_quantity) == Decimal("6.000")

    shortage = client.patch(
        f"/orders/{order_id}",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu.id, "quantity": 20}]},
    )
    assert shortage.status_code == 409
    db_session.refresh(inventory)
    assert Decimal(inventory.current_quantity) == Decimal("6.000")

    reduced = client.patch(
        f"/orders/{order_id}",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu.id, "quantity": 1}]},
    )
    assert reduced.status_code == 200, reduced.text
    db_session.refresh(inventory)
    assert Decimal(inventory.current_quantity) == Decimal("9.000")
    edit_movements = list(
        db_session.scalars(
            select(StockMovement)
            .where(
                StockMovement.reference_type == "order_edit",
                StockMovement.reference_id == order_id,
            )
            .order_by(StockMovement.id)
        )
    )
    assert [movement.movement_type for movement in edit_movements] == [
        MovementType.ADJUST,
        MovementType.ADJUST,
    ]
    assert [Decimal(movement.quantity) for movement in edit_movements] == [
        Decimal("-2.000"),
        Decimal("3.000"),
    ]

    cancelled = client.patch(
        f"/orders/{order_id}/status",
        headers=accounting_headers,
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200, cancelled.text
    db_session.refresh(inventory)
    assert Decimal(inventory.current_quantity) == Decimal("10.000")
    rejected_edit = client.patch(
        f"/orders/{order_id}",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu.id, "quantity": 2}]},
    )
    assert rejected_edit.status_code == 409
    update_audits = list(
        db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "order",
                AuditLog.entity_id == str(order_id),
                AuditLog.action == "update",
            )
        )
    )
    assert len(update_audits) == 2
    assert update_audits[0].details["inventory_consumption_delta"][str(inventory.id)] == "2.000"


def test_staff_order_edit_keeps_internal_accounting_rules(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    inventory, menu = seed_direct_menu(db_session)
    users = client.get("/users", headers=root_headers).json()
    accounting_user = next(
        user for user in users if user["role"] == "accounting_manager"
    )
    staff = client.post(
        "/staff",
        headers=root_headers,
        json={"name": "پرسنل تست", "user_id": accounting_user["id"]},
    )
    assert staff.status_code == 201, staff.text
    created = client.post(
        "/orders",
        headers=accounting_headers,
        json={
            "staff_member_id": staff.json()["id"],
            "items": [{"menu_item_id": menu.id, "quantity": 1}],
        },
    )
    assert created.status_code == 201, created.text
    edited = client.patch(
        f"/orders/{created.json()['id']}",
        headers=accounting_headers,
        json={
            "discount": 0,
            "payment_method": "cash",
            "items": [{"menu_item_id": menu.id, "quantity": 3}],
        },
    )
    assert edited.status_code == 200, edited.text
    assert Decimal(edited.json()["subtotal"]) == Decimal("300.00")
    assert Decimal(edited.json()["discount"]) == Decimal("300.00")
    assert Decimal(edited.json()["total"]) == Decimal("0.00")
    assert edited.json()["payment_method"] == "other"
    db_session.refresh(inventory)
    assert Decimal(inventory.current_quantity) == Decimal("7.000")
