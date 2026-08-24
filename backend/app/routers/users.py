from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.core.security import hash_password
from app.db import get_db
from app.deps import client_ip, require_roles
from app.models import User, UserRole
from app.schemas import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])
root_only = require_roles(UserRole.ROOT)


@router.get("", response_model=list[UserRead])
def list_users(
    role: UserRole | None = None,
    active: bool | None = None,
    _: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> list[User]:
    query = select(User).order_by(User.created_at.desc())
    if role is not None:
        query = query.where(User.role == role)
    if active is not None:
        query = query.where(User.is_active == active)
    return list(db.scalars(query))


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> User:
    if db.scalar(select(User.id).where(User.username == payload.username)):
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create",
        category="users",
        entity_type="user",
        entity_id=user.id,
        summary=f"Created {payload.role.value} account {payload.username}",
        details={"role": payload.role.value, "full_name": payload.full_name},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == UserRole.ROOT:
        raise HTTPException(status_code=400, detail="The deployment root cannot be edited here")
    changes = payload.model_dump(exclude_unset=True, exclude={"password"})
    for key, value in changes.items():
        setattr(user, key, value)
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        changes["password"] = "changed"
    if user.id == actor.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    record_audit(
        db,
        actor=actor,
        action="update",
        category="users",
        entity_type="user",
        entity_id=user.id,
        summary=f"Updated account {user.username}",
        details={key: str(value) for key, value in changes.items()},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return user
