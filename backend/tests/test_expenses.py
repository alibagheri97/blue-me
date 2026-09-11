from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import (
    InventoryItem,
    PurchaseReceipt,
    PurchaseStatus,
    StockMovement,
    User,
)


def receipt(client, headers, lines, when="2026-09-09T12:00:00", **extra):
    response = client.post(
        "/purchases",
        headers=headers,
        json={"purchased_at": when, "lines": lines, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def line(item, qty, unit, cost):
    return {
        "inventory_item_id": item,
        "quantity": str(qty),
        "purchase_unit": unit,
        "line_total": str(cost),
    }


def setup_ledger(client, headers, db):
    category = client.post(
        "/inventory/categories", headers=headers, json={"name": "مواد اولیه"}
    ).json()["id"]
    items = []
    for name, unit, cat in (("مرغ", "گرم", category), ("نان", "عدد", None)):
        r = client.post(
            "/inventory/items",
            headers=headers,
            json={"name": name, "sku": name, "unit": unit, "category_id": cat},
        )
        assert r.status_code == 201, r.text
        items.append(r.json()["id"])
    meat, bread = items
    first = receipt(
        client,
        headers,
        [line(meat, 2, "کیلوگرم", 200000), line(bread, 10, "عدد", 10000)],
        supplier_name="تأمین یک",
        extra_cost="20000",
        discount="10000",
        invoice_number="INV-1",
    )
    second = receipt(
        client,
        headers,
        [line(meat, 500, "گرم", 70000)],
        when="2026-09-10T02:00:00",
        supplier_name="تأمین دو",
    )
    voided = receipt(
        client, headers, [line(meat, 1000, "گرم", 800000)], supplier_name="باطل"
    )
    # Use the real void path, and verify the dashboard never deletes this history.
    response = client.post(
        f"/purchases/{voided['id']}/void",
        headers=headers,
        json={"reason": "ثبت اشتباه فاکتور"},
    )
    assert response.status_code == 200, response.text
    movement = client.post(
        f"/inventory/items/{bread}/movements",
        headers=headers,
        json={
            "movement_type": "receive",
            "quantity": "3",
            "unit_cost": "2000",
            "reason": "ورودی مستقیم نان",
        },
    )
    assert movement.status_code == 201, movement.text
    row = db.get(StockMovement, movement.json()["id"])
    row.created_at = datetime(2026, 9, 9, 22, 30)  # Tehran 02:00, still September 9.
    db.commit()
    return meat, bread, first, second, voided


DAY = "start_date=2026-09-09&end_date=2026-09-09"


@pytest.mark.parametrize(
    "opening_fields",
    [
        {"supplier_name": "موجودی اولیه موقت"},
        {"supplier_name": "  موجودی اولیه موقت  ", "invoice_number": "legacy-opening"},
        {"supplier_name": "Opening balance", "invoice_number": "OPENING-2026-08-26"},
        {"invoice_number": "OPENING-2026-08-26-SUPPLEMENT-01"},
        {"invoice_number": " opening-2026-09-09 "},
    ],
)
def test_temporary_opening_stock_is_excluded_from_the_entire_expenses_section(
    client,
    root_headers,
    db_session,
    opening_fields,
):
    meat, _, first, *_ = setup_ledger(client, root_headers, db_session)
    baseline = client.get(f"/expenses?{DAY}", headers=root_headers).json()
    opening = receipt(
        client,
        root_headers,
        [line(meat, 10, "کیلوگرم", 115025000)],
        when="2026-09-09T06:00:00",
        **opening_fields,
    )
    balances = [
        (i.id, i.current_quantity, i.average_cost)
        for i in db_session.scalars(select(InventoryItem).order_by(InventoryItem.id))
    ]
    movements = [
        (m.id, m.quantity, m.unit_cost)
        for m in db_session.scalars(select(StockMovement).order_by(StockMovement.id))
    ]
    data = client.get(f"/expenses?{DAY}", headers=root_headers).json()
    assert data == baseline
    for filters in (
        "",
        "&receipt_status=posted",
        "&receipt_status=voided",
        f"&item_id={meat}",
        "&search=موجودی اولیه موقت",
        "&supplier=موجودی اولیه موقت",
    ):
        result = client.get(f"/expenses?{DAY}{filters}", headers=root_headers).json()
        assert all(
            r["id"] != opening["id"]
            for r in result["receipts"]["items"]
            if r["source"] == "purchase"
        )
    options = client.get("/expenses/options", headers=root_headers).json()
    assert opening_fields.get("supplier_name") not in options["suppliers"]
    history = client.get(
        f"/expenses/items/{meat}/prices?{DAY}&stock_unit=گرم", headers=root_headers
    ).json()
    assert history["total"] == 2
    assert Decimal(history["summary"]["first_price"]) == Decimal(
        first["lines"][0]["unit_cost"]
    )
    assert all(
        r["source_id"] != opening["id"]
        for r in history["items"]
        if r["source"] == "purchase"
    )
    exported = client.get(f"/expenses/export?{DAY}", headers=root_headers).json()[
        "items"
    ]
    assert all(
        r["source_id"] != opening["id"] for r in exported if r["source"] == "purchase"
    )
    assert (
        client.get(
            f"/expenses/receipts/{opening['id']}", headers=root_headers
        ).status_code
        == 404
    )
    assert (
        client.get(f"/purchases/{opening['id']}", headers=root_headers).status_code
        == 200
    )
    assert balances == [
        (i.id, i.current_quantity, i.average_cost)
        for i in db_session.scalars(select(InventoryItem).order_by(InventoryItem.id))
    ]
    assert movements == [
        (m.id, m.quantity, m.unit_cost)
        for m in db_session.scalars(select(StockMovement).order_by(StockMovement.id))
    ]


def test_real_purchases_are_not_excluded_for_missing_metadata_or_temporary_notes(
    client,
    root_headers,
    db_session,
):
    meat, *_ = setup_ledger(client, root_headers, db_session)
    for extra in (
        {},
        {"supplier_name": "", "invoice_number": ""},
        {
            "notes": "فاکتور خرید واقعی؛ جایگزین موجودی اولیه موقت",
            "supplier_name": "فروشنده واقعی",
            "invoice_number": "BUY-OPENING-REPLACEMENT",
        },
    ):
        receipt(client, root_headers, [line(meat, 1, "کیلوگرم", 100000)], **extra)
    result = client.get(f"/expenses?{DAY}", headers=root_headers).json()
    assert Decimal(result["kpis"]["total_cost"]) == 596000
    assert result["kpis"]["purchase_count"] == 5


def test_expense_totals_price_history_receipt_details_and_export(
    client, root_headers, db_session
):
    meat, bread, first, second, voided = setup_ledger(client, root_headers, db_session)
    before_stock = [
        item.current_quantity
        for item in db_session.scalars(select(InventoryItem).order_by(InventoryItem.id))
    ]
    response = client.get(f"/expenses?{DAY}", headers=root_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    kpi = data["kpis"]
    assert Decimal(kpi["total_cost"]) == 296000
    assert Decimal(kpi["purchase_cost"]) == 290000
    assert Decimal(kpi["manual_cost"]) == 6000
    assert Decimal(kpi["goods_cost"]) == 286000
    assert Decimal(kpi["net_adjustment"]) == 10000
    assert kpi["posted_count"] == 3 and kpi["voided_count"] == 1
    assert kpi["price_increases"] == 2
    assert sum(Decimal(r["cost"]) for r in data["daily"]) == 296000
    for key in ("categories", "suppliers"):
        assert sum(Decimal(r["cost"]) for r in data[key]) == 296000
    assert sum(Decimal(r["total_cost"]) for r in data["items"]) == 296000
    assert data["receipts"]["total"] == 4
    assert (
        next(r for r in data["receipts"]["items"] if r["source"] == "manual")[
            "manual_line"
        ]["unit"]
        == "عدد"
    )
    history = client.get(
        f"/expenses/items/{meat}/prices?{DAY}&stock_unit=گرم&page_size=1",
        headers=root_headers,
    )
    assert history.status_code == 200, history.text
    p = history.json()
    assert p["total"] == 2 and len(p["items"]) == 1
    assert Decimal(p["summary"]["quantity"]) == 2500
    assert Decimal(p["summary"]["first_price"]) == Decimal("104.7619")
    assert Decimal(p["summary"]["last_price"]) == 140
    assert Decimal(p["summary"]["change_percent"]) == Decimal("33.64")
    assert len(p["daily"]) == 1 and Decimal(p["daily"][0]["price"]) == 140
    assert p["items"][0]["source_id"] == second["id"]
    assert (
        client.get(f"/expenses/receipts/{first['id']}", headers=root_headers).json()[
            "lines"
        ]
        == first["lines"]
    )
    exported = client.get(f"/expenses/export?{DAY}", headers=root_headers).json()[
        "items"
    ]
    assert len(exported) == 5  # Includes the voided row, explicitly labelled.
    assert (
        sum(Decimal(r["landed_total"]) for r in exported if r["status"] == "posted")
        == 296000
    )
    after_stock = [
        item.current_quantity
        for item in db_session.scalars(select(InventoryItem).order_by(InventoryItem.id))
    ]
    assert before_stock == after_stock
    assert db_session.get(PurchaseReceipt, voided["id"]).status == PurchaseStatus.VOIDED


def test_expense_filters_use_matched_line_cost_and_keep_history_after_archive(
    client, root_headers, db_session
):
    meat, bread, first, _, _ = setup_ledger(client, root_headers, db_session)
    expected = Decimal(first["lines"][0]["landed_total"]) + 70000
    response = client.get(
        f"/expenses?{DAY}&item_id={meat}&receipt_status=posted&page_size=1",
        headers=root_headers,
    )
    a = response.json()
    assert Decimal(a["kpis"]["total_cost"]) == expected
    assert a["receipts"]["total"] == 2 and len(a["receipts"]["items"]) == 1
    b = client.get(
        f"/expenses?{DAY}&item_id={meat}&receipt_status=voided", headers=root_headers
    ).json()
    assert a["kpis"] == b["kpis"]  # Status controls the receipt list only.
    assert len(b["receipts"]["items"]) == 1
    category_id = db_session.get(InventoryItem, meat).category_id
    c = client.get(
        f"/expenses?{DAY}&category_id={category_id}", headers=root_headers
    ).json()
    assert Decimal(c["kpis"]["total_cost"]) == expected
    c = client.get(f"/expenses?{DAY}&category_id=0", headers=root_headers).json()
    assert (
        Decimal(c["kpis"]["total_cost"])
        == Decimal(first["lines"][1]["landed_total"]) + 6000
    )
    c = client.get(f"/expenses?{DAY}&supplier=تأمین یک", headers=root_headers).json()
    assert Decimal(c["kpis"]["total_cost"]) == 220000
    c = client.get(f"/expenses?{DAY}&source=manual", headers=root_headers).json()
    assert Decimal(c["kpis"]["total_cost"]) == 6000
    c = client.get(f"/expenses?{DAY}&search=INV-1", headers=root_headers).json()
    assert Decimal(c["kpis"]["total_cost"]) == 220000
    assert (
        client.delete(f"/inventory/items/{meat}", headers=root_headers).status_code
        == 204
    )
    db_session.get(InventoryItem, meat).last_purchase_price = 999999
    db_session.commit()
    c = client.get(f"/expenses?{DAY}&item_id={meat}", headers=root_headers).json()
    assert c["items"][0]["is_active"] is False
    assert Decimal(c["items"][0]["last_price"]) == 140
    assert Decimal(c["kpis"]["total_cost"]) == expected


def test_expense_business_boundary_zero_price_and_empty_ranges(
    client, root_headers, db_session
):
    meat, bread, *_ = setup_ledger(client, root_headers, db_session)
    receipt(
        client, root_headers, [line(bread, 1, "عدد", 0)], when="2026-09-10T04:59:59"
    )
    receipt(
        client, root_headers, [line(bread, 1, "عدد", 999)], when="2026-09-10T05:00:00"
    )
    next_day = client.get(
        "/expenses?start_date=2026-09-10&end_date=2026-09-10", headers=root_headers
    ).json()
    assert Decimal(next_day["kpis"]["total_cost"]) == 999
    empty = client.get(
        "/expenses?start_date=2026-08-10&end_date=2026-08-10", headers=root_headers
    ).json()
    assert Decimal(empty["kpis"]["total_cost"]) == 0 and len(empty["daily"]) == 1
    for query in (
        "start_date=2026-09-09",
        "start_date=2026-09-10&end_date=2026-09-09",
        "days=366",
        "days=0",
        "category_id=-1",
        "source=invalid",
    ):
        assert client.get(f"/expenses?{query}", headers=root_headers).status_code == 422
    assert (
        client.get(
            f"/expenses/items/{meat}/prices?{DAY}&stock_unit=عدد", headers=root_headers
        ).json()["summary"]
        is None
    )
    assert (
        client.get(
            "/expenses/items/999999/prices?stock_unit=عدد", headers=root_headers
        ).status_code
        == 404
    )
    assert (
        client.get("/expenses/receipts/999999", headers=root_headers).status_code == 404
    )


def test_expenses_permission_is_independent_and_read_only(
    client,
    root_headers,
    accounting_headers,
    kitchen_headers,
    storage_headers,
    db_session,
):
    assert client.get("/expenses", headers=accounting_headers).status_code == 200
    for headers in (kitchen_headers, storage_headers):
        for path in (
            "/expenses",
            "/expenses/options",
            "/expenses/export",
            "/expenses/receipts/1",
            "/expenses/items/1/prices?stock_unit=عدد",
        ):
            assert client.get(path, headers=headers).status_code == 403
    user = db_session.scalar(select(User).where(User.username == "kitchen"))
    response = client.patch(
        f"/users/{user.id}", headers=root_headers, json={"section_access": ["expenses"]}
    )
    assert response.status_code == 200, response.text
    assert client.get("/expenses", headers=kitchen_headers).status_code == 200
    assert client.get("/expenses/options", headers=kitchen_headers).status_code == 200
    assert client.get("/inventory/items", headers=kitchen_headers).status_code == 403
    assert client.get("/reports/overview", headers=kitchen_headers).status_code == 403
    assert (
        client.post(
            "/purchases",
            headers=kitchen_headers,
            json={
                "purchased_at": "2026-09-09T12:00:00",
                "lines": [line(1, 1, "عدد", 1)],
            },
        ).status_code
        == 403
    )
    user.section_access_override = []
    db_session.commit()
    assert client.get("/expenses", headers=kitchen_headers).status_code == 403


def test_price_history_does_not_compare_different_historic_units(
    client, root_headers, db_session
):
    meat, *_ = setup_ledger(client, root_headers, db_session)
    row = db_session.get(InventoryItem, meat)
    # Historical snapshots must survive a changed unit, even for legacy imports.
    row.unit = "کیلوگرم"
    db_session.commit()
    receipt(
        client,
        root_headers,
        [line(meat, 1, "کیلوگرم", 200000)],
        when="2026-09-09T18:00:00",
    )
    result = client.get(f"/expenses?{DAY}&item_id={meat}", headers=root_headers).json()
    assert {r["unit"] for r in result["items"]} == {"گرم", "کیلوگرم"}
    prices = client.get(
        f"/expenses/items/{meat}/prices?{DAY}&stock_unit=کیلوگرم", headers=root_headers
    ).json()
    assert prices["total"] == 1 and Decimal(prices["summary"]["last_price"]) == 200000
