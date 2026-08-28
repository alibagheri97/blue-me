from fastapi import APIRouter, Depends, Request
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.db import get_db
from app.deps import client_ip, get_current_user, require_roles
from app.models import Order, OrderStatus, User, UserRole, utcnow
from app.schemas import SystemSettingsRead, SystemSettingsUpdate
from app.services.system_settings import get_system_settings

router = APIRouter(prefix="/settings", tags=["settings"])
root_only = require_roles(UserRole.ROOT)


@router.get("", response_model=SystemSettingsRead)
def read_system_settings(
    _: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SystemSettingsRead:
    settings = get_system_settings(db)
    db.commit()
    db.refresh(settings)
    return SystemSettingsRead.model_validate(settings)


@router.patch("", response_model=SystemSettingsRead)
def update_system_settings(
    payload: SystemSettingsUpdate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> SystemSettingsRead:
    settings = get_system_settings(db, lock=True)
    previous = settings.kitchen_workflow_enabled
    completed_orders = 0
    if previous and not payload.kitchen_workflow_enabled:
        result = db.execute(
            update(Order)
            .where(
                Order.status.in_(
                    [OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY]
                )
            )
            .values(status=OrderStatus.COMPLETED, updated_at=utcnow())
        )
        completed_orders = result.rowcount or 0
    settings.kitchen_workflow_enabled = payload.kitchen_workflow_enabled
    settings.updated_by_id = actor.id
    record_audit(
        db,
        actor=actor,
        action="update",
        category="settings",
        entity_type="system_settings",
        entity_id=settings.id,
        summary=(
            "گردش سه‌مرحله‌ای آشپزخانه فعال شد"
            if settings.kitchen_workflow_enabled
            else "گردش سه‌مرحله‌ای آشپزخانه غیرفعال شد"
        ),
        details={
            "kitchen_workflow_enabled": settings.kitchen_workflow_enabled,
            "previous_value": previous,
            "active_orders_completed": completed_orders,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(settings)
    return SystemSettingsRead.model_validate(settings)
