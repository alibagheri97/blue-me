from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.models import (
    ApprovalStatus,
    DailyNeed,
    InventoryItem,
    NeedPriority,
    NeedSource,
    Notification,
    User,
    UserRole,
)
from app.services.business_time import business_today


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _notify_roots(db: Session, need: DailyNeed) -> None:
    roots = db.scalars(
        select(User).where(User.role == UserRole.ROOT, User.is_active.is_(True))
    )
    for root in roots:
        db.add(
            Notification(
                recipient_user_id=root.id,
                kind="automatic_purchase_need",
                title="هشدار موجودی و خرید فردا",
                message=(
                    f"موجودی {need.item_name} به حد سفارش رسیده است؛ "
                    f"{need.quantity.normalize()} {need.unit} برای خرید فردا پیشنهاد شد."
                ),
                entity_type="daily_need",
                entity_id=str(need.id),
            )
        )


def _close_notifications(db: Session, need_id: int) -> None:
    notifications = db.scalars(
        select(Notification).where(
            Notification.entity_type == "daily_need",
            Notification.entity_id == str(need_id),
            Notification.is_read.is_(False),
        )
    )
    now = _now()
    for notification in notifications:
        notification.is_read = True
        notification.read_at = now


def sync_auto_purchase_need(
    db: Session,
    *,
    item: InventoryItem,
    actor: User,
    supply_received: bool = False,
) -> DailyNeed | None:
    """Keep tomorrow's automatic purchase need aligned with the locked stock row."""
    tomorrow = business_today() + timedelta(days=1)
    existing = db.scalar(
        select(DailyNeed)
        .where(
            DailyNeed.inventory_item_id == item.id,
            DailyNeed.required_date == tomorrow,
            DailyNeed.source == NeedSource.AUTOMATIC,
            DailyNeed.status.in_([ApprovalStatus.PENDING, ApprovalStatus.APPROVED]),
        )
        .order_by(DailyNeed.id.desc())
        .with_for_update()
    )
    enabled = (
        item.is_active
        and item.auto_reorder_enabled
        and Decimal(item.target_stock_level) > Decimal(item.reorder_level)
    )
    is_low = enabled and Decimal(item.current_quantity) <= Decimal(item.reorder_level)

    if not is_low:
        if existing is not None:
            existing.status = (
                ApprovalStatus.FULFILLED if supply_received else ApprovalStatus.CANCELLED
            )
            existing.decided_by_id = actor.id
            existing.decided_at = _now()
            existing.decision_note = (
                "موجودی با ورود کالا تأمین شد"
                if supply_received
                else "هشدار پس از تغییر موجودی یا حد سفارش دیگر فعال نیست"
            )
            _close_notifications(db, existing.id)
            record_audit(
                db,
                actor=actor,
                action=f"auto_need_{existing.status.value}",
                category="daily_needs",
                entity_type="daily_need",
                entity_id=existing.id,
                summary=f"Automatic purchase need closed for {item.name}",
                details={"stock": str(item.current_quantity), "status": existing.status.value},
            )
        return None

    suggested = Decimal(item.target_stock_level) - Decimal(item.current_quantity)
    priority = NeedPriority.URGENT if Decimal(item.current_quantity) <= 0 else NeedPriority.HIGH
    notes = (
        f"پیشنهاد خودکار سیستم: موجودی فعلی {item.current_quantity} {item.unit}، "
        f"حد سفارش {item.reorder_level} و موجودی هدف {item.target_stock_level} {item.unit}."
    )
    if existing is not None:
        existing.quantity = suggested
        existing.priority = priority
        existing.notes = notes
        existing.quantity_at_creation = item.current_quantity
        existing.reorder_level_at_creation = item.reorder_level
        return existing

    need = DailyNeed(
        required_date=tomorrow,
        inventory_item_id=item.id,
        item_name=item.name,
        quantity=suggested,
        unit=item.unit,
        priority=priority,
        source=NeedSource.AUTOMATIC,
        status=ApprovalStatus.PENDING,
        notes=notes,
        quantity_at_creation=item.current_quantity,
        reorder_level_at_creation=item.reorder_level,
        requested_by_id=actor.id,
    )
    db.add(need)
    db.flush()
    _notify_roots(db, need)
    record_audit(
        db,
        actor=actor,
        action="auto_create",
        category="daily_needs",
        entity_type="daily_need",
        entity_id=need.id,
        summary=f"Created automatic purchase need for {item.name}",
        details={
            "stock": str(item.current_quantity),
            "reorder_level": str(item.reorder_level),
            "target": str(item.target_stock_level),
            "suggested_quantity": str(suggested),
        },
    )
    return need
