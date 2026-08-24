import os
os.environ["DATABASE_URL_OVERRIDE"] = "sqlite+pysqlite://"
os.environ["APP_SECRET_KEY"] = "test-secret-key-that-is-longer-than-32-characters"
os.environ["APP_ENV"] = "test"
os.environ["UPLOAD_DIR"] = "/tmp/blue-me-test-uploads"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db import Base, get_db
from app.main import app
from app.models import User, UserRole


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        session.add_all(
            [
                User(
                    username="root",
                    full_name="Root Admin",
                    password_hash=hash_password("root-password-123"),
                    role=UserRole.ROOT,
                ),
                User(
                    username="storage",
                    full_name="Storage Manager",
                    password_hash=hash_password("storage-password-123"),
                    role=UserRole.STORAGE_MANAGER,
                ),
                User(
                    username="accounting",
                    full_name="Accounting Manager",
                    password_hash=hash_password("accounting-password-123"),
                    role=UserRole.ACCOUNTING_MANAGER,
                ),
                User(
                    username="kitchen",
                    full_name="Kitchen Manager",
                    password_hash=hash_password("kitchen-password-123"),
                    role=UserRole.KITCHEN_MANAGER,
                ),
            ]
        )
        session.commit()

        def override_db():
            yield session

        app.dependency_overrides[get_db] = override_db
        yield session
        app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session: Session):
    with TestClient(app) as test_client:
        yield test_client


def auth_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def root_headers(client: TestClient):
    return auth_headers(client, "root", "root-password-123")


@pytest.fixture()
def storage_headers(client: TestClient):
    return auth_headers(client, "storage", "storage-password-123")


@pytest.fixture()
def accounting_headers(client: TestClient):
    return auth_headers(client, "accounting", "accounting-password-123")


@pytest.fixture()
def kitchen_headers(client: TestClient):
    return auth_headers(client, "kitchen", "kitchen-password-123")
