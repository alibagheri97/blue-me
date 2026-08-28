from fastapi.testclient import TestClient


FINANCIAL_ORDER_FIELDS = {
    "subtotal",
    "discount",
    "total",
    "payment_method",
    "created_by_id",
}
FINANCIAL_ORDER_LINE_FIELDS = {"unit_price", "line_total", "unit_cost", "line_cost"}
FINANCIAL_MENU_FIELDS = {
    "selling_price",
    "calculated_cost",
    "gross_profit",
    "margin_percent",
}
FINANCIAL_INVENTORY_FIELDS = {
    "selling_price",
    "selling_quantity",
    "selling_unit",
    "selling_total_price",
    "purchase_quantity",
    "purchase_unit",
    "purchase_total_price",
    "last_purchase_price",
}


def seed_sale_and_recipe(
    client: TestClient,
    *,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
    kitchen_headers: dict[str, str],
) -> tuple[dict, dict]:
    inventory = client.post(
        "/inventory/items",
        headers=root_headers,
        json={
            "sku": "PRIVACY-INGREDIENT-001",
            "name": "Privacy test ingredient",
            "unit": "gram",
            "reorder_level": "0",
            "target_stock_level": "0",
            "purchase_quantity": 1000,
            "purchase_unit": "gram",
            "purchase_price": 200_000,
            "selling_quantity": 1000,
            "selling_unit": "gram",
            "selling_price": 350_000,
        },
    )
    assert inventory.status_code == 201, inventory.text
    inventory_item = inventory.json()
    received = client.post(
        f"/inventory/items/{inventory_item['id']}/movements",
        headers=root_headers,
        json={
            "movement_type": "receive",
            "quantity": 10_000,
            "unit_cost": 200,
            "reason": "Opening stock for privacy test",
        },
    )
    assert received.status_code == 201, received.text

    direct_menu = client.post(
        "/menu-items",
        headers=accounting_headers,
        json={
            "name": "Privacy direct sale",
            "category": "Privacy",
            "selling_price": 500_000,
            "inventory_item_id": inventory_item["id"],
            "stock_quantity_per_sale": 100,
        },
    )
    assert direct_menu.status_code == 201, direct_menu.text
    order = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": direct_menu.json()["id"], "quantity": 2}]},
    )
    assert order.status_code == 201, order.text

    recipe_menu = client.post(
        "/menu-items",
        headers=accounting_headers,
        json={
            "name": "Privacy recipe sale",
            "category": "Privacy",
            "selling_price": 750_000,
            "is_active": False,
        },
    )
    assert recipe_menu.status_code == 201, recipe_menu.text
    recipe = client.post(
        "/kitchen/recipes",
        headers=kitchen_headers,
        json={
            "menu_item_id": recipe_menu.json()["id"],
            "yield_quantity": 1,
            "preparation_minutes": 10,
            "ingredients": [
                {
                    "inventory_item_id": inventory_item["id"],
                    "quantity": 120,
                    "unit": "gram",
                }
            ],
        },
    )
    assert recipe.status_code == 201, recipe.text
    return order.json(), recipe.json()


def test_only_root_and_accounting_can_access_sales_and_order_financials(
    client: TestClient,
    root_headers: dict[str, str],
    storage_headers: dict[str, str],
    accounting_headers: dict[str, str],
    kitchen_headers: dict[str, str],
    sales_headers: dict[str, str],
):
    order, _ = seed_sale_and_recipe(
        client,
        root_headers=root_headers,
        accounting_headers=accounting_headers,
        kitchen_headers=kitchen_headers,
    )
    order_id = order["id"]

    for headers in (root_headers, accounting_headers):
        dashboard = client.get("/dashboard", headers=headers)
        assert dashboard.status_code == 200, dashboard.text
        assert dashboard.json()["sales_today"] == "1000000.00"
        report = client.get("/reports/overview?days=30", headers=headers)
        assert report.status_code == 200, report.text
        assert report.json()["kpis"]["revenue"] == "1000000.00"
        order_response = client.get(f"/orders/{order_id}", headers=headers)
        assert order_response.status_code == 200, order_response.text
        assert order_response.json()["total"] == "1000000.00"
        receipt = client.get(f"/orders/{order_id}/receipt", headers=headers)
        assert receipt.status_code == 200, receipt.text

    for headers in (storage_headers, kitchen_headers, sales_headers):
        assert client.get("/dashboard", headers=headers).status_code == 403
        assert client.get("/reports/overview?days=30", headers=headers).status_code == 403
        assert client.get("/orders", headers=headers).status_code == 403
        assert client.get(f"/orders/{order_id}", headers=headers).status_code == 403
        assert client.get(f"/orders/{order_id}/receipt", headers=headers).status_code == 403
        assert client.get("/customers", headers=headers).status_code == 403
        assert client.get("/staff", headers=headers).status_code == 403

    forbidden_create = client.post(
        "/orders",
        headers=sales_headers,
        json={"items": [{"menu_item_id": order["items"][0]["menu_item_id"], "quantity": 1}]},
    )
    assert forbidden_create.status_code == 403


def test_kitchen_endpoints_return_only_operational_data(
    client: TestClient,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
    kitchen_headers: dict[str, str],
):
    order, created_recipe = seed_sale_and_recipe(
        client,
        root_headers=root_headers,
        accounting_headers=accounting_headers,
        kitchen_headers=kitchen_headers,
    )

    assert not FINANCIAL_MENU_FIELDS.intersection(created_recipe["menu_item"])
    assert "food_cost_percent" not in created_recipe
    assert not FINANCIAL_INVENTORY_FIELDS.intersection(
        created_recipe["ingredients"][0]["inventory_item"]
    )
    assert created_recipe["calculated_cost"] == "24000.00"

    menu = client.get("/kitchen/menu-items", headers=kitchen_headers)
    assert menu.status_code == 200, menu.text
    assert menu.json()
    assert all(not FINANCIAL_MENU_FIELDS.intersection(item) for item in menu.json())
    assert client.get("/menu-items", headers=kitchen_headers).status_code == 403

    inventory = client.get("/kitchen/inventory-items", headers=kitchen_headers)
    assert inventory.status_code == 200, inventory.text
    assert inventory.json()
    assert all(
        not FINANCIAL_INVENTORY_FIELDS.intersection(item) for item in inventory.json()
    )
    assert client.get("/inventory/items", headers=kitchen_headers).status_code == 403

    queue = client.get("/kitchen/orders", headers=kitchen_headers)
    assert queue.status_code == 200, queue.text
    ticket = next(item for item in queue.json() if item["id"] == order["id"])
    assert not FINANCIAL_ORDER_FIELDS.intersection(ticket)
    assert ticket["items"]
    assert all(
        not FINANCIAL_ORDER_LINE_FIELDS.intersection(line) for line in ticket["items"]
    )

    status_result = client.patch(
        f"/orders/{order['id']}/status",
        headers=kitchen_headers,
        json={"status": "preparing"},
    )
    assert status_result.status_code == 200, status_result.text
    assert status_result.json()["status"] == "preparing"
    assert not FINANCIAL_ORDER_FIELDS.intersection(status_result.json())
    assert all(
        not FINANCIAL_ORDER_LINE_FIELDS.intersection(line)
        for line in status_result.json()["items"]
    )
