from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db import get_db
from app.models import (
    AttendanceRecord,
    ChecklistPhase,
    CheckInChecklistItem,
    StaffMember,
    User,
    UserRole,
)

bearer = HTTPBearer(auto_error=False)


def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is unavailable")
    return user


def get_current_user(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> User:
    required_item = db.scalar(
        select(CheckInChecklistItem.id)
        .where(
            CheckInChecklistItem.user_id == user.id,
            CheckInChecklistItem.is_active.is_(True),
            CheckInChecklistItem.phase == ChecklistPhase.ENTRY,
        )
        .limit(1)
    )
    if required_item is None:
        return user
    open_attendance = db.execute(
        select(AttendanceRecord.id, AttendanceRecord.entry_checklist_completed_at)
        .join(StaffMember, StaffMember.id == AttendanceRecord.staff_member_id)
        .where(
            StaffMember.user_id == user.id,
            StaffMember.is_active.is_(True),
            AttendanceRecord.checked_out_at.is_(None),
        )
        .limit(1)
    ).one_or_none()
    if open_attendance is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "CHECK_IN_REQUIRED",
                "message": "Complete your required check-in checklist first",
            },
        )
    if open_attendance.entry_checklist_completed_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ENTRY_CHECKLIST_REQUIRED",
                "message": "Complete the checklist after checking in",
            },
        )
    return user


def require_roles(*roles: UserRole) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission")
        return user

    return dependency


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:64]
    return request.client.host[:64] if request.client else None
