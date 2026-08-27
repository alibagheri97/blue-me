from datetime import date, datetime, timedelta
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
        f"/users/{created.json()['id']}",
        headers=root_headers,
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False


def test_inventory_edit_supports_unit_purchase_and_selling_prices(
    client: TestClient,
    root_headers: dict[str, str],
    storage_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    created = client.post(
        "/inventory/items",
        headers=root_headers,
        json={
            "sku": "UNIT-PRICE-001",
            "name": "Unit-priced ingredient",
            "unit": "gram",
            "reorder_level": "0",
            "target_stock_level": "0",
            "purchase_price": "10",
            "selling_price": "20",
        },
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    assert Decimal(created.json()["average_cost"]) == Decimal("10")
    assert Decimal(created.json()["last_purchase_price"]) == Decimal("10")
    assert Decimal(created.json()["selling_price"]) == Decimal("20")

    received = client.post(
        f"/inventory/items/{item_id}/movements",
        headers=storage_headers,
        json={
            "movement_type": "receive",
            "quantity": "100",
            "unit_cost": "10",
            "reason": "Opening stock for unit price test",
        },
    )
    assert received.status_code == 201, received.text

    menu_category = client.post(
        "/menu-categories",
        headers=accounting_headers,
        json={"name": "Unit price test menu", "color": "#2563eb"},
    )
    assert menu_category.status_code == 201, menu_category.text
    menu_item = client.post(
        "/menu-items",
        headers=accounting_headers,
        json={
            "name": "Direct unit price sale",
            "category": "Unit price test menu",
            "category_id": menu_category.json()["id"],
            "selling_price": "100",
            "inventory_item_id": item_id,
            "stock_quantity_per_sale": "2",
        },
    )
    assert menu_item.status_code == 201, menu_item.text
    first_order = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu_item.json()["id"], "quantity": 1}]},
    )
    assert first_order.status_code == 201, first_order.text
    assert Decimal(first_order.json()["items"][0]["line_cost"]) == Decimal("20")

    root_edit = client.patch(
        f"/inventory/items/{item_id}",
        headers=root_headers,
        json={
            "purchase_price": "12",
            "selling_price": "25",
            "price_change_reason": "Supplier and retail price update",
        },
    )
    assert root_edit.status_code == 200, root_edit.text
    assert Decimal(root_edit.json()["average_cost"]) == Decimal("12")
    assert Decimal(root_edit.json()["last_purchase_price"]) == Decimal("12")
    assert Decimal(root_edit.json()["selling_price"]) == Decimal("25")
    second_order = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu_item.json()["id"], "quantity": 1}]},
    )
    assert second_order.status_code == 201, second_order.text
    assert Decimal(second_order.json()["items"][0]["line_cost"]) == Decimal("24")
    assert Decimal(first_order.json()["items"][0]["line_cost"]) == Decimal("20")

    proposed = client.patch(
        f"/inventory/items/{item_id}",
        headers=storage_headers,
        json={
            "purchase_price": "15",
            "selling_price": "30",
            "price_change_reason": "New supplier quotation",
        },
    )
    assert proposed.status_code == 200, proposed.text
    assert Decimal(proposed.json()["average_cost"]) == Decimal("12")
    assert Decimal(proposed.json()["selling_price"]) == Decimal("25")

    all_requests = client.get("/inventory/price-requests", headers=root_headers)
    assert all_requests.status_code == 200, all_requests.text
    pending = [
        request
        for request in all_requests.json()
        if request["item_id"] == item_id and request["status"] == "pending"
    ]
    assert {request["price_type"] for request in pending} == {"purchase", "selling"}
    for request in pending:
        decision = client.post(
            f"/inventory/price-requests/{request['id']}/decision",
            headers=root_headers,
            json={"status": "approved", "note": "Approved unit pricing"},
        )
        assert decision.status_code == 200, decision.text

    final_item = client.get(f"/inventory/items/{item_id}", headers=root_headers)
    assert Decimal(final_item.json()["average_cost"]) == Decimal("15")
    assert Decimal(final_item.json()["last_purchase_price"]) == Decimal("15")
    assert Decimal(final_item.json()["selling_price"]) == Decimal("30")


def test_menu_visibility_controls_accounting_sale_and_monochrome_receipt(
    client: TestClient,
    root_headers: dict[str, str],
    storage_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    inventory_item = client.post(
        "/inventory/items",
        headers=root_headers,
        json={
            "sku": "POS-VISIBLE-001",
            "name": "Direct sale drink",
            "unit": "bottle",
            "reorder_level": "0",
            "target_stock_level": "0",
            "purchase_price": "10000",
        },
    )
    assert inventory_item.status_code == 201, inventory_item.text
    item_id = inventory_item.json()["id"]
    received = client.post(
        f"/inventory/items/{item_id}/movements",
        headers=storage_headers,
        json={
            "movement_type": "receive",
            "quantity": "10",
            "unit_cost": "10000",
            "reason": "Opening POS visibility test stock",
        },
    )
    assert received.status_code == 201, received.text

    category = client.post(
        "/menu-categories",
        headers=accounting_headers,
        json={"name": "POS visibility", "color": "#111111"},
    )
    assert category.status_code == 201, category.text
    hidden_item = client.post(
        "/menu-items",
        headers=accounting_headers,
        json={
            "name": "Hidden until approved for sale",
            "category": category.json()["name"],
            "category_id": category.json()["id"],
            "selling_price": "25000",
            "inventory_item_id": item_id,
            "stock_quantity_per_sale": "1",
            "is_active": False,
        },
    )
    assert hidden_item.status_code == 201, hidden_item.text
    menu_item_id = hidden_item.json()["id"]
    assert hidden_item.json()["recipe_configured"] is True
    assert hidden_item.json()["is_available"] is True

    management_menu = client.get(
        "/menu-items?include_inactive=true", headers=accounting_headers
    )
    assert management_menu.status_code == 200, management_menu.text
    assert menu_item_id in {item["id"] for item in management_menu.json()}
    sale_menu = client.get("/menu-items?active=true", headers=accounting_headers)
    assert sale_menu.status_code == 200, sale_menu.text
    assert menu_item_id not in {item["id"] for item in sale_menu.json()}

    hidden_order = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu_item_id, "quantity": 1}]},
    )
    assert hidden_order.status_code == 400, hidden_order.text

    shown_item = client.patch(
        f"/menu-items/{menu_item_id}",
        headers=accounting_headers,
        json={"is_active": True},
    )
    assert shown_item.status_code == 200, shown_item.text
    sale_menu = client.get("/menu-items?active=true", headers=accounting_headers)
    assert [item["id"] for item in sale_menu.json()] == [menu_item_id]
    assert sale_menu.json()[0]["is_available"] is True

    order = client.post(
        "/orders",
        headers=accounting_headers,
        json={
            "items": [{"menu_item_id": menu_item_id, "quantity": 2}],
            "payment_method": "cash",
        },
    )
    assert order.status_code == 201, order.text
    assert Decimal(order.json()["items"][0]["unit_price"]) == Decimal("25000")
    assert Decimal(order.json()["total"]) == Decimal("50000")

    receipt = client.get(
        f"/orders/{order.json()['id']}/receipt", headers=accounting_headers
    )
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["customer_copy"] == {
        "title": "رسید مشتری",
        "show_prices": True,
        "footer": "از خرید شما سپاسگزاریم",
        "paper_width_mm": 80,
        "monochrome": True,
        "high_contrast": True,
        "font_weight": 800,
        "minimum_font_size_pt": 11,
    }
    assert receipt.json()["kitchen_copy"]["monochrome"] is True
    assert receipt.json()["kitchen_copy"]["high_contrast"] is True
    assert receipt.json()["kitchen_copy"]["font_weight"] == 800
    assert 35 <= len(receipt.json()["quote"]["body"]) <= 135
    assert receipt.json()["quote"]["author"]
    reprint = client.get(
        f"/orders/{order.json()['id']}/receipt", headers=accounting_headers
    )
    assert reprint.json()["quote"] == receipt.json()["quote"]
    assert receipt.json()["order"]["id"] == order.json()["id"]


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
    assert (
        client.get(
            f"/orders/{order_data['id']}/receipt", headers=accounting_headers
        ).status_code
        == 200
    )

    assert (
        client.patch(
            f"/orders/{order_data['id']}/status",
            headers=kitchen_headers,
            json={"status": "preparing"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/orders/{order_data['id']}/status",
            headers=kitchen_headers,
            json={"status": "ready"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/orders/{order_data['id']}/status",
            headers=accounting_headers,
            json={"status": "completed"},
        ).status_code
        == 200
    )

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
        json={
            "sku": "COF-1",
            "name": "Coffee",
            "unit": "gram",
            "reorder_level": 100,
            "selling_price": 0,
        },
    ).json()
    client.post(
        f"/inventory/items/{item['id']}/movements",
        headers=storage_headers,
        json={
            "movement_type": "receive",
            "quantity": 1000,
            "unit_cost": 0.01,
            "reason": "Test receive",
        },
    )
    menu = client.post(
        "/menu-items",
        headers=root_headers,
        json={"name": "Espresso", "category": "Coffee", "selling_price": 3},
    ).json()
    client.post(
        "/kitchen/recipes",
        headers=kitchen_headers,
        json={
            "menu_item_id": menu["id"],
            "ingredients": [
                {"inventory_item_id": item["id"], "quantity": 20, "unit": "gram"}
            ],
        },
    )
    order = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu["id"], "quantity": 2}]},
    ).json()
    assert (
        client.get(f"/inventory/items/{item['id']}", headers=storage_headers).json()[
            "current_quantity"
        ]
        == "960.000"
    )
    cancelled = client.patch(
        f"/orders/{order['id']}/status",
        headers=accounting_headers,
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert (
        client.get(f"/inventory/items/{item['id']}", headers=storage_headers).json()[
            "current_quantity"
        ]
        == "1000.000"
    )


def test_batch_purchase_direct_sale_historic_profit_and_automatic_shopping(
    client: TestClient,
    root_headers: dict[str, str],
    storage_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    category = client.post(
        "/inventory/categories",
        headers=storage_headers,
        json={"name": "نوشیدنی تست", "color": "#06b6d4"},
    ).json()
    water = client.post(
        "/inventory/items",
        headers=storage_headers,
        json={
            "sku": "WATER-TEST",
            "name": "آب معدنی تست",
            "category_id": category["id"],
            "unit": "عدد",
            "reorder_level": 5,
            "target_stock_level": 24,
            "auto_reorder_enabled": False,
            "selling_price": 0,
        },
    ).json()
    meat = client.post(
        "/inventory/items",
        headers=storage_headers,
        json={
            "sku": "MEAT-TEST",
            "name": "گوشت تست",
            "unit": "گرم",
            "reorder_level": 1000,
            "target_stock_level": 5000,
            "auto_reorder_enabled": False,
            "selling_price": 0,
        },
    ).json()

    receipt = client.post(
        "/purchases",
        headers=storage_headers,
        json={
            "supplier_name": "تأمین‌کننده تست",
            "invoice_number": "INV-100",
            "purchased_at": datetime.now().isoformat(),
            "extra_cost": 11000,
            "discount": 0,
            "lines": [
                {
                    "inventory_item_id": water["id"],
                    "quantity": 24,
                    "purchase_unit": "عدد",
                    "conversion_factor": 1,
                    "line_total": 155000,
                },
                {
                    "inventory_item_id": meat["id"],
                    "quantity": 5,
                    "purchase_unit": "کیلوگرم",
                    "conversion_factor": 1000,
                    "line_total": 1000000,
                },
            ],
        },
    )
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["total_cost"] == "1166000.00"
    assert receipt.json()["lines"][1]["stock_quantity"] == "5000.000"
    assert (
        client.get(f"/inventory/items/{water['id']}", headers=storage_headers).json()[
            "current_quantity"
        ]
        == "24.000"
    )
    assert (
        client.get(f"/inventory/items/{meat['id']}", headers=storage_headers).json()[
            "current_quantity"
        ]
        == "5000.000"
    )
    assert (
        client.post("/purchases", headers=accounting_headers, json={}).status_code
        == 403
    )

    enabled = client.patch(
        f"/inventory/items/{water['id']}",
        headers=storage_headers,
        json={"auto_reorder_enabled": True},
    )
    assert enabled.status_code == 200, enabled.text

    menu_category = client.post(
        "/menu-categories",
        headers=accounting_headers,
        json={"name": "نوشیدنی صندوق", "color": "#0284c7", "sort_order": 10},
    )
    assert menu_category.status_code == 201, menu_category.text
    menu = client.post(
        "/menu-items",
        headers=accounting_headers,
        json={
            "name": "آب معدنی فروش",
            "category_id": menu_category.json()["id"],
            "category": "نوشیدنی صندوق",
            "selling_price": 10000,
            "inventory_item_id": water["id"],
            "stock_quantity_per_sale": 1,
            "is_active": True,
        },
    )
    assert menu.status_code == 201, menu.text
    assert menu.json()["recipe_configured"] is True
    assert menu.json()["max_available_quantity"] == 24

    order = client.post(
        "/orders",
        headers=accounting_headers,
        json={"items": [{"menu_item_id": menu.json()["id"], "quantity": 20}]},
    )
    assert order.status_code == 201, order.text
    order_line = order.json()["items"][0]
    original_line_cost = Decimal(order_line["line_cost"])
    assert original_line_cost > 0
    assert (
        client.get(f"/inventory/items/{water['id']}", headers=storage_headers).json()[
            "current_quantity"
        ]
        == "4.000"
    )

    needs = client.get("/kitchen/daily-needs", headers=root_headers)
    automatic = [
        need for need in needs.json() if need["inventory_item_id"] == water["id"]
    ]
    assert len(automatic) == 1
    assert automatic[0]["source"] == "automatic"
    assert automatic[0]["quantity"] == "20.000"
    notifications = client.get("/notifications", headers=root_headers)
    assert notifications.status_code == 200
    assert notifications.json()["unread_count"] == 1

    report_before = client.get("/reports/overview?days=30", headers=root_headers).json()
    assert Decimal(report_before["kpis"]["estimated_cogs"]) == original_line_cost

    cannot_void_consumed = client.post(
        f"/purchases/{receipt.json()['id']}/void",
        headers=root_headers,
        json={"reason": "تست کنترل ابطال"},
    )
    assert cannot_void_consumed.status_code == 409

    replenishment = client.post(
        "/purchases",
        headers=storage_headers,
        json={
            "supplier_name": "تأمین‌کننده دوم",
            "purchased_at": datetime.now().isoformat(),
            "lines": [
                {
                    "inventory_item_id": water["id"],
                    "quantity": 20,
                    "purchase_unit": "عدد",
                    "conversion_factor": 1,
                    "line_total": 300000,
                }
            ],
        },
    )
    assert replenishment.status_code == 201, replenishment.text
    updated_need = next(
        need
        for need in client.get("/kitchen/daily-needs", headers=root_headers).json()
        if need["id"] == automatic[0]["id"]
    )
    assert updated_need["status"] == "fulfilled"
    report_after = client.get("/reports/overview?days=30", headers=root_headers).json()
    assert Decimal(report_after["kpis"]["estimated_cogs"]) == original_line_cost
    assert Decimal(report_after["kpis"]["purchase_spend"]) == Decimal("1466000.00")

    unused_category = client.post(
        "/menu-categories",
        headers=accounting_headers,
        json={"name": "دسته موقت", "color": "#64748b"},
    ).json()
    assert (
        client.delete(
            f"/menu-categories/{unused_category['id']}", headers=accounting_headers
        ).status_code
        == 204
    )


def test_menu_recipe_deducts_every_ingredient_for_each_ordered_output(
    client: TestClient,
    root_headers: dict[str, str],
    storage_headers: dict[str, str],
    accounting_headers: dict[str, str],
    kitchen_headers: dict[str, str],
):
    category = client.post(
        "/inventory/categories",
        headers=storage_headers,
        json={"name": "مواد تست شاورما", "color": "#f59e0b"},
    )
    assert category.status_code == 201, category.text

    ingredient_specs = [
        ("مرغ تست", "گرم", "1000", "100"),
        ("نان تست", "عدد", "20", "1"),
        ("نمک تست", "گرم", "100", "2"),
        ("پنیر پیتزا تست", "گرم", "500", "20"),
    ]
    ingredients = []
    for index, (name, unit, opening_stock, recipe_quantity) in enumerate(
        ingredient_specs, 1
    ):
        created = client.post(
            "/inventory/items",
            headers=storage_headers,
            json={
                "sku": f"SHAWARMA-{index}",
                "name": name,
                "category_id": category.json()["id"],
                "unit": unit,
                "reorder_level": 0,
                "selling_price": 0,
            },
        )
        assert created.status_code == 201, created.text
        received = client.post(
            f"/inventory/items/{created.json()['id']}/movements",
            headers=storage_headers,
            json={
                "movement_type": "receive",
                "quantity": opening_stock,
                "unit_cost": "10",
                "reason": "موجودی اولیه تست فرمول چند ماده‌ای",
            },
        )
        assert received.status_code == 201, received.text
        ingredients.append(
            {
                "id": created.json()["id"],
                "unit": unit,
                "opening_stock": Decimal(opening_stock),
                "recipe_quantity": Decimal(recipe_quantity),
            }
        )

    menu_item = client.post(
        "/menu-items",
        headers=root_headers,
        json={
            "name": "شاورما مرغ پنیری تست",
            "category": "شاورما",
            "selling_price": "150000",
            "is_active": True,
        },
    )
    assert menu_item.status_code == 201, menu_item.text

    recipe = client.post(
        "/kitchen/recipes",
        headers=kitchen_headers,
        json={
            "menu_item_id": menu_item.json()["id"],
            "yield_quantity": "1",
            "preparation_minutes": 8,
            "instructions": "مواد را برای یک شاورما آماده کنید.",
            "ingredients": [
                {
                    "inventory_item_id": ingredient["id"],
                    "quantity": str(ingredient["recipe_quantity"]),
                    "unit": ingredient["unit"],
                }
                for ingredient in ingredients
            ],
        },
    )
    assert recipe.status_code == 201, recipe.text
    assert len(recipe.json()["ingredients"]) == 4

    order = client.post(
        "/orders",
        headers=accounting_headers,
        json={
            "items": [{"menu_item_id": menu_item.json()["id"], "quantity": 2}],
            "payment_method": "cash",
        },
    )
    assert order.status_code == 201, order.text

    for ingredient in ingredients:
        item = client.get(
            f"/inventory/items/{ingredient['id']}", headers=storage_headers
        )
        assert item.status_code == 200
        expected = ingredient["opening_stock"] - ingredient["recipe_quantity"] * 2
        assert Decimal(item.json()["current_quantity"]) == expected
