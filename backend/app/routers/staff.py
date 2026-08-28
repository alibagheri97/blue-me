from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit
from app.db import get_db
from app.deps import client_ip, require_roles
from app.models import Order, OrderItem, OrderStatus, StaffMember, User, UserRole
from app.schemas import OrderRead, StaffMemberCreate, StaffMemberRead, StaffMemberUpdate

router = APIRouter(prefix="/staff", tags=["staff"])
root_only = require_roles(UserRole.ROOT)
staff_view_roles = require_roles(UserRole.ROOT, UserRole.ACCOUNTING_MANAGER)


def staff_stats_subquery():
    order_costs = (
        select(
            Order.id.label("order_id"),
            Order.staff_member_id.label("staff_member_id"),
            Order.subtotal.label("menu_value"),
            Order.created_at.label("created_at"),
            func.coalesce(func.sum(OrderItem.line_cost), 0).label("estimated_cost"),
        )
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(
            Order.is_staff_meal.is_(True),
            Order.staff_member_id.is_not(None),
            Order.status != OrderStatus.CANCELLED,
        )
        .group_by(Order.id, Order.staff_member_id, Order.subtotal, Order.created_at)
        .subquery()
    )
    return (
        select(
            order_costs.c.staff_member_id,
            func.count(order_costs.c.order_id).label("meal_count"),
            func.coalesce(func.sum(order_costs.c.menu_value), 0).label("menu_value"),
            func.coalesce(func.sum(order_costs.c.estimated_cost), 0).label(
                "estimated_cost"
            ),
            func.max(order_costs.c.created_at).label("last_meal_at"),
        )
        .group_by(order_costs.c.staff_member_id)
        .subquery()
    )


def staff_query():
    stats = staff_stats_subquery()
    return (
        select(
            StaffMember,
            stats.c.meal_count,
            stats.c.menu_value,
            stats.c.estimated_cost,
            stats.c.last_meal_at,
        )
        .outerjoin(stats, stats.c.staff_member_id == StaffMember.id)
        .options(selectinload(StaffMember.user))
    )


def serialize_staff(row, *, actor: User) -> StaffMemberRead:
    member, meal_count, menu_value, estimated_cost, last_meal_at = row
    return StaffMemberRead(
        id=member.id,
        name=member.name,
        phone=member.phone,
        position=member.position,
        user_id=member.user_id,
        notes=member.notes,
        is_active=member.is_active,
        created_at=member.created_at,
        updated_at=member.updated_at,
        user=member.user,
        is_current_user=member.user_id == actor.id,
        meal_count=int(meal_count or 0),
        menu_value=Decimal(menu_value or 0),
        estimated_cost=Decimal(estimated_cost or 0),
        last_meal_at=last_meal_at,
    )


def read_staff(db: Session, staff_id: int, *, actor: User) -> StaffMemberRead:
    row = db.execute(staff_query().where(StaffMember.id == staff_id)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return serialize_staff(row, actor=actor)


def ensure_unique_links(
    db: Session,
    *,
    phone: str | None,
    user_id: int | None,
    exclude_id: int | None = None,
) -> None:
    if phone:
        query = select(StaffMember.id).where(StaffMember.phone == phone)
        if exclude_id is not None:
            query = query.where(StaffMember.id != exclude_id)
        if db.scalar(query) is not None:
            raise HTTPException(status_code=409, detail="Staff phone already exists")
    if user_id is not None:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=422, detail="Linked user account not found")
        query = select(StaffMember.id).where(StaffMember.user_id == user_id)
        if exclude_id is not None:
            query = query.where(StaffMember.id != exclude_id)
        if db.scalar(query) is not None:
            raise HTTPException(
                status_code=409,
                detail="User account is already linked to a staff member",
            )


@router.get("", response_model=list[StaffMemberRead])
def list_staff(
    search: str = Query(default="", max_length=100),
    active: bool | None = None,
    actor: User = Depends(staff_view_roles),
    db: Session = Depends(get_db),
) -> list[StaffMemberRead]:
    query = staff_query()
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                StaffMember.name.ilike(term),
                StaffMember.phone.ilike(term),
                StaffMember.position.ilike(term),
            )
        )
    if active is not None:
        query = query.where(StaffMember.is_active == active)
    query = query.order_by(
        case((StaffMember.user_id == actor.id, 0), else_=1),
        StaffMember.is_active.desc(),
        StaffMember.name,
    )
    return [serialize_staff(row, actor=actor) for row in db.execute(query).all()]


@router.post("", response_model=StaffMemberRead, status_code=status.HTTP_201_CREATED)
def create_staff(
    payload: StaffMemberCreate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> StaffMemberRead:
    ensure_unique_links(db, phone=payload.phone, user_id=payload.user_id)
    member = StaffMember(**payload.model_dump())
    db.add(member)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create",
        category="staff",
        entity_type="staff_member",
        entity_id=member.id,
        summary=f"Created staff account for {member.name}",
        details={
            "position": member.position,
            "phone": member.phone,
            "linked_user_id": member.user_id,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    return read_staff(db, member.id, actor=actor)


@router.patch("/{staff_id}", response_model=StaffMemberRead)
def update_staff(
    staff_id: int,
    payload: StaffMemberUpdate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> StaffMemberRead:
    member = db.get(StaffMember, staff_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    changes = payload.model_dump(exclude_unset=True)
    ensure_unique_links(
        db,
        phone=changes.get("phone", member.phone),
        user_id=changes.get("user_id", member.user_id),
        exclude_id=member.id,
    )
    for key, value in changes.items():
        setattr(member, key, value)
    record_audit(
        db,
        actor=actor,
        action="update",
        category="staff",
        entity_type="staff_member",
        entity_id=member.id,
        summary=f"Updated staff account for {member.name}",
        details={key: str(value) for key, value in changes.items()},
        ip_address=client_ip(request),
    )
    db.commit()
    return read_staff(db, member.id, actor=actor)


@router.delete("/{staff_id}", response_model=StaffMemberRead)
def deactivate_staff(
    staff_id: int,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> StaffMemberRead:
    member = db.get(StaffMember, staff_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    member.is_active = False
    record_audit(
        db,
        actor=actor,
        action="deactivate",
        category="staff",
        entity_type="staff_member",
        entity_id=member.id,
        summary=f"Deactivated staff account for {member.name}",
        details={"linked_user_id": member.user_id},
        ip_address=client_ip(request),
    )
    db.commit()
    return read_staff(db, member.id, actor=actor)


@router.get("/{staff_id}/orders", response_model=list[OrderRead])
def staff_order_history(
    staff_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(staff_view_roles),
    db: Session = Depends(get_db),
) -> list[Order]:
    if db.get(StaffMember, staff_id) is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    query = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.staff_member_id == staff_id, Order.is_staff_meal.is_(True))
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(query).unique())
