from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.core.security import create_access_token, verify_password
from app.db import get_db
from app.deps import client_ip, get_current_user
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserRead

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        record_audit(
            db,
            actor=user,
            action="login_failed",
            category="security",
            entity_type="session",
            entity_id=None,
            summary=f"Failed login for {payload.username}",
            ip_address=client_ip(request),
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
    token, expires_at = create_access_token(user.id, user.role.value)
    record_audit(
        db,
        actor=user,
        action="login",
        category="security",
        entity_type="session",
        entity_id=None,
        summary="Signed in",
        ip_address=client_ip(request),
    )
    db.commit()
    return TokenResponse(access_token=token, expires_at=expires_at, user=user)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user

