#!/bin/sh
set -eu

python - <<'PY'
import time
from sqlalchemy import create_engine, text
from app.core.config import settings

last_error = None
for attempt in range(60):
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("MySQL is ready")
        break
    except Exception as exc:
        last_error = exc
        if attempt % 5 == 0:
            print(f"Waiting for MySQL ({attempt + 1}/60): {exc}")
        time.sleep(2)
else:
    raise SystemExit(f"MySQL did not become ready: {last_error}")
PY

alembic -c alembic.ini upgrade head
python -m app.cli bootstrap
exec uvicorn app.main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8100}" --workers "${API_WORKERS:-2}" --proxy-headers --forwarded-allow-ips='*'

