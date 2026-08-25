from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.core.config import settings
from app.db import engine
from app.routers import (
    audit_logs,
    auth,
    config,
    inventory,
    kitchen,
    notifications,
    orders,
    purchases,
    reports,
    users,
)

app = FastAPI(
    title=f"{settings.app_name} API",
    version="1.0.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)

if settings.app_env != "production":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3100", "http://127.0.0.1:3100"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

upload_dir = Path(settings.upload_dir)
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

app.include_router(config.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(inventory.router)
app.include_router(purchases.router)
app.include_router(orders.router)
app.include_router(kitchen.router)
app.include_router(reports.router)
app.include_router(audit_logs.router)
app.include_router(notifications.router)


@app.get("/ready", tags=["configuration"])
def readiness() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected"}
