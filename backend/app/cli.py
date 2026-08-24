import argparse
import sys

from sqlalchemy import select

from app.audit import record_audit
from app.core.config import settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import Category, User, UserRole


def bootstrap() -> None:
    if len(settings.root_password) < 12:
        raise RuntimeError("ROOT_PASSWORD must contain at least 12 characters")
    if len(settings.app_secret_key) < 32:
        raise RuntimeError("APP_SECRET_KEY must contain at least 32 characters")
    with SessionLocal() as db:
        root = db.scalar(select(User).where(User.role == UserRole.ROOT))
        if root is None:
            if db.scalar(select(User.id).where(User.username == settings.root_username)):
                raise RuntimeError("ROOT_USERNAME is already used by a non-root account")
            root = User(
                username=settings.root_username,
                full_name=settings.root_full_name,
                password_hash=hash_password(settings.root_password),
                role=UserRole.ROOT,
            )
            db.add(root)
            db.flush()
            record_audit(
                db,
                actor=root,
                action="bootstrap",
                category="system",
                entity_type="user",
                entity_id=root.id,
                summary="Created deployment root account",
            )
            print(f"Created root account: {root.username}")
        else:
            print(f"Root account already exists: {root.username}")

        if not db.scalar(select(Category.id).limit(1)):
            db.add_all(
                [
                    Category(name="مواد اولیه", color="#2563eb", description="مواد خام و اولیه آشپزخانه"),
                    Category(name="نوشیدنی", color="#06b6d4", description="نوشیدنی‌ها و ملزومات آن‌ها"),
                    Category(name="بسته‌بندی", color="#8b5cf6", description="لیوان، جعبه، پاکت و ظروف مصرفی"),
                    Category(name="نظافت", color="#10b981", description="مواد شوینده و بهداشتی"),
                ]
            )
            print("Created starter inventory categories")
        db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Blue Me management commands")
    parser.add_argument("command", choices=["bootstrap"], help="Command to run")
    args = parser.parse_args()
    if args.command == "bootstrap":
        bootstrap()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
