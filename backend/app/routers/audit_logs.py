from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_roles
from app.models import AuditLog, User, UserRole
from app.schemas import AuditPage
from app.services.business_time import day_bounds

router = APIRouter(prefix="/audit-logs", tags=["audit"])
root_only = require_roles(UserRole.ROOT)


@router.get("", response_model=AuditPage)
def list_audit_logs(
    actor_id: int | None = None,
    category: str | None = Query(default=None, max_length=40),
    action: str | None = Query(default=None, max_length=80),
    day: date | None = None,
    search: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    _: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> AuditPage:
    filters = []
    if actor_id is not None:
        filters.append(AuditLog.actor_id == actor_id)
    if category:
        filters.append(AuditLog.category == category)
    if action:
        filters.append(AuditLog.action == action)
    if day:
        start, end = day_bounds(day)
        filters.append(AuditLog.created_at.between(start, end))
    if search:
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                AuditLog.summary.ilike(term),
                AuditLog.actor_username.ilike(term),
                AuditLog.entity_type.ilike(term),
                AuditLog.entity_id.ilike(term),
            )
        )
    total = db.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0
    items = list(
        db.scalars(
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return AuditPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/facets")
def audit_facets(_: User = Depends(root_only), db: Session = Depends(get_db)) -> dict:
    categories = [row[0] for row in db.execute(select(AuditLog.category).distinct().order_by(AuditLog.category))]
    actions = [row[0] for row in db.execute(select(AuditLog.action).distinct().order_by(AuditLog.action))]
    users = [
        {"id": user.id, "username": user.username, "full_name": user.full_name}
        for user in db.scalars(select(User).order_by(User.full_name))
    ]
    return {"categories": categories, "actions": actions, "users": users}
