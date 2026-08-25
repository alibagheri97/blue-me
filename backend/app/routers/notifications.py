from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Notification, User
from app.schemas import NotificationRead

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    filters = [Notification.recipient_user_id == actor.id]
    if unread_only:
        filters.append(Notification.is_read.is_(False))
    items = list(
        db.scalars(
            select(Notification)
            .where(*filters)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    )
    unread_count = db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.recipient_user_id == actor.id,
            Notification.is_read.is_(False),
        )
    ) or 0
    return {
        "items": [NotificationRead.model_validate(item) for item in items],
        "unread_count": unread_count,
    }


@router.post("/{notification_id}/read", response_model=NotificationRead)
def read_notification(
    notification_id: int,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Notification:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_user_id == actor.id,
        )
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        db.refresh(notification)
    return notification


@router.post("/read-all")
def read_all_notifications(
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    notifications = list(
        db.scalars(
            select(Notification).where(
                Notification.recipient_user_id == actor.id,
                Notification.is_read.is_(False),
            )
        )
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    for notification in notifications:
        notification.is_read = True
        notification.read_at = now
    db.commit()
    return {"updated": len(notifications)}
