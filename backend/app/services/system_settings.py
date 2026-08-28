from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SystemSetting


SYSTEM_SETTINGS_ID = 1


def get_system_settings(db: Session, *, lock: bool = False) -> SystemSetting:
    query = select(SystemSetting).where(SystemSetting.id == SYSTEM_SETTINGS_ID)
    if lock:
        query = query.with_for_update()
    settings = db.scalar(query)
    if settings is None:
        settings = SystemSetting(
            id=SYSTEM_SETTINGS_ID,
            kitchen_workflow_enabled=True,
        )
        db.add(settings)
        db.flush()
    return settings
