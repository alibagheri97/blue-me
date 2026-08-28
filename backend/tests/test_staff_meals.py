from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, MovementType, StockMovement


def create_direct_staff_meal_product(
    client: TestClient,
    *,
    storage_headers: dict[str, str],
    accounting_headers: dict[str, str],
) -> tuple[int, int]:
    category = client.post(
        "/inventory/categories",
        headers=storage_headers,
        json={"name": "مواد غذای پرسنلی", "color": "#7c3aed"},
    )
    assert category.status_code == 201, category.text
    inventory = client.post(
        "/inventory/items",
        headers=storage_headers,
        json={
            "sku": "STAFF-MIX-TEST",
            "name": "پرس شاورما میکس تست",
            "category_id": category.json()["id"],
            "unit": "پرس",
            "reorder_level": 2,
            "selling_price": 0,
        },
    )
    assert inventory.status_code == 201, inventory.text
    item_id = inventory.json()["id"]
    receive = client.post(
        f"/inventory/items/{item_id}/movements",
        headers=storage_headers,
        json={
            "movement_type": "receive",
            "quantity": 20,
            "unit_cost": 40_000,
            "reason": "موجودی تست غذای پرسنلی",
        },
    )
    assert receive.status_code == 201, receive.text
    menu_category = client.post(
        "/menu-categories",
        headers=accounting_headers,
        json={"name": "شاورما تست", "color": "#2563eb", "sort_order": 1},
    )
    assert menu_category.status_code == 201, menu_category.text
    menu = client.post(
        "/menu-items",
        headers=accounting_headers,
        json={
            "name": "شاورما میکس",
            "category_id": menu_category.json()["id"],
            "category": "شاورما تست",
            "selling_price": 450_000,
            "inventory_item_id": item_id,
            "stock_quantity_per_sale": 1,
            "is_active": True,
        },
    )
    assert menu.status_code == 201, menu.text
    return item_id, menu.json()["id"]


def create_accounting_staff(
    client: TestClient,
    *,
    root_headers: dict[str, str],
) -> dict:
    users = client.get("/users", headers=root_headers)
    assert users.status_code == 200, users.text
    accounting = next(
        user for user in users.json() if user["role"] == "accounting_manager"
    )
    staff = client.post(
        "/staff",
        headers=root_headers,
        json={
            "name": accounting["full_name"],
            "position": "مدیر حسابداری",
            "user_id": accounting["id"],
            "notes": "حساب غذای پرسنلی",
        },
    )
    assert staff.status_code == 201, staff.text
    return staff.json()


def test_staff_meal_deducts_stock_but_is_excluded_from_sales_and_profit(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    storage_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    item_id, menu_id = create_direct_staff_meal_product(
        client,
        storage_headers=storage_headers,
        accounting_headers=accounting_headers,
    )
    staff = create_accounting_staff(client, root_headers=root_headers)

    selectable = client.get("/staff?active=true", headers=accounting_headers)
    assert selectable.status_code == 200, selectable.text
    own_account = next(item for item in selectable.json() if item["id"] == staff["id"])
    assert own_account["is_current_user"] is True

    normal_order = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu_id, "quantity": 1}]},
    )
    assert normal_order.status_code == 201, normal_order.text
    staff_order = client.post(
        "/orders",
        headers=accounting_headers,
        json={
            "staff_member_id": staff["id"],
            "payment_method": "cash",
            "discount": 12_000,
            "items": [{"menu_item_id": menu_id, "quantity": 1}],
        },
    )
    assert staff_order.status_code == 201, staff_order.text
    order = staff_order.json()
    assert order["is_staff_meal"] is True
    assert order["staff_member_id"] == staff["id"]
    assert order["staff_name"] == staff["name"]
    assert order["customer_id"] is None
    assert Decimal(order["subtotal"]) == Decimal("450000.00")
    assert Decimal(order["discount"]) == Decimal("450000.00")
    assert Decimal(order["total"]) == Decimal("0.00")
    assert order["payment_method"] == "other"

    inventory = client.get(f"/inventory/items/{item_id}", headers=storage_headers)
    assert inventory.status_code == 200
    assert inventory.json()["current_quantity"] == "18.000"
    movement = db_session.scalar(
        select(StockMovement)
        .where(
            StockMovement.reference_type == "order",
            StockMovement.reference_id == order["id"],
        )
        .order_by(StockMovement.id.desc())
    )
    assert movement is not None
    assert movement.movement_type == MovementType.CONSUME

    dashboard = client.get("/dashboard", headers=root_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["orders_today"] == 1
    assert Decimal(dashboard.json()["sales_today"]) == Decimal("450000.00")

    report = client.get("/reports/overview?days=30", headers=root_headers)
    assert report.status_code == 200, report.text
    report_data = report.json()
    assert report_data["kpis"]["orders"] == 1
    assert Decimal(report_data["kpis"]["revenue"]) == Decimal("450000.00")
    assert Decimal(report_data["kpis"]["estimated_cogs"]) == Decimal("40000.00")
    product = next(
        item for item in report_data["product_performance"] if item["id"] == menu_id
    )
    assert product["quantity"] == 1

    staff_accounts = client.get("/staff", headers=root_headers)
    account = next(item for item in staff_accounts.json() if item["id"] == staff["id"])
    assert account["meal_count"] == 1
    assert Decimal(account["menu_value"]) == Decimal("450000.00")
    assert Decimal(account["estimated_cost"]) == Decimal("40000.00")
    assert account["last_meal_at"] is not None

    history = client.get(f"/staff/{staff['id']}/orders", headers=accounting_headers)
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [order["id"]]
    receipt = client.get(f"/orders/{order['id']}/receipt", headers=accounting_headers)
    assert receipt.status_code == 200
    assert receipt.json()["customer_copy"]["show_prices"] is False
    assert receipt.json()["customer_copy"]["title"] == "برگه غذای پرسنلی"

    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_type == "order", AuditLog.entity_id == str(order["id"])
        )
    )
    assert audit is not None
    assert audit.details["is_staff_meal"] is True
    assert audit.details["excluded_from_sales_reports"] is True
    assert audit.details["gross_profit"] is None

    mixed_target = client.post(
        "/orders",
        headers=accounting_headers,
        json={
            "staff_member_id": staff["id"],
            "customer": {"name": "مشتری تست", "phone": "09120000000"},
            "items": [{"menu_item_id": menu_id, "quantity": 1}],
        },
    )
    assert mixed_target.status_code == 422
    forbidden_create = client.post(
        "/staff",
        headers=accounting_headers,
        json={"name": "پرسنل بدون مجوز"},
    )
    assert forbidden_create.status_code == 403


def test_cancelling_staff_meal_restores_consumed_stock(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    storage_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    item_id, menu_id = create_direct_staff_meal_product(
        client,
        storage_headers=storage_headers,
        accounting_headers=accounting_headers,
    )
    staff = create_accounting_staff(client, root_headers=root_headers)
    order = client.post(
        "/orders",
        headers=accounting_headers,
        json={
            "staff_member_id": staff["id"],
            "items": [{"menu_item_id": menu_id, "quantity": 2}],
        },
    )
    assert order.status_code == 201, order.text
    cancelled = client.patch(
        f"/orders/{order.json()['id']}/status",
        headers=accounting_headers,
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200, cancelled.text
    inventory = client.get(f"/inventory/items/{item_id}", headers=storage_headers)
    assert inventory.json()["current_quantity"] == "20.000"
    movements = list(
        db_session.scalars(
            select(StockMovement)
            .where(StockMovement.item_id == item_id)
            .order_by(StockMovement.id)
        )
    )
    assert [movement.movement_type for movement in movements][-2:] == [
        MovementType.CONSUME,
        MovementType.ADJUST,
    ]
    account = next(
        item
        for item in client.get("/staff", headers=root_headers).json()
        if item["id"] == staff["id"]
    )
    assert account["meal_count"] == 0


def test_new_system_user_gets_a_linked_staff_account(
    client: TestClient,
    root_headers: dict[str, str],
):
    created = client.post(
        "/users",
        headers=root_headers,
        json={
            "username": "new.sales.staff",
            "full_name": "پرسنل فروش جدید",
            "password": "strong-password-123",
            "role": "sales_manager",
        },
    )
    assert created.status_code == 201, created.text
    staff = client.get("/staff?search=پرسنل فروش جدید", headers=root_headers)
    assert staff.status_code == 200
    assert len(staff.json()) == 1
    assert staff.json()[0]["user_id"] == created.json()["id"]
    assert staff.json()[0]["position"] == "مدیر فروش"

    standalone = client.post(
        "/staff",
        headers=root_headers,
        json={"name": "پرسنل تلفن فارسی", "phone": "۰۹۱۲ ۱۲۳ ۴۵۶۷"},
    )
    assert standalone.status_code == 201, standalone.text
    assert standalone.json()["phone"] == "0912 123 4567"
    duplicate = client.post(
        "/staff",
        headers=root_headers,
        json={"name": "شماره تکراری", "phone": "0912 123 4567"},
    )
    assert duplicate.status_code == 409
