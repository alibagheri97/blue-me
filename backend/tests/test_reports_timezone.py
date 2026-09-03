from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models import Order, OrderStatus, PaymentMethod, User, UserRole
from app.routers import reports
from app.services import business_time


def test_day_bounds_convert_configured_business_day_to_utc(monkeypatch):
    monkeypatch.setattr(business_time.settings, "app_timezone", "Asia/Tehran")
    monkeypatch.setattr(business_time.settings, "business_day_start_hour", 5)

    start, end = reports.day_bounds(date(2026, 1, 15))

    assert start == datetime(2026, 1, 15, 1, 30)
    assert end == datetime(2026, 1, 16, 1, 29, 59, 999999)


def test_business_datetime_uses_utc_for_stored_naive_values(monkeypatch):
    monkeypatch.setattr(business_time.settings, "app_timezone", "Asia/Tehran")

    localized = reports.business_datetime(datetime(2026, 1, 14, 20, 45))

    assert localized.isoformat() == "2026-01-15T00:15:00+03:30"


def test_business_date_assigns_after_midnight_sales_to_previous_day(monkeypatch):
    monkeypatch.setattr(business_time.settings, "app_timezone", "Asia/Tehran")
    monkeypatch.setattr(business_time.settings, "business_day_start_hour", 5)

    assert business_time.business_date(datetime(2026, 1, 14, 22, 30)) == date(
        2026, 1, 14
    )
    assert business_time.business_date(datetime(2026, 1, 15, 1, 30)) == date(
        2026, 1, 15
    )


def test_statistics_and_order_history_use_five_am_business_day(
    client, db_session, root_headers, monkeypatch
):
    monkeypatch.setattr(business_time.settings, "app_timezone", "Asia/Tehran")
    monkeypatch.setattr(business_time.settings, "business_day_start_hour", 5)
    monkeypatch.setattr(reports, "business_today", lambda: date(2026, 1, 15))
    root = db_session.scalar(select(User).where(User.role == UserRole.ROOT))
    assert root is not None

    def sale(
        number: str,
        total: str,
        created_at: datetime,
        payment_method: PaymentMethod = PaymentMethod.CASH,
    ) -> Order:
        return Order(
            order_number=number,
            status=OrderStatus.COMPLETED,
            customer_name="Guest",
            subtotal=Decimal(total),
            discount=Decimal("0"),
            total=Decimal(total),
            payment_method=payment_method,
            created_by_id=root.id,
            created_at=created_at,
            updated_at=created_at,
        )

    db_session.add_all(
        [
            sale("PREVIOUS-0200", "100", datetime(2026, 1, 14, 22, 30)),
            sale(
                "CURRENT-0500",
                "200",
                datetime(2026, 1, 15, 1, 30),
                PaymentMethod.CARD,
            ),
            sale(
                "CURRENT-0200",
                "300",
                datetime(2026, 1, 15, 22, 30),
                PaymentMethod.ONLINE,
            ),
            sale(
                "NEXT-0500",
                "400",
                datetime(2026, 1, 16, 1, 30),
                PaymentMethod.OTHER,
            ),
        ]
    )
    db_session.commit()

    dashboard = client.get("/dashboard", headers=root_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["sales_today"] == "500.00"
    assert dashboard.json()["orders_today"] == 2

    history = client.get("/orders?day=2026-01-15", headers=root_headers)
    assert history.status_code == 200
    assert {order["order_number"] for order in history.json()} == {
        "CURRENT-0500",
        "CURRENT-0200",
    }

    report = client.get("/reports/overview?days=7", headers=root_headers)
    assert report.status_code == 200
    daily = {entry["date"]: entry for entry in report.json()["daily_sales"]}
    assert daily["2026-01-14"]["revenue"] == "100.00"
    assert daily["2026-01-15"]["revenue"] == "500.00"
    assert report.json()["kpis"]["revenue"] == "600.00"
    totals = {
        entry["method"]: entry for entry in report.json()["payment_breakdown"]
    }
    assert totals["cash"] == {
        "method": "cash",
        "amount": "100.00",
        "orders": 1,
        "share_percent": "16.67",
    }
    assert totals["card"]["amount"] == "200.00"
    assert totals["online"]["amount"] == "300.00"
    assert totals["other"]["amount"] == "0.00"
    selected_day = {
        entry["method"]: entry
        for entry in daily["2026-01-15"]["payment_breakdown"]
    }
    assert selected_day["cash"]["amount"] == "0.00"
    assert selected_day["card"]["amount"] == "200.00"
    assert selected_day["online"]["amount"] == "300.00"
    assert selected_day["other"]["amount"] == "0.00"


def test_invalid_business_timezone_falls_back_to_tehran(monkeypatch):
    monkeypatch.setattr(business_time.settings, "app_timezone", "not/a-timezone")
    monkeypatch.setattr(business_time.settings, "business_day_start_hour", 5)

    start, end = reports.day_bounds(date(2026, 1, 15))

    assert start == datetime(2026, 1, 15, 1, 30)
    assert end == datetime(2026, 1, 16, 1, 29, 59, 999999)
