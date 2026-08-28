from datetime import date, datetime

from app.routers import reports
from app.services import business_time


def test_day_bounds_convert_configured_business_day_to_utc(monkeypatch):
    monkeypatch.setattr(business_time.settings, "app_timezone", "Asia/Tehran")

    start, end = reports.day_bounds(date(2026, 1, 15))

    assert start == datetime(2026, 1, 14, 20, 30)
    assert end == datetime(2026, 1, 15, 20, 29, 59, 999999)


def test_business_datetime_uses_utc_for_stored_naive_values(monkeypatch):
    monkeypatch.setattr(business_time.settings, "app_timezone", "Asia/Tehran")

    localized = reports.business_datetime(datetime(2026, 1, 14, 20, 45))

    assert localized.isoformat() == "2026-01-15T00:15:00+03:30"


def test_invalid_business_timezone_falls_back_to_tehran(monkeypatch):
    monkeypatch.setattr(business_time.settings, "app_timezone", "not/a-timezone")

    start, end = reports.day_bounds(date(2026, 1, 15))

    assert start == datetime(2026, 1, 14, 20, 30)
    assert end == datetime(2026, 1, 15, 20, 29, 59, 999999)
