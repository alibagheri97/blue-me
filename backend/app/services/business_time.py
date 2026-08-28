from datetime import UTC, date, datetime, time
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


def business_today() -> date:
    return datetime.now(UTC).astimezone(business_timezone()).date()


def day_bounds(value: date) -> tuple[datetime, datetime]:
    timezone = business_timezone()
    local_start = datetime.combine(value, time.min, tzinfo=timezone)
    local_end = datetime.combine(value, time.max, tzinfo=timezone)
    return (
        local_start.astimezone(UTC).replace(tzinfo=None),
        local_end.astimezone(UTC).replace(tzinfo=None),
    )


def local_day_bounds(value: date) -> tuple[datetime, datetime]:
    """Bounds for business-local values intentionally stored without a timezone."""
    return datetime.combine(value, time.min), datetime.combine(value, time.max)
