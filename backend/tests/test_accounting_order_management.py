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
    StockMovement,
)


def seed_direct_menu(db: Session) -> tuple[InventoryItem, MenuItem]:
    category = Category(name="مواد تست مدیریت سفارش", color="#2563eb")
    menu_category = MenuCategory(name="منوی تست مدیریت سفارش", color="#2563eb")
    db.add_all([category, menu_category])
    db.flush()
    inventory = InventoryItem(
        sku="ORDER-MANAGEMENT-STOCK",
        name="موجودی تست مدیریت سفارش",
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
        name="محصول تست مدیریت سفارش",
        category=menu_category.name,
        category_id=menu_category.id,
        selling_price=Decimal("100"),
        inventory_item_id=inventory.id,
        stock_quantity_per_sale=Decimal("1"),
        is_active=True,
    )
    db.add(menu)
    db.commit()
    return inventory, menu


def test_accounting_can_register_inventory_intake(
    client: TestClient,
    accounting_headers: dict[str, str],
):
    categories = client.get("/inventory/categories", headers=accounting_headers)
    assert categories.status_code == 200, categories.text

    created_item = client.post(
        "/inventory/items",
        headers=accounting_headers,
        json={
            "sku": "ACCOUNTING-INTAKE-001",
            "name": "کالای ورودی حسابداری",
            "unit": "عدد",
            "reorder_level": 0,
            "target_stock_level": 0,
            "purchase_quantity": 1,
            "purchase_unit": "عدد",
            "purchase_price": 0,
            "selling_quantity": 1,
            "selling_unit": "عدد",
            "selling_price": 0,
        },
    )
    assert created_item.status_code == 201, created_item.text

    receipt = client.post(
        "/purchases",
        headers=accounting_headers,
        json={
            "purchased_at": "2026-08-29T12:00:00",
            "supplier_name": "تأمین‌کننده تست",
            "lines": [
                {
                    "inventory_item_id": created_item.json()["id"],
                    "quantity": 4,
                    "purchase_unit": "عدد",
                    "conversion_factor": 1,
                    "line_total": 400,
                }
            ],
        },
    )
    assert receipt.status_code == 201, receipt.text
    assert Decimal(receipt.json()["total_cost"]) == Decimal("400.00")
    history = client.get("/purchases", headers=accounting_headers)
    assert history.status_code == 200, history.text
    assert history.json()["total"] == 1


def test_order_edit_can_convert_guest_to_new_or_existing_customer(
    client: TestClient,
    db_session: Session,
    accounting_headers: dict[str, str],
):
    _, menu = seed_direct_menu(db_session)
    created = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu.id, "quantity": 1}]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["customer_id"] is None

    assigned = client.patch(
        f"/orders/{created.json()['id']}",
        headers=accounting_headers,
        json={
            "customer": {"name": "مشتری تازه", "phone": "۰۹۱۲۰۰۰۰۰۰۱"},
            "items": [{"menu_item_id": menu.id, "quantity": 1}],
        },
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["customer_name"] == "مشتری تازه"
    assert assigned.json()["customer_id"] is not None

    customer_id = assigned.json()["customer_id"]
    customers = client.get(
        "/customers?search=09120000001", headers=accounting_headers
    )
    assert customers.status_code == 200, customers.text
    assert len(customers.json()) == 1
    assert customers.json()[0]["id"] == customer_id
    assert customers.json()[0]["name"] == "مشتری تازه"
    assert customers.json()[0]["phone"] == "09120000001"

    guest_again = client.patch(
        f"/orders/{created.json()['id']}",
        headers=accounting_headers,
        json={
            "customer_id": None,
            "items": [{"menu_item_id": menu.id, "quantity": 1}],
        },
    )
    assert guest_again.status_code == 200, guest_again.text
    assert guest_again.json()["customer_id"] is None
    assert guest_again.json()["customer_name"] == "Guest"

    existing_again = client.patch(
        f"/orders/{created.json()['id']}",
        headers=accounting_headers,
        json={
            "customer_id": customer_id,
            "items": [{"menu_item_id": menu.id, "quantity": 1}],
        },
    )
    assert existing_again.status_code == 200, existing_again.text
    assert existing_again.json()["customer_id"] == customer_id
    assert existing_again.json()["customer_name"] == "مشتری تازه"


def test_root_and_accounting_can_soft_delete_orders_and_restore_stock_once(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
    kitchen_headers: dict[str, str],
    storage_headers: dict[str, str],
    sales_headers: dict[str, str],
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

    for headers in (kitchen_headers, storage_headers, sales_headers):
        forbidden = client.delete(f"/orders/{order_id}", headers=headers)
        assert forbidden.status_code == 403
    deleted = client.delete(f"/orders/{order_id}", headers=accounting_headers)
    assert deleted.status_code == 204, deleted.text
    db_session.refresh(inventory)
    assert Decimal(inventory.current_quantity) == Decimal("10.000")

    assert client.get(f"/orders/{order_id}", headers=root_headers).status_code == 404
    assert (
        client.get(f"/orders/{order_id}/receipt", headers=root_headers).status_code
        == 404
    )
    assert all(
        order["id"] != order_id
        for order in client.get("/orders", headers=root_headers).json()
    )
    assert all(
        order["id"] != order_id
        for order in client.get("/kitchen/orders", headers=kitchen_headers).json()
    )
    assert client.get("/dashboard", headers=root_headers).json()["orders_today"] == 0
    assert (
        client.get("/reports/overview?days=30", headers=root_headers)
        .json()["kpis"]["orders"]
        == 0
    )

    movements = list(
        db_session.scalars(
            select(StockMovement).where(
                StockMovement.reference_type == "order_delete",
                StockMovement.reference_id == order_id,
            )
        )
    )
    assert len(movements) == 1
    assert movements[0].movement_type == MovementType.ADJUST
    assert Decimal(movements[0].quantity) == Decimal("2.000")
    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_type == "order",
            AuditLog.entity_id == str(order_id),
            AuditLog.action == "delete",
        )
    )
    assert audit is not None
    assert audit.details["recoverable_soft_delete"] is True

    assert client.delete(f"/orders/{order_id}", headers=root_headers).status_code == 404
    db_session.refresh(inventory)
    assert Decimal(inventory.current_quantity) == Decimal("10.000")


def test_deleting_already_cancelled_order_does_not_restore_stock_twice(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    inventory, menu = seed_direct_menu(db_session)
    created = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu.id, "quantity": 3}]},
    )
    order_id = created.json()["id"]
    cancelled = client.patch(
        f"/orders/{order_id}/status",
        headers=accounting_headers,
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200, cancelled.text
    db_session.refresh(inventory)
    assert Decimal(inventory.current_quantity) == Decimal("10.000")

    deleted = client.delete(f"/orders/{order_id}", headers=root_headers)
    assert deleted.status_code == 204, deleted.text
    db_session.refresh(inventory)
    assert Decimal(inventory.current_quantity) == Decimal("10.000")
    delete_movements = list(
        db_session.scalars(
            select(StockMovement).where(
                StockMovement.reference_type == "order_delete",
                StockMovement.reference_id == order_id,
            )
        )
    )
    assert delete_movements == []
