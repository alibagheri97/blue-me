from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, role: str) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": str(user_id), "role": role, "exp": expires_at, "iat": datetime.now(UTC)}
    return jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM), expires_at


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])

