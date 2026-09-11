from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models import AuditLog, MovementType, Order, StockMovement
from app.services.payroll import period_profit
from test_staff_meals import create_accounting_staff, create_direct_staff_meal_product


def test_staff_toggle_and_waste_keep_receipts_real_and_costs_consistent(
    client, db_session, root_headers, storage_headers, accounting_headers,
):
    item_id, menu_id = create_direct_staff_meal_product(
        client, storage_headers=storage_headers, accounting_headers=accounting_headers,
    )
    staff = create_accounting_staff(client, root_headers=root_headers)
    ids = []
    for method in ("card", "cash", "online", "other"):
        response = client.post("/orders", headers=accounting_headers, json={
            "payment_method": method, "items": [{"menu_item_id": menu_id, "quantity": 1}],
        })
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    for extra in ({"staff_member_id": staff["id"]}, {"is_system_waste": True, "notes": "سوختن غذا در آماده‌سازی"}):
        response = client.post("/orders", headers=accounting_headers, json={
            **extra, "items": [{"menu_item_id": menu_id, "quantity": 2}],
        })
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    waste_id = ids[-1]
    waste = response.json()
    assert waste["is_system_waste"] and not waste["is_staff_meal"]
    assert waste["status"] == "completed"
    assert waste["customer_name"] == "اتلاف سیستم"
    assert Decimal(waste["total"]) == 0
    for order in db_session.scalars(select(Order).where(Order.id.in_(ids))):
        order.created_at = datetime(2026, 9, 9, 22, 30)  # 02:00 Tehran: business day September 9.
    db_session.commit()

    url = "/reports/overview?start_date=2026-09-09&end_date=2026-09-09"
    excluded = client.get(url, headers=root_headers)
    included = client.get(url + "&include_staff_meals=true", headers=root_headers)
    assert excluded.status_code == included.status_code == 200
    a, b = excluded.json(), included.json()
    assert a["period"]["include_staff_meals"] is False
    assert a["kpis"]["orders"] == 4
    assert b["kpis"]["orders"] == 5
    assert a["kpis"]["staff_orders"] == 0
    assert b["kpis"]["staff_orders"] == 1
    assert Decimal(b["kpis"]["staff_cost"]) == 80_000
    assert Decimal(a["kpis"]["waste_cost"]) == 80_000
    assert Decimal(a["kpis"]["revenue"]) == Decimal(b["kpis"]["revenue"]) == 1_800_000
    assert Decimal(a["kpis"]["gross_profit"]) == 1_560_000
    assert Decimal(b["kpis"]["gross_profit"]) == 1_480_000
    assert a["payment_breakdown"] == b["payment_breakdown"]
    assert all(Decimal(row["amount"]) == 450_000 and row["orders"] == 1 for row in a["payment_breakdown"])
    for report, count, quantity in ((a, 4, 4), (b, 5, 6)):
        daily = report["daily_sales"][0]
        assert daily["orders"] == count and daily["waste_orders"] == 1
        assert Decimal(daily["gross_profit"]) == Decimal(report["kpis"]["gross_profit"])
        assert sum(hour["orders"] for hour in report["hourly_demand"]) == count
        product = report["product_performance"][0]
        assert product["quantity"] == quantity and product["waste_quantity"] == 2
        assert Decimal(product["gross_profit"]) == Decimal(report["kpis"]["gross_profit"])
        assert report["category_performance"][0]["quantity"] == quantity
    assert period_profit(db_session, date(2026, 9, 9), date(2026, 9, 9)) == Decimal("1560000.00")
    assert client.get("/reports/overview?start_date=2026-09-10&end_date=2026-09-10", headers=root_headers).json()["kpis"]["orders"] == 0
    assert client.get("/reports/overview?start_date=2026-09-10&end_date=2026-09-09", headers=root_headers).status_code == 422
    assert client.get("/reports/overview?start_date=2026-09-09", headers=root_headers).status_code == 422
    history = client.get("/orders?day=2026-09-09&include_staff_meals=false", headers=accounting_headers).json()
    assert len(history) == 5 and all(not order["is_staff_meal"] for order in history)

    stock = client.get(f"/inventory/items/{item_id}", headers=root_headers).json()
    assert Decimal(stock["current_quantity"]) == 12
    movement = db_session.scalar(select(StockMovement).where(StockMovement.reference_id == waste_id, StockMovement.reference_type == "order"))
    assert movement.movement_type == MovementType.WASTE
    update = client.patch(f"/orders/{waste_id}", headers=accounting_headers, json={
        "items": [{"menu_item_id": menu_id, "quantity": 1}], "notes": "اصلاح تعداد اتلاف", "payment_method": "cash",
    })
    assert update.status_code == 200, update.text
    assert update.json()["is_system_waste"] and Decimal(update.json()["total"]) == 0
    assert client.patch(f"/orders/{waste_id}", headers=accounting_headers, json={
        "customer_id": None, "notes": "انتقال اتلاف", "items": [{"menu_item_id": menu_id, "quantity": 1}],
    }).status_code == 409
    receipt = client.get(f"/orders/{waste_id}/receipt", headers=accounting_headers).json()
    assert not receipt["customer_copy"]["show_prices"]
    assert "اتلاف" in receipt["customer_copy"]["title"]
    assert client.delete(f"/orders/{waste_id}", headers=accounting_headers).status_code == 204
    assert client.delete(f"/orders/{waste_id}", headers=accounting_headers).status_code == 404
    assert Decimal(client.get(f"/inventory/items/{item_id}", headers=root_headers).json()["current_quantity"]) == 14
    assert client.get(url, headers=root_headers).json()["kpis"]["waste_orders"] == 0


def test_archive_preserves_stock_history_and_blocks_new_consumption(
    client, db_session, root_headers, storage_headers, accounting_headers, kitchen_headers,
):
    item_id, menu_id = create_direct_staff_meal_product(
        client, storage_headers=storage_headers, accounting_headers=accounting_headers,
    )
    payload = {"items": [{"menu_item_id": menu_id, "quantity": 1}]}
    sale = client.post("/orders", headers=accounting_headers, json=payload)
    assert sale.status_code == 201
    assert client.delete(f"/inventory/items/{item_id}", headers=kitchen_headers).status_code == 403
    assert client.delete(f"/inventory/items/{item_id}", headers=accounting_headers).status_code == 204
    assert client.get("/inventory/items", headers=root_headers).json()["total"] == 0
    archived = client.get("/inventory/items?active=false", headers=root_headers).json()["items"][0]
    assert Decimal(archived["current_quantity"]) == 19
    assert not client.get("/menu-items", headers=accounting_headers).json()[0]["is_available"]
    assert client.post("/orders", headers=accounting_headers, json=payload).status_code == 409
    assert client.delete(f"/orders/{sale.json()['id']}", headers=accounting_headers).status_code == 204
    restored = client.patch(f"/inventory/items/{item_id}", headers=accounting_headers, json={"is_active": True})
    assert restored.status_code == 200 and Decimal(restored.json()["current_quantity"]) == 20
    assert client.post("/orders", headers=accounting_headers, json=payload).status_code == 201
    assert db_session.scalar(select(AuditLog).where(AuditLog.entity_type == "inventory_item", AuditLog.action == "archive")) is not None


def test_waste_requires_reason_and_exclusive_account(client, accounting_headers):
    base = {"is_system_waste": True, "items": [{"menu_item_id": 1, "quantity": 1}]}
    assert client.post("/orders", headers=accounting_headers, json=base).status_code == 422
    for key, value in (("staff_member_id", 1), ("customer_id", 1), ("customer", {"name": "مشتری", "phone": "09120000000"})):
        assert client.post("/orders", headers=accounting_headers, json={**base, key: value, "notes": "اتلاف غذا"}).status_code == 422
