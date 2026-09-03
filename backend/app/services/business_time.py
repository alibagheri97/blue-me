from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings


def business_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.app_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Tehran")


def business_datetime(value: datetime) -> datetime:
    utc_value = (
        value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    )
    return utc_value.astimezone(business_timezone())


def business_date(value: datetime | None = None) -> date:
    """Return the operating date after applying the configured day cut-off."""
    localized = business_datetime(value or datetime.now(UTC))
    return (localized - timedelta(hours=settings.business_day_start_hour)).date()


def business_today() -> date:
    return business_date()


def day_bounds(value: date) -> tuple[datetime, datetime]:
    timezone = business_timezone()
    local_start = datetime.combine(
        value,
        time(hour=settings.business_day_start_hour),
        tzinfo=timezone,
    )
    local_end = local_start + timedelta(days=1, microseconds=-1)
    return (
        local_start.astimezone(UTC).replace(tzinfo=None),
        local_end.astimezone(UTC).replace(tzinfo=None),
    )


def local_day_bounds(value: date) -> tuple[datetime, datetime]:
    """Bounds for business-local values intentionally stored without a timezone."""
    start = datetime.combine(value, time(hour=settings.business_day_start_hour))
    return start, start + timedelta(days=1, microseconds=-1)
