from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Category,
    InventoryItem,
    MenuCategory,
    MenuItem,
    Order,
    StockMovement,
    TakeawaySupply,
)


def seed_catalog(
    db: Session,
    *,
    box_quantity: Decimal = Decimal("10"),
) -> tuple[MenuItem, InventoryItem, InventoryItem, InventoryItem]:
    inventory_category = Category(name="ملزومات بیرون‌بر", color="#f97316")
    menu_category = MenuCategory(name="منوی بیرون‌بر", color="#f97316")
    db.add_all([inventory_category, menu_category])
    db.flush()
    food = InventoryItem(
        sku="TAKEAWAY-FOOD",
        name="غذای تست",
        category_id=inventory_category.id,
        unit="عدد",
        current_quantity=Decimal("10"),
        average_cost=Decimal("20"),
        reorder_level=Decimal("0"),
    )
    box = InventoryItem(
        sku="TAKEAWAY-BOX",
        name="ظرف آلومینیومی",
        category_id=inventory_category.id,
        unit="عدد",
        current_quantity=box_quantity,
        average_cost=Decimal("5"),
        reorder_level=Decimal("0"),
    )
    toothpick = InventoryItem(
        sku="TAKEAWAY-TOOTHPICK",
        name="خلال دندان",
        category_id=inventory_category.id,
        unit="عدد",
        current_quantity=Decimal("100"),
        average_cost=Decimal("1"),
        reorder_level=Decimal("0"),
    )
    db.add_all([food, box, toothpick])
    db.flush()
    menu_item = MenuItem(
        name="محصول تست بیرون‌بر",
        category=menu_category.name,
        category_id=menu_category.id,
        selling_price=Decimal("100"),
        inventory_item_id=food.id,
        stock_quantity_per_sale=Decimal("1"),
        is_active=True,
    )
    db.add(menu_item)
    db.commit()
    return menu_item, food, box, toothpick


def add_takeaway_supplies(
    client: TestClient,
    headers: dict[str, str],
    *,
    box_id: int,
    toothpick_id: int,
) -> tuple[dict, dict]:
    box = client.post(
        "/takeaway-supplies",
        headers=headers,
        json={"inventory_item_id": box_id, "quantity_per_package": "1"},
    )
    toothpick = client.post(
        "/takeaway-supplies",
        headers=headers,
        json={"inventory_item_id": toothpick_id, "quantity_per_package": "2"},
    )
    assert box.status_code == 201, box.text
    assert toothpick.status_code == 201, toothpick.text
    return box.json(), toothpick.json()


def test_takeaway_supply_configuration_is_audited_and_role_limited(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
    kitchen_headers: dict[str, str],
    storage_headers: dict[str, str],
    sales_headers: dict[str, str],
):
    _, _, box, toothpick = seed_catalog(db_session)
    created, _ = add_takeaway_supplies(
        client,
        root_headers,
        box_id=box.id,
        toothpick_id=toothpick.id,
    )
    assert Decimal(created["calculated_cost"]) == Decimal("5.00")
    assert created["max_packages_available"] == 10

    duplicate = client.post(
        "/takeaway-supplies",
        headers=accounting_headers,
        json={"inventory_item_id": box.id, "quantity_per_package": "3"},
    )
    assert duplicate.status_code == 409

    updated = client.patch(
        f"/takeaway-supplies/{created['id']}",
        headers=accounting_headers,
        json={"quantity_per_package": "2"},
    )
    assert updated.status_code == 200, updated.text
    assert Decimal(updated.json()["quantity_per_package"]) == Decimal("2")
    assert updated.json()["max_packages_available"] == 5

    for headers in (kitchen_headers, storage_headers, sales_headers):
        assert client.get("/takeaway-supplies", headers=headers).status_code == 403

    deleted = client.delete(
        f"/takeaway-supplies/{created['id']}", headers=root_headers
    )
    assert deleted.status_code == 204, deleted.text
    remaining = client.get("/takeaway-supplies", headers=root_headers)
    assert remaining.status_code == 200
    assert [item["inventory_item_id"] for item in remaining.json()] == [
        toothpick.id
    ]
    actions = list(
        db_session.scalars(
            select(AuditLog.action).where(
                AuditLog.entity_type == "takeaway_supply",
                AuditLog.entity_id == str(created["id"]),
            ).order_by(AuditLog.id)
        )
    )
    assert actions == ["create", "update", "delete"]


def test_takeaway_order_deducts_edits_and_restores_packaging_stock(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
    kitchen_headers: dict[str, str],
):
    menu_item, food, box, toothpick = seed_catalog(db_session)
    add_takeaway_supplies(
        client,
        root_headers,
        box_id=box.id,
        toothpick_id=toothpick.id,
    )

    dine_in = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu_item.id, "quantity": 1}]},
    )
    assert dine_in.status_code == 201, dine_in.text
    assert dine_in.json()["order_type"] == "dine_in"
    assert dine_in.json()["takeaway_package_count"] == 0
    assert Decimal(dine_in.json()["takeaway_cost"]) == Decimal("0")
    for item, expected in (
        (food, "9"),
        (box, "10"),
        (toothpick, "100"),
    ):
        db_session.refresh(item)
        assert Decimal(item.current_quantity) == Decimal(expected)

    takeaway = client.post(
        "/orders",
        headers=accounting_headers,
        json={
            "order_type": "takeaway",
            "takeaway_package_count": 2,
            "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
    )
    assert takeaway.status_code == 201, takeaway.text
    order_id = takeaway.json()["id"]
    assert takeaway.json()["order_type"] == "takeaway"
    assert takeaway.json()["takeaway_package_count"] == 2
    assert Decimal(takeaway.json()["takeaway_cost"]) == Decimal("14")
    for item, expected in (
        (food, "8"),
        (box, "8"),
        (toothpick, "96"),
    ):
        db_session.refresh(item)
        assert Decimal(item.current_quantity) == Decimal(expected)

    packaging_movements = list(
        db_session.scalars(
            select(StockMovement)
            .where(
                StockMovement.reference_type == "order_takeaway",
                StockMovement.reference_id == order_id,
            )
            .order_by(StockMovement.item_id)
        )
    )
    assert {
        movement.item_id: Decimal(movement.quantity)
        for movement in packaging_movements
    } == {box.id: Decimal("-2"), toothpick.id: Decimal("-4")}

    kitchen_orders = client.get("/kitchen/orders", headers=kitchen_headers)
    assert kitchen_orders.status_code == 200
    kitchen_order = next(
        order for order in kitchen_orders.json() if order["id"] == order_id
    )
    assert kitchen_order["order_type"] == "takeaway"
    assert kitchen_order["takeaway_package_count"] == 2
    assert "takeaway_cost" not in kitchen_order

    report = client.get("/reports/overview?days=30", headers=root_headers)
    assert report.status_code == 200, report.text
    assert Decimal(report.json()["kpis"]["estimated_cogs"]) == Decimal("54")
    assert Decimal(report.json()["kpis"]["gross_profit"]) == Decimal("146")

    increased = client.patch(
        f"/orders/{order_id}",
        headers=accounting_headers,
        json={
            "order_type": "takeaway",
            "takeaway_package_count": 3,
            "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
    )
    assert increased.status_code == 200, increased.text
    assert Decimal(increased.json()["takeaway_cost"]) == Decimal("21")
    for item, expected in ((box, "7"), (toothpick, "94")):
        db_session.refresh(item)
        assert Decimal(item.current_quantity) == Decimal(expected)

    changed_to_dine_in = client.patch(
        f"/orders/{order_id}",
        headers=accounting_headers,
        json={
            "order_type": "dine_in",
            "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
    )
    assert changed_to_dine_in.status_code == 200, changed_to_dine_in.text
    assert changed_to_dine_in.json()["takeaway_package_count"] == 0
    assert Decimal(changed_to_dine_in.json()["takeaway_cost"]) == Decimal("0")
    for item, expected in ((food, "8"), (box, "10"), (toothpick, "100")):
        db_session.refresh(item)
        assert Decimal(item.current_quantity) == Decimal(expected)

    deleted = client.delete(f"/orders/{order_id}", headers=root_headers)
    assert deleted.status_code == 204, deleted.text
    db_session.refresh(food)
    db_session.refresh(box)
    db_session.refresh(toothpick)
    assert Decimal(food.current_quantity) == Decimal("9")
    assert Decimal(box.current_quantity) == Decimal("10")
    assert Decimal(toothpick.current_quantity) == Decimal("100")


def test_takeaway_order_defaults_to_one_package_and_fails_atomically_on_shortage(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    menu_item, food, box, toothpick = seed_catalog(
        db_session, box_quantity=Decimal("0")
    )
    add_takeaway_supplies(
        client,
        root_headers,
        box_id=box.id,
        toothpick_id=toothpick.id,
    )
    before_orders = db_session.scalar(select(func.count()).select_from(Order))
    rejected = client.post(
        "/orders",
        headers=accounting_headers,
        json={
            "order_type": "takeaway",
            "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
    )
    assert rejected.status_code == 409, rejected.text
    assert "ظرف آلومینیومی" in rejected.text
    assert db_session.scalar(select(func.count()).select_from(Order)) == before_orders
    db_session.refresh(food)
    db_session.refresh(box)
    db_session.refresh(toothpick)
    assert Decimal(food.current_quantity) == Decimal("10")
    assert Decimal(box.current_quantity) == Decimal("0")
    assert Decimal(toothpick.current_quantity) == Decimal("100")

    invalid_dine_in = client.post(
        "/orders",
        headers=accounting_headers,
        json={
            "order_type": "dine_in",
            "takeaway_package_count": 2,
            "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
    )
    assert invalid_dine_in.status_code == 422

    supply = db_session.scalar(
        select(TakeawaySupply).where(TakeawaySupply.inventory_item_id == box.id)
    )
    assert supply is not None
    box.current_quantity = Decimal("2")
    db_session.commit()
    accepted = client.post(
        "/orders",
        headers=accounting_headers,
        json={
            "order_type": "takeaway",
            "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["takeaway_package_count"] == 1
    assert Decimal(accepted.json()["takeaway_cost"]) == Decimal("7")

    cancelled = client.patch(
        f"/orders/{accepted.json()['id']}/status",
        headers=accounting_headers,
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200, cancelled.text
    for item, expected in ((food, "10"), (box, "2"), (toothpick, "100")):
        db_session.refresh(item)
        assert Decimal(item.current_quantity) == Decimal(expected)
