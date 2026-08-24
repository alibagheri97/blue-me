from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_public_health_and_authentication(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}
    config = client.get("/public/config")
    assert config.status_code == 200
    assert config.json()["app_name"] == "Blue Me"
    failed = client.post("/auth/login", json={"username": "root", "password": "wrong"})
    assert failed.status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_root_user_management_and_role_boundary(
    client: TestClient, root_headers: dict[str, str], storage_headers: dict[str, str]
):
    created = client.post(
        "/users",
        headers=root_headers,
        json={
            "username": "sales.new",
            "full_name": "Sales New",
            "password": "strong-password-123",
            "role": "sales_manager",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "sales_manager"
    assert client.get("/users", headers=storage_headers).status_code == 403
    disabled = client.patch(
        f"/users/{created.json()['id']}", headers=root_headers, json={"is_active": False}
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False


def test_inventory_price_recipe_order_and_reporting_flow(
    client: TestClient,
    db_session: Session,
    root_headers: dict[str, str],
    storage_headers: dict[str, str],
    accounting_headers: dict[str, str],
    kitchen_headers: dict[str, str],
):
    category = client.post(
        "/inventory/categories",
        headers=storage_headers,
        json={"name": "Protein", "description": "Recipe proteins", "color": "#ef4444"},
    )
    assert category.status_code == 201, category.text

    item = client.post(
        "/inventory/items",
        headers=storage_headers,
        json={
            "sku": "CHK-001",
            "name": "Chicken breast",
            "category_id": category.json()["id"],
            "unit": "gram",
            "reorder_level": "1000",
            "selling_price": "12.50",
        },
    )
    assert item.status_code == 201, item.text
    item_id = item.json()["id"]
    assert Decimal(item.json()["selling_price"]) == Decimal("0.00")

    received = client.post(
        f"/inventory/items/{item_id}/movements",
        headers=storage_headers,
        json={
            "movement_type": "receive",
            "quantity": "10000",
            "unit_cost": "0.02",
            "reason": "Opening stock invoice",
        },
    )
    assert received.status_code == 201, received.text
    assert received.json()["quantity_after"] == "10000.000"

    requests = client.get("/inventory/price-requests", headers=root_headers)
    assert requests.status_code == 200
    assert len(requests.json()) == 1
    approved = client.post(
        f"/inventory/price-requests/{requests.json()[0]['id']}/decision",
        headers=root_headers,
        json={"status": "approved", "note": "Approved for launch"},
    )
    assert approved.status_code == 200, approved.text
    updated_item = client.get(f"/inventory/items/{item_id}", headers=storage_headers)
    assert Decimal(updated_item.json()["selling_price"]) == Decimal("12.50")

    menu = client.post(
        "/menu-items",
        headers=root_headers,
        json={
            "name": "Chicken sandwich",
            "category": "Sandwiches",
            "selling_price": "8.00",
            "description": "Fresh chicken sandwich",
        },
    )
    assert menu.status_code == 201, menu.text
    menu_id = menu.json()["id"]

    recipe = client.post(
        "/kitchen/recipes",
        headers=kitchen_headers,
        json={
            "menu_item_id": menu_id,
            "yield_quantity": "1",
            "preparation_minutes": 8,
            "instructions": "Cook safely and assemble.",
            "ingredients": [
                {"inventory_item_id": item_id, "quantity": "150", "unit": "gram"}
            ],
        },
    )
    assert recipe.status_code == 201, recipe.text
    assert recipe.json()["calculated_cost"] == "3.00"

    need = client.post(
        "/kitchen/daily-needs",
        headers=kitchen_headers,
        json={
            "required_date": (date.today() + timedelta(days=1)).isoformat(),
            "inventory_item_id": item_id,
            "item_name": "Chicken breast",
            "quantity": "5000",
            "unit": "gram",
            "priority": "high",
            "notes": "Morning delivery",
        },
    )
    assert need.status_code == 201, need.text
    decision = client.post(
        f"/kitchen/daily-needs/{need.json()['id']}/decision",
        headers=root_headers,
        json={"status": "approved"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"

    order = client.post(
        "/orders",
        headers=accounting_headers,
        json={
            "customer": {"name": "Ava Customer", "phone": "+1 555 0100"},
            "payment_method": "card",
            "discount": "1.00",
            "items": [{"menu_item_id": menu_id, "quantity": 2, "notes": "No sauce"}],
        },
    )
    assert order.status_code == 201, order.text
    order_data = order.json()
    assert order_data["customer_name"] == "Ava Customer"
    assert order_data["subtotal"] == "16.00"
    assert order_data["total"] == "15.00"

    after_order = client.get(f"/inventory/items/{item_id}", headers=storage_headers)
    assert after_order.json()["current_quantity"] == "9700.000"
    assert client.get(f"/orders/{order_data['id']}/receipt", headers=accounting_headers).status_code == 200

    assert client.patch(
        f"/orders/{order_data['id']}/status",
        headers=kitchen_headers,
        json={"status": "preparing"},
    ).status_code == 200
    assert client.patch(
        f"/orders/{order_data['id']}/status",
        headers=kitchen_headers,
        json={"status": "ready"},
    ).status_code == 200
    assert client.patch(
        f"/orders/{order_data['id']}/status",
        headers=accounting_headers,
        json={"status": "completed"},
    ).status_code == 200

    dashboard = client.get("/dashboard", headers=root_headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["orders_today"] == 1
    assert dashboard.json()["sales_today"] == "15.00"

    report = client.get("/reports/overview?days=30", headers=root_headers)
    assert report.status_code == 200, report.text
    assert report.json()["kpis"]["revenue"] == "15.00"
    assert report.json()["product_performance"][0]["name"] == "Chicken sandwich"
    assert report.json()["product_performance"][0]["gross_profit"] == "9.00"

    audit = client.get("/audit-logs?category=orders", headers=root_headers)
    assert audit.status_code == 200, audit.text
    assert audit.json()["total"] >= 4
    assert all(entry["category"] == "orders" for entry in audit.json()["items"])


def test_cancelling_order_restores_recipe_stock(
    client: TestClient,
    root_headers: dict[str, str],
    storage_headers: dict[str, str],
    accounting_headers: dict[str, str],
    kitchen_headers: dict[str, str],
):
    item = client.post(
        "/inventory/items",
        headers=root_headers,
        json={"sku": "COF-1", "name": "Coffee", "unit": "gram", "reorder_level": 100, "selling_price": 0},
    ).json()
    client.post(
        f"/inventory/items/{item['id']}/movements",
        headers=storage_headers,
        json={"movement_type": "receive", "quantity": 1000, "unit_cost": 0.01, "reason": "Test receive"},
    )
    menu = client.post(
        "/menu-items",
        headers=root_headers,
        json={"name": "Espresso", "category": "Coffee", "selling_price": 3},
    ).json()
    client.post(
        "/kitchen/recipes",
        headers=kitchen_headers,
        json={"menu_item_id": menu["id"], "ingredients": [{"inventory_item_id": item["id"], "quantity": 20, "unit": "gram"}]},
    )
    order = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu["id"], "quantity": 2}]},
    ).json()
    assert client.get(f"/inventory/items/{item['id']}", headers=storage_headers).json()["current_quantity"] == "960.000"
    cancelled = client.patch(
        f"/orders/{order['id']}/status", headers=accounting_headers, json={"status": "cancelled"}
    )
    assert cancelled.status_code == 200, cancelled.text
    assert client.get(f"/inventory/items/{item['id']}", headers=storage_headers).json()["current_quantity"] == "1000.000"
